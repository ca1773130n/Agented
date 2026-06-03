# Agented × autoresearch-core — Deterministic Goal-Loop Verdict (DRAFT)

**Date:** 2026-06-03
**Status:** Draft — revised per Codex xhigh review (2026-06-03): kernel verdict is **authoritative** when `metric_spec` is set (never reaches `check_cmd`/`shell=True`); `failure_class` dropped (no subprocess to classify); kernel `VerdictRecord` carried transiently for dead-end gating; `__RESULT__` prompt plumbing added; `Dockerfile` COPY required. Open questions resolved (§6).
**Goal:** Give Agented's goal/Ouroboros loop a **deterministic metric/comparator/target verdict** — the one thing it lacks — by binding the `autoresearch-core` kernel as a new **verdict source** inside `GoalJudgeService.judge`, reusing everything else (the loop, the iteration ledger, the `goal_loop_dead_ends` table, the scheduler/rotation, `hybrid_recall` RRF, Tesserae KG). Behind `AUTORESEARCH_KERNEL_ENABLED` (**default OFF**).

**Depends on:** `autoresearch-core` 0.1.0 (`~/Developer/Projects/autoresearch-core`).

---

## 1. Current state (recon, exact)

- **`JudgeVerdict`** (`services/goal_judge_service.py:~112`) — dataclass: `met, source, reason, stdout, tokens_in, tokens_out, cost_usd, ouroboros_verdict`. **No metric/evidence fields.**
- **`GoalJudgeService.judge`** (`:~137`) — classmethod; dispatch: `check_cmd` → `_run_deterministic` (`subprocess.run(check_cmd, shell=True)`, `met = returncode==0`); else `hypothesis+predicted_outcome` → `_run_ouroboros_judge`; else `_run_llm_judge`.
- **`goal_loop_runner.py`** — `judge` call site (`:~324`): `verdict = GoalJudgeService.judge(goal, turn_text, check_cmd=…, hypothesis=…, predicted_outcome=…)`. Dead-end record (`:~384`) fires when `ouroboros and verdict.ouroboros_verdict == "falsified"` → `add_goal_loop_dead_end(session_id, iteration, approach=hypothesis, reason, evidence, approach_hash=_approach_hash(hypothesis))`. Dead-ends injected into the next prompt at `:455`. Local `_approach_hash` = `sha1(lower.strip())[:16]` (`:92`).
- **`db/goal_loop.py`** — `goal_loop_iterations` (cols incl. `verdict, judge_source, judge_reason, judge_stdout, hypothesis, predicted_outcome, ouroboros_verdict`; DDL `v07_features.py:222`); `goal_loop_dead_ends` (`UNIQUE(session_id, approach_hash)`, DDL `:480`); `add_goal_loop_dead_end` (`:138`, idempotent via UNIQUE), `list_goal_loop_dead_ends` (`:178`), `record_goal_loop_iteration_complete` (`:78`).
- **Execution model** — the loop does **not** spawn a subprocess; it reads PTY `turn_text` via `ProjectSessionManager.subscribe_raw` (`turn_done` event). **There is no `__RESULT__` sentinel today** — `turn_text` is the agent output we parse.
- **`embedding_service.hybrid_recall`** (`:196`) — RRF over FTS5+vector; **reuse, do not re-implement.**
- **`config.py`** — module-level constants from `os.environ` (no Settings class).
- **Deps** — `uv` with editable local sources (`[tool.uv.sources]`, e.g. `ai-accounts-core = { path = "../../ai-accounts/packages/core", editable = true }`).
- **Tests** — **SQLite only** (`isolated_db` fixture monkeypatches `config.DB_PATH`, `init_db()`); no Postgres. Pattern: `tests/test_goal_loop_ouroboros.py`.
- `docs/superpowers/specs/` exists.

---

## 2. v1 scope (Codex-decided cut line)

- Add a **`source="kernel"` deterministic verdict branch** in `judge`, evaluated **before the `check_cmd` dispatch**, gated on `AUTORESEARCH_KERNEL_ENABLED` **and** an operator-supplied `MetricSpec`. When set, `metric_spec` is the **authoritative acceptance criterion**: the kernel owns the verdict (supported/refuted/inconclusive via `parse_metrics_line(turn_text)` + `measure`), and the loop **never** reaches `check_cmd` (`shell=True`) or the LLM/ouroboros judges. **No subprocess, no shell.**
- **`MetricSpec` source = operator-supplied at the goal/session level** (parallel to `check_cmd`) — a `metric_spec` config field, NOT parsed from agent prose. The agent is instructed (prompt plumbing, §3-F) to print `__RESULT__ {"<key>": <number>}`; it does NOT supply the comparator/target.
- **Dead-ends:** reuse `goal_loop_dead_ends` (already `UNIQUE`+idempotent). Only a **deterministic refutation** auto-promotes (kernel `should_promote_dead_end`). Record with Agented's existing `_approach_hash` (hash consistency with current dead-ends — do NOT switch to the kernel's hash).
- **Reuse, not port:** scheduler/rotation, `hybrid_recall` RRF, Tesserae KG, the loop, the ledger. **No** memory consolidation; **no** new RRF fuser.
- **Flag** `AUTORESEARCH_KERNEL_ENABLED` (default off); all new behavior gated → byte-identical when off.

---

## 3. Integration points (exact, minimal)

