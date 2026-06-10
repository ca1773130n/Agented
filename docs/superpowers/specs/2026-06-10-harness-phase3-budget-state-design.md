# Harness-1 Phase 3 — Live Budget Discipline + Operator State Surface (Design)

**Date:** 2026-06-10
**Status:** Approved (design); pending plan
**Depends on:** Phase 1 (PR #208: `harness_runs.budget_used`, checkpoints) and Phase 2 (PR #209: `verification_records`) — both merged
**Source:** `docs/research/harness-1-integration.md` (P6 + P7-reframed); arXiv:2606.02373

## Motivation

Phase 1 made runs recoverable; Phase 2 made them auditable. Phase 3 makes them
**observable and budget-disciplined while still running**:

- Today token usage is parsed **only post-run** (`BudgetService.extract_token_usage`
  over the final `stdout_log`), and the only live enforcement is the
  period-aggregate kill in `budget_monitor` (`execution_runner.py:111`).
  A single runaway run burns budget silently until the *period* total trips.
- The state Phases 1–2 persist (`harness_runs` cursor + `budget_used`,
  checkpoints, `verification_records`) has **no operator surface** — neither an
  API endpoint nor a console panel.

Decisions made with the user:
1. **Per-run ceiling = soft warn (~80%) + hard kill (100%)** — consistent with
   the existing period-limit kill; Phase-1 checkpoints make the kill recoverable.
2. **Scope includes a minimal Vue panel**, not just the backend API.

---

## Unit A — P6: per-run incremental accounting + ceiling (backend)

### Where accounting runs
Extend the **existing `budget_monitor` thread** (`execution_runner.py:111`) —
one thread per execution, already polling every 30 s with the process handle.
No new threads; nothing added to the `append_log` hot path.

Each tick, additionally:
1. `partial_log = ExecutionLogService.get_stdout_log(execution_id)` — reads the
   live in-memory buffer mid-run (verified Phase-1 behavior).
2. `usage = BudgetService.extract_token_usage(partial_log, backend_type)` — the
   existing parser works on partial logs.
3. Convert tokens → USD using `BudgetService`'s existing pricing path (the same
   computation `record_usage` uses; the plan pins the exact function). This is a
   **live estimate** — the authoritative `record_usage` at `finish_execution`
   is untouched and remains the source of truth.
