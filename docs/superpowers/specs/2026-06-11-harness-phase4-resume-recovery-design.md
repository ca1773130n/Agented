# Harness-1 Phase 4 — Restart Recovery, Claude True-Resume, Goal-Loop Re-Entry (Design)

**Date:** 2026-06-11
**Status:** Approved (design)
**Depends on:** Phases 1–3 (PRs #208/#209/#210) — all merged
**Source:** `docs/research/harness-1-integration.md` (P4 + P8, both *refuted as written* by the
adversarial verification — this design implements the corrected reframes); arXiv:2606.02373

## Motivation & verified constraints

Phase 1 made runs recoverable on disk; nothing yet *recovers* them:

- Startup marks crashed `running` executions `interrupted`
  (`_mark_stale_executions`, `migrations/_runner.py:217`) and then **nothing
  re-dispatches them** — they're dead ends. `restore_pending_retries`
  (`lifecycle.py:361`) only revives the *retry queue*, not interrupted runs.
- The one-shot `subprocess.Popen` model holds **no resumable handle** to a
  harness's internal state (P4's original framing was refuted on this). But
  claude's terminal result JSON **does** carry a `session_id`, already parsed at
  `budget_service.py:111` and persisted into `token_usage` — never onto
  `execution_logs.session_id` (column exists, unwritten by this path) and never
  used.
- PTY-backed goal-loop/ralph sessions **cannot reattach** after a restart (fd
  and child are gone; `cleanup_dead_sessions` marks them `failed`) — P8's
  original framing was refuted on this. But durable per-iteration state exists
  (`goal_loop_iterations` migration 122, dead-ends tables, the session's goal
  config passed to `start_runner` via `execution_type_handler.py:487-495`), so
  re-entry belongs at the **orchestration layer**: a fresh session seeded with
  accumulated knowledge.

Decisions made with the user:
1. **Full phase: Units A + B + C.**
2. **Safety policy: manual re-dispatch always; automatic only behind a
   per-trigger opt-in flag (default OFF).**
3. Unit C is **manual/API-first** (no goal-loop UI this phase); the only
   frontend touch is a Re-dispatch button in ExecutionHistory.

---

## Unit A — restart recovery (trigger substrate)

### Provenance + flag (migration 152)
- `execution_logs.redispatched_from TEXT NULL` — links a re-dispatched
  execution to its origin. PRAGMA-guarded ALTER + fresh-DDL update
  (`schema/_core.py`).
- `triggers.auto_redispatch INTEGER DEFAULT 0` — per-trigger opt-in for
  automatic recovery. Same migration, same dual registration.

### Re-dispatch semantics (service fn, used by route + startup)
`ExecutionService.redispatch_execution(execution_id) -> ExecutionResult`-style
service entry point that:
1. Loads the original `execution_logs` row; eligible only when `status` is
   `interrupted` or `failed`. 404/409-style errors otherwise.
2. **No fan-out guard:** refuses (409) if any execution already has
   `redispatched_from = execution_id`.
3. Launches a **new** execution (new `execution_id`) through the **existing
   dispatch path** (the same `execute_with_fallback`/`run_trigger` machinery
   the retry queue uses) with the original row's **stored** `prompt` and
   `trigger_config_snapshot` — a deterministic re-run, no prompt re-render.
4. Sets `redispatched_from` on the new row; audit-logs
   `execution.redispatched`.

### Routes + startup
- `POST /admin/executions/{execution_id}/redispatch` on `executions_router`
  (mirrors the existing cancel/pause handler style).
- Startup recovery step beside `restore_pending_retries` (`lifecycle.py:361`):
  for each `interrupted` execution whose trigger has `auto_redispatch=1` and no
  existing re-dispatch child → call the same service fn (one attempt,
  audit-logged). Everything else waits for the operator.

## Unit B — claude true-resume (context-preserving re-dispatch)

- **Capture:** where post-run usage is recorded (the `extract_token_usage` →
  `record_usage` path in `execution_service.py`), also write the extracted
  `session_id` to `execution_logs.session_id` when present (small UPDATE; the
  column exists).
- **Use:** `CommandBuilder.build()` / `ExecutionService.build_command` gain an
  optional `resume_session_id: Optional[str]` — **claude branch only**, appends
  `["--resume", session_id]`. codex/gemini ignore it (no wired session
  semantics) and always re-dispatch fresh.
- **Wire:** `redispatch_execution` checks the original row: backend `claude`
  AND non-null `session_id` → launch with `resume_session_id` and a short
  continuation prompt (`"You were interrupted while working on the task below.
  Continue from where you left off.\n\n<original prompt>"`); otherwise the
  fresh deterministic re-run from Unit A.