- **A — `JudgeVerdict`** (`:109`): add `metric_spec: Optional[dict] = None` and a **transient** `kernel_record: Optional[object] = None` (the kernel `VerdictRecord`, used by the runner for dead-end gating; NOT persisted). **Drop `failure_class`** — with no subprocess there's no stderr/timeout, so H2/H3/H4 don't apply in the goal loop. Persist a compact summary by setting `JudgeVerdict.stdout` to JSON (`record_goal_loop_iteration_complete` already saves `stdout` → `judge_stdout` at `goal_loop_runner.py:351`).
- **B — `judge`** (`:137`): add `metric_spec: Optional[dict] = None` to the signature; insert a branch **before the `check_cmd` dispatch (`:159`)**. When `metric_spec` is set it is the authoritative criterion — the kernel decides and the loop NEVER reaches `check_cmd`/`shell=True` or the LLM/ouroboros judges:
  ```
  if AUTORESEARCH_KERNEL_ENABLED and metric_spec:
      try:
          spec = MetricSpec(**metric_spec)
      except (TypeError, ValueError):
          spec = None                       # malformed config → ignore, normal dispatch
      if spec is not None:
          metrics = parse_metrics_line(last_assistant_text)
          rec = measure(spec, ExperimentResult(metrics=metrics, exit_code=0))
          # no __RESULT__ yet → metric_key absent → rec.verdict == "inconclusive"
          return JudgeVerdict(
              met=(rec.verdict == "supported"), source="kernel", reason=rec.detail,
              metric_spec=metric_spec, kernel_record=rec,
              stdout=json.dumps({"verdict": rec.verdict, "evidence_level": rec.evidence_level,
                                 "strategy": rec.strategy, "detail": rec.detail}),
          )
  # malformed/absent metric_spec → existing check_cmd/ouroboros/llm dispatch unchanged
  ```
  `inconclusive` (no `__RESULT__` reported yet) → `met=False` → loop continues until the metric is hit. **Precedence:** when `metric_spec` is set, `check_cmd` is ignored (reject configuring both).
- **C — `goal_loop_runner`**: plumb `metric_spec` (from goal/session config, beside `check_cmd`) into the `judge(...)` call (`:324`). After the verdict, **if** flag on **and** `verdict.source == "kernel"` **and** a real `hypothesis` **and** `should_promote_dead_end(verdict.kernel_record)` → `add_goal_loop_dead_end(session_id, iteration, approach=hypothesis, reason=verdict.reason, evidence=…, approach_hash=_approach_hash(hypothesis))`. (sha1 `_approach_hash` kept — `should_promote_dead_end` uses no hash.) The existing ouroboros-falsified path (`:387`) is unchanged.
- **D — `config.py`**: `AUTORESEARCH_KERNEL_ENABLED = os.environ.get("AUTORESEARCH_KERNEL_ENABLED","0") == "1"`.
- **E — deps + Docker**: `pyproject.toml` → add `autoresearch-core` to `dependencies` + `[tool.uv.sources]` `{ path = "../../autoresearch-core", editable = true }` (mirrors `ai-accounts-core`, `pyproject.toml:42`). **The `Dockerfile` must also COPY `autoresearch-core` into the build context** (like it copies `ai-accounts` at `Dockerfile:50`) and use `uv sync --no-editable`; the editable path alone won't resolve in the image.
- **F — prompt plumbing** (`_initial_prompt`/`_continue_prompt` in `goal_loop_runner.py`): when flag on **and** `metric_spec` is set, append a one-line instruction to print the measured metric as a final line `__RESULT__ {"<metric_key>": <number>}`. Gated → no prompt change when off.

---

## 4. Testing (SQLite — fully runnable in the worktree)

- Unit: the `judge` kernel branch (supported/refuted/inconclusive mapping to `met`; no-metrics → fall-through); flag-off → existing dispatch unchanged.
- Loop: a goal-loop run (SQLite `isolated_db`) where `turn_text` carries `__RESULT__` + a `metric_spec` → asserts a `judge_source="kernel"` iteration and (on refuted) exactly one `goal_loop_dead_ends` row (idempotent on re-run).
- Regression: flag OFF → no new behavior, existing `test_goal_loop_ouroboros.py` semantics intact.

---

## 5. Reuse-not-port (explicit, per the duplication audit)

Scheduler/rotation (`rotation_service`), RRF retrieval (`hybrid_recall`), Tesserae KG (`tesserae_integration`), the goal loop + iteration ledger + dead-ends table — all **reused via the existing code**; the kernel contributes only the deterministic verdict + the promotion-authority rule.

---

## 6. Resolved (Codex xhigh review)

1. **`MetricSpec` source:** operator goal/session config `metric_spec`. The agent prints only the `__RESULT__` value — never the comparator/target.
2. **Storage:** no migration. Compact kernel JSON in `JudgeVerdict.stdout` (→ `judge_stdout`); the `VerdictRecord` rides transiently on `JudgeVerdict.kernel_record` for the runner's dead-end gating.
3. **Hashes:** keep Agented's sha1 `_approach_hash`; do not reconcile; the kernel's `should_skip` is NOT used (`_dead_ends_context` handles avoidance). `should_promote_dead_end` uses no hash → no inconsistency.
4. **Docker:** editable path isn't enough — the `Dockerfile` must COPY `autoresearch-core` into the build context (as it copies `ai-accounts` at `Dockerfile:50`) and use `uv sync --no-editable` (§3-E).
5. **`supported → met=True`:** yes for v1 — valid precisely because `metric_spec` is the authoritative goal acceptance criterion.
6. **Failure class:** dropped — no subprocess means no stderr/timeout signal for H2/H3/H4 (§3-A).
7. **Blockers (now in scope):** `__RESULT__` prompt plumbing (§3-F); `MetricSpec(**metric_spec)` validated/caught (§3-B); no-shell guaranteed by kernel authority (§3-B).
