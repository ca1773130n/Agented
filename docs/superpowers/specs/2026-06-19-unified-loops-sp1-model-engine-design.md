# v0.6.0 Unified Loops — Sub-project #1: Model + Engine — Design

**Parent:** [v0.6.0 Unified Loop Control Surface](2026-06-19-v0.6.0-unified-loops-design.md) — sub-project #1 of 3 (MVP).
**Date:** 2026-06-19
**Decisions baked in:** *extend* (not rebuild) the executor; **deep-unify Ralph** onto the one executor (user-chosen).

## 1. Key recon finding (shapes everything)

`goal_loop_runner` is ALREADY ~80% of the unified executor. It has, today:
- Ordered termination ladder (`goal_loop_runner.py:296–558`): external stop → process-death → judge `met` → iteration cap → wall-time cap → **cost budget** (`max_cost_usd`, `state.total_cost_usd`) → Ouroboros convergence (a stagnation special-case).
- Per-iteration DB tracking → `goal_loop_iterations` (`db/goal_loop.py`; migration `_migrate_122_goal_loop`, `v07_features.py:206`): cols incl. `iteration, verdict, judge_source, tokens_in, tokens_out, cost_usd, hypothesis, ouroboros_verdict`.
- Checkpoint/resume (`_build_resume_context:734`, `resume_goal_loop:839`) via `project_sessions.goal_loop_config` + `resumed_from`.
- External stop (`stop_runner:270`), live state (`get_runner_state:278`), broadcast events (`goal_iteration_started/completed`, `goal_loop_ended`).

Ralph runs a **separate** path: `RalphSessionHandler` (`execution_type_handler.py:141`) injects the `/ralph-loop` skill and lets Claude self-loop; `RalphMonitorService` polls git-commit hash every 30s, circuit-breaks after 3 no-progress checks. Transient (in-memory), no DB iterations, no budgets, no resume. GRD autopilot is pure CLI shell-out (no Agented loop tracking) — out of scope for #1.

**Therefore #1 = formalize the schema + fill 2 research-mandated gaps + rebuild Ralph onto the executor.** Highest migration today = **168** → new = **169**.

## 2. Deliverables

### 2a. `LoopSpec` — the unifying typed schema
New `backend/app/models/loop_spec.py` (msgspec Struct + Pydantic per repo convention). Promotes the untyped goal-loop config dict into:

```
LoopSpec:
  body:
    kind: "agent_task" | "eval_refine"          # workflow_step deferred to post-MVP
    goal: str                                     # the loop's objective / prompt
    agent / backend_kind / model_override          # who runs each iteration
    check_cmd: str | None                          # deterministic done-check (tests, etc.)
  exit:            # ORDERED — first match wins; quality-gate-first, budget LAST (F4)
    quality_gate: { test_pass | metric{name,threshold} | judge{backend,model} } | None
    stagnation:   { no_progress_for: int } | None  # NEW — generic (F8)
    convergence:  bool                             # existing Ouroboros (kept)
    # HARD fallbacks (always enforced):
    max_iterations: int
    max_wall_seconds: int
    max_cost_usd: float                            # existing
    max_tokens: int                                # NEW (F8) — accumulate tokens_in+out
  state:
    context_policy: "carry" | "reset"             # NEW — carry = current continue-prompt;
                                                  #   reset = fresh session/process per iter (Ralph-purist, F1/F2)
    checkpoint: bool                              # reuse existing resume
  meta: { execution_type: "goal_loop" | "ralph" } # discriminator for back-compat + UI
```

Backward-compat: a `LoopSpec.from_legacy_config(dict)` parser accepts the current `goal_loop_config` and `ralph_config` dicts unchanged.

### 2b. Refactor `goal_loop_runner` to consume `LoopSpec`
- `start_runner(session_id, config: dict, cwd)` stays the public entry; internally parses `dict → LoopSpec` via `from_legacy_config` (no caller changes; routes untouched).
- Termination ladder reads from `LoopSpec.exit` instead of bare config keys. The existing checks move behind the spec; order preserved.
- `_RunnerState` → keeps name (internal); gains `total_tokens`.