- **Honest limits (in code comments + tests):** SIGKILLed/crashed runs never
  printed the terminal JSON → no `session_id` → automatic fresh fallback.
  True resume mainly benefits *failed-but-cleanly-exited* claude runs.

## Unit C — goal-loop re-entry (P8, orchestration layer)

- **Eligibility without a schema rebuild:** the `project_sessions` status
  CHECK is `('active','paused','completed','failed')` (`_orgs.py`) and SQLite
  cannot widen a CHECK without a table rebuild. So no new status and no
  `cleanup_dead_sessions` change: **`failed` goal-loop sessions are
  resume-eligible** — both restart-killed and genuinely-crashed loops are
  legitimately resumable from accumulated knowledge, and the operator decides.
- **`POST .../sessions/{session_id}/resume-loop`** (manual only; mounted on
  the same router family as the existing goal-loop session routes —
  `grd_routes.py` — exact path mirrors its siblings):
  1. Eligible only for goal-loop-type sessions (`goal_loop`/`ralph_loop`) in
     status `failed`; 409 otherwise; no-fan-out guard via provenance (below).
  2. Reads the session's persisted goal config (whatever
     `execution_type_handler.py:487-495` passes to `start_runner` — the plan
     pins the exact column/blob) + durable history: `goal_loop_iterations`
     rows (iteration count, verdicts) and dead-ends.
  3. Spawns a **fresh** session through the existing
     `execution_type_handler`/`start_runner` entry point, with a re-entry
     context block prepended to the initial prompt: resuming after
     interruption at iteration N, prior verdict summary, known dead ends.
  4. Provenance: `project_sessions.resumed_from TEXT NULL` (migration 152;
     plus `update_project_session` allowlist entry if that helper is used).
  5. Audit-logs `session.loop_resumed`.
- **No PTY reattach, no transcript replay** — the fresh loop continues from
  accumulated knowledge, which is what the substrate can honestly do.

## Frontend (minimal)
- **Re-dispatch button** in `ExecutionHistory.vue` on `interrupted`/`failed`
  rows (and/or the log modal next to the existing actions): calls the Unit-A
  endpoint via a new `executionApi.redispatch(executionId)`
  (`services/api/triggers.ts`), optimistic refresh, disabled state while
  in-flight. i18n keys in `executionHistory.*` across **all four** catalogs.
- Component/view test following the sibling convention.

## Testing & verification gates

**Backend (targeted pytest only):**
- Migration 152: registered; PRAGMA-guarded ALTERs idempotent; fresh DDL
  updated (direct `create_fresh_schema` test, per the Phase-3 lesson).
- Redispatch service: eligible statuses; 409 on fan-out; new execution carries
  the stored prompt + `redispatched_from`; audit logged. Claude resume path:
  `--resume` present exactly when backend=claude AND session_id exists;
  continuation prompt used; codex/gemini always fresh.
- `session_id` capture: recorded onto `execution_logs` from the usage path.
- Startup auto-recovery: only `auto_redispatch=1` triggers; one attempt; skips
  rows with existing children.
- Resume-loop: eligibility; re-entry context contains iteration count +
  dead-ends; spawns via the real entry point (spawn itself mocked); provenance
  set.
- Regressions: `test_execution_service.py`, `test_execution_retry*`,
  `test_litestar_streams.py`, Phase-1/3 harness suites.

**Frontend:** `npm run test:run` (new button test; suite at baseline),
`just build`.
**Lint:** ruff on touched files — no new errors vs `main`.

## Out of scope
Auto-redispatch beyond the opt-in flag; codex/gemini resume; stream-json
migration for early session_id capture; goal-loop UI; PTY reattach;
re-dispatch of `success` runs; retry-count/backoff policies for re-dispatch
(one manual attempt, one auto attempt, period).

## File manifest
**Backend modified:** `app/db/schema/_core.py` (+`_orgs.py` if the status
CHECK needs widening), `app/db/migrations/v07_features.py` (152),
`app/db/execution_logs.py` (provenance helpers), `app/db/triggers.py` or the
trigger-config path for `auto_redispatch`, `app/services/execution_service.py`
(redispatch + session_id capture), `app/services/command_builder.py`
(`resume_session_id`), `app/services/project_session_manager.py`
(cleanup split), goal-loop re-entry service fn (new small module or in
`goal_loop_runner.py`), `app_litestar/routes/executions.py` +
`app_litestar/routes/` sessions router (resume-loop), `app_litestar/lifecycle.py`
(startup recovery).
**Frontend:** `services/api/triggers.ts` + `types/triggers.ts`,
`views/ExecutionHistory.vue`, locales ×4, view/component test.
**Tests:** `test_migration_152_redispatch.py`, `test_redispatch_service.py`,
`test_claude_resume_command.py`, `test_startup_auto_redispatch.py`,
`test_goal_loop_reentry.py`, frontend test.