4. `harness_state.update_budget_used(execution_id, cost)` — new small repo fn
   (direct UPDATE of `harness_runs.budget_used`; creates the run row if absent,
   mirroring `record_checkpoint`'s upsert semantics).
5. Enforce the per-run ceiling (below).

`budget_monitor` needs the `backend_type` — thread it through from the caller
(`execution_service._budget_monitor`), which has the trigger config in scope.

### Per-backend honesty
- **codex**: JSONL `turn.completed` events accumulate → genuine incremental
  accounting. **opencode**: best-effort.
- **claude / gemini**: usage appears only in the terminal JSON → extraction
  returns `None` mid-run, `budget_used` stays 0 until finish, and per-run
  enforcement cannot trigger mid-run. The checks **no-op when extraction yields
  nothing** — documented limitation (matches the research report's exit
  criteria), not hidden behavior.

### Per-run ceiling
- New **nullable** column `per_run_limit_usd` on `budget_limits`
  (`schema/_misc.py:59`), via PRAGMA-guarded `ALTER TABLE` **migration 151**
  (pattern: `_migrate_144_token_usage_immutable_date`). Update the fresh-schema
  DDL too. Extend `get_budget_limit`/`set_budget_limit` (`db/budgets.py`)
  to read/write it (preserve the existing `hard >= soft` style validation:
  reject negative values).
- **Unset (NULL) = feature off** — default behavior unchanged for existing
  installs.
- In the monitor tick, when a limit is set and `cost` is known:
  - **`cost >= 0.8 × limit`** → one-shot soft signal: append a
    `[BUDGET] approaching per-run limit: $X.XX of $Y.YY` **stderr** line
    (flows to the console through the existing SSE subscribe), plus
    `create_health_alert` and an `execution.budget_warning` audit event.
    A **local boolean in the thread** prevents repeats (one thread per
    execution — no shared state needed).
  - **`cost >= limit`** → SIGKILL via the **same code path** as the existing
    period-limit kill (`os.killpg` + `[BUDGET]` stderr line +
    `execution.budget_exceeded` audit + health alert), with a
    per-run-specific reason string.
- Fail-open: any error in the accounting/enforcement tick is caught and
  logged at debug; the monitor's existing period check is never disrupted.

## Unit B — P7: `GET /executions/{execution_id}/state` (backend)

One read-only handler on the existing `executions_router`
(`app_litestar/routes/executions.py`, beside `GET /executions/{execution_id}`
at `:125`), returning a composed snapshot:

```json
{
  "execution": {"status", "exit_code", "started_at", "finished_at", "duration_ms", "backend_type"},
  "run": {"status", "step_cursor", "budget_used", "updated_at"} | null,
  "latest_checkpoint": {"step", "created_at", "stdout_lines", "stderr_lines"} | null,
  "verifications": [ ...verification_records rows... ],
  "per_run_limit_usd": number | null
}
```

- 404 if the execution doesn't exist; `run`/`latest_checkpoint` are `null` for
  runs that never checkpointed (pre-Phase-1 rows) — the endpoint must not 500
  on them.
- Checkpoint summary only (step + timestamps + the ledger's stored line
  counts) — **not** the raw ledger JSON.
- No `/resume` changes (an in-memory `POST /resume` already exists at `:353`).
  No new SSE channel — the `[BUDGET]` stderr line already streams live.

## Unit C — minimal Vue panel (frontend)

- **`HarnessStatePanel.vue`** (new, `src/components/executions/`): read-only
  panel showing run status, step cursor, live budget (`budget_used` vs
  `per_run_limit_usd`, warning style past 80%), checkpoint freshness
  (step + relative time), and the verification-records list (claim + status +
  checked_at). Fetches `/state` when shown; polls every 5 s while
  `execution.status === 'running'`; stops on terminal status / unmount.
- Mounted in the **execution detail surface in `ExecutionHistory.vue`**
  (the plan pins the exact insertion point).
- **API client**: extend the executions-domain object in `services/api.ts`
  (follow its per-domain pattern) with `getExecutionState(executionId)`.
- **i18n**: new `harnessState.*` namespace added to **all four** catalogs
  (`en`, `ko`, `ja`, `zh`), key-identical.
- **Budget form field**: add `per_run_limit_usd` as one optional field to the
  existing budget-limits form (the `budgetLimitsExtended` surface), wired
  through the existing set-budget API.
- **Tests**: Vitest + @vue/test-utils component test for `HarnessStatePanel`
  (renders states; poll start/stop), following the sibling test convention.

## Testing & verification gates

**Backend (targeted pytest — never the full serial suite):**
- Monitor tick: fake `Popen` + stubbed `extract_token_usage` →
  `budget_used` updates; soft signal fires once (not twice); kill at 100%;
  no-op when extraction returns `None`; fail-open on parser exception;
  NULL limit = no enforcement.
- Migration 151: PRAGMA-guarded ALTER is idempotent; registered in
  `V07_MIGRATIONS` **and** fresh-schema DDL updated; `set/get_budget_limit`
  round-trips the new column.
- `/state` route: full snapshot for a checkpointed+verified execution;
  nulls for a bare execution; 404 for unknown id.
- Regression: `test_execution_service.py`, `test_harness_state_repo.py`,
  `test_execution_log_checkpoint.py`, `test_litestar_streams.py`.

**Frontend:** `just build` (vue-tsc + vite) and `npm run test:run` must pass;
new component test green; all four locale catalogs stay key-identical.

**Lint:** `ruff format` + `ruff check` on all touched backend files.

## Out of scope (later phases / explicitly cut)
- P4 resume / P8 PTY substrate (Phase 4 — still gated on research-report §8).
- Per-event incremental usage parsers for claude/gemini.
- Any SSE protocol changes; any budget UI beyond the single new field.
- Frontend display of the raw checkpoint ledger or evidence ledger (P3 data).

## File manifest
**Backend new:** none (all changes land in existing modules) — except tests:
`tests/test_budget_monitor_per_run.py`, `tests/test_execution_state_route.py`,
`tests/test_migration_151_per_run_limit.py`.
**Backend modified:** `app/services/execution_runner.py` (monitor tick),
`app/services/execution_service.py` (thread `backend_type` into the monitor),
`app/services/budget_service.py` (only if a small cost helper must be exposed),
`app/db/harness_state.py` (`update_budget_used`), `app/db/budgets.py`
(new column in get/set), `app/db/schema/_misc.py` (fresh DDL),
`app/db/migrations/v07_features.py` (migration 151),
`app_litestar/routes/executions.py` (`GET /state`).
**Frontend new:** `src/components/executions/HarnessStatePanel.vue` + test.
**Frontend modified:** `src/views/ExecutionHistory.vue` (mount point),
`src/services/api.ts` (client fn), budget-limits form (one field),
`src/locales/{en,ko,ja,zh}.json` (`harnessState.*` + the budget-field label).