### 2c. Fill the 2 research-mandated gaps
- **Token budget** (`max_tokens`): the runner already records `tokens_in/out` per iteration; accumulate into `state.total_tokens`, add a ladder check emitting `goal_loop_ended(reason="token_cap")`. (F8 "token snowball".)
- **Generic stagnation** (`stagnation.no_progress_for`): generalize the existing `not_met_streak` (already in `get_runner_state`) + Ouroboros convergence into a configurable "N iterations with no progress" exit. *No-progress* signal per body kind: `agent_task` → no new git commit (reuse `RalphMonitorService`'s commit-hash check, extracted into a shared helper); `eval_refine` → verdict unchanged / score not improving. Emits `goal_loop_ended(reason="stagnation")`. (F8; algorithm = simplest grounded form, see Open Q.)

### 2d. Deep-unify Ralph onto the executor (the big one)
- `RalphSessionHandler.start()` becomes a thin wrapper: build a `LoopSpec{ body.kind=agent_task, exit.stagnation=no_progress_for:3 (git-commit), exit.max_iterations, state.context_policy=reset }` and call `start_runner`. No more `/ralph-loop` skill self-loop.
- The git-commit no-progress check (today in `RalphMonitorService`) becomes the `agent_task` stagnation signal in the shared helper — so the executor drives the loop and decides done/stop, not a side monitor.
- **`context_policy=reset`** is the new executor capability Ralph needs: instead of `_send_continue()` (synthetic prompt into the same long session), spawn a FRESH session/process each iteration with the goal prompt (Ralph-purist fresh context, F1/F2). `carry` keeps today's behavior. This is the single riskiest task → built test-first with parity tests.
- Ralph now gets, for free: DB iteration tracking, token/cost/iteration/wall budgets, stop controls, and **resume** (previously impossible).
- `RalphMonitorService` is retired (its git-check logic survives in the shared helper); `RalphConfig` maps to `LoopSpec` via `from_legacy_config`.

### 2e. Migration 169
- Add `loop_iterations` as the unified table — OR (lower-risk, preferred) keep `goal_loop_iterations` and add a `body_kind TEXT DEFAULT 'eval_refine'` discriminator + `tokens_total INTEGER` convenience col; Ralph writes here too. (Decide in plan; default to extending the existing table to avoid a data migration.)
- Add `max_tokens` / `context_policy` persistence into the stored loop config (it's a JSON blob in `project_sessions.goal_loop_config`, so likely no column change — confirm in plan).

## 3. Out of scope for #1 (later sub-projects / post-MVP)
- Eval quality-gates beyond what goal-loop's judge already does, LLM-judge versioning, sandbox hardening → **sub-project #2**.
- Per-iteration trace UI, live status redesign, human-gate intervene → **sub-project #3**.
- Cyclic workflows (`body.kind=workflow_step`), Loop Builder UI polish → post-MVP.
- GRD autopilot migration (CLI-driven) → not in MVP.

## 4. Risks & mitigations
- **Ralph rewrite changes a working primitive** → TDD + behavior-parity tests (a Ralph LoopSpec reaches the same outcomes); keep `RalphConfig`/route shapes identical; ship behind the existing `execution_type=ralph` so nothing else changes.
- **`context_policy=reset` (fresh session per iteration)** is genuinely new execution → isolate it as its own task, test the spawn/teardown + that budgets/tracking still accrue across the reset boundary.
- **Stagnation false-positives** (killing a loop mid-progress) → default `no_progress_for` conservative (≥3), and it's an *optional* exit (off unless set), never replaces the hard budget fallbacks.

## 5. Open questions (resolve in plan)
- **Stagnation algorithm** — MVP = git-commit-progress (agent_task) + verdict-unchanged (eval_refine); richer signals (output-similarity, repeated-tool-call) deferred. Confirm this is enough.
- **Table strategy** — extend `goal_loop_iterations` (preferred, no data migration) vs new `loop_iterations`. Plan picks one.
- **Resume + context_policy=reset interaction** — resume already replays prior iterations as context; with `reset` each iteration is fresh anyway. Confirm resume semantics for reset loops.

## 6. Verification
`just build`; backend targeted pytest (LoopSpec parse/round-trip incl. legacy configs; runner termination ladder incl. new token + stagnation exits; Ralph-as-LoopSpec parity; context_policy reset vs carry; migration 169) + the existing goal_loop / ralph suites green; frontend `npm run test:run` at the 7-failure baseline.

---
**Next:** writing-plans → task-by-task implementation plan → execute (TDD, per-task commits), same cadence as the GRD/Tesserae milestone.
