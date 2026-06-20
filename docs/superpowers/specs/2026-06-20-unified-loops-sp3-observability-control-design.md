# v0.6.0 Unified Loops — Sub-project #3: Observability + Control — Design

**Parent:** [v0.6.0 Unified Loop Control Surface](2026-06-19-v0.6.0-unified-loops-design.md) — sub-project #3 of 3 (final MVP slice).
**Builds on:** #1 (PR #232) + #2 (PR #233) — `LoopSpec`, the single executor, `GoalJudgeService`, quality-gate/sandbox.
**Date:** 2026-06-20
**Decisions baked in (user-chosen):** **full** scope incl. configurable auto human-gate checkpoints.

## 1. Recon findings (post-#1/#2) that shape this

- Runner broadcasts `goal_iteration_started` / `goal_iteration_completed` / `goal_loop_ended` via `ProjectSessionManager._broadcast` → SSE (`goal_loop_runner.py:435/496/912`). Frontend dispatches them in `useProjectSession.ts:224–286` into `GoalLoopStatusBanner.vue`.
- `list_session_goal_iterations` (`grd_routes.py:1571`) already returns the full #1/#2 telemetry (verdict, confidence, judge_version, body_kind, tokens_total, cost). **Trace UI is mostly frontend.**
- `get_runner_state` (`goal_loop_runner.py:303`) returns iteration/max/wall/elapsed/not_met_streak — **but not** total_cost_usd/total_tokens or the active caps. Live budget display needs these added.
- **Pause is UI-only today**: `pause_session` (`grd_routes.py:1399`) sets `session_info.paused=True` (suppresses SSE); the runner has only `stop_event` — **no `pause_event`** (`_RunnerState`). A true loop pause needs one.
- Human-gate injection is proven: `session_answer_question`/`session_answer_plan` (`grd_routes.py:1126/1216`) write a stream-json envelope to stdin via `ProjectSessionManager.send_input`. Reusable for gate decisions.
- Highest migration = 170. **#3 needs no migration** (human-gate config lives in the `goal_loop_config` JSON; pause/gate state is runtime).

## 2. Deliverables

### Backend

**2a. True pause / resume (`pause_event`)**
`_RunnerState` gains `pause_event: threading.Event`. The loop checks it at the iteration boundary (just before advancing to the next iteration) and blocks (with a short poll + stop_event check) while paused — process stays alive, no kill. New `pause_runner(session_id)` / `resume_runner(session_id)`. Wire the existing `pause_session`/`resume_session` routes to ALSO pause/resume the runner (today they only flip the SSE flag). Emit `goal_loop_paused` / `goal_loop_resumed`.

**2b. Live status enrichment**
Extend `get_runner_state` with `total_cost_usd`, `total_tokens`, `max_cost_usd`, `max_tokens` (the caps), `paused: bool`, and `awaiting_human: bool`, so the UI shows budget-consumed-vs-cap + state. `monitor_session` surfaces it for goal-loop sessions.

**2c. Mid-loop intervene**
`_RunnerState` gains `pending_note: Optional[str]`. New route `POST /{id}/sessions/{sid}/loop/intervene {message}` → `intervene_runner(session_id, message)` stores the note. The runner prepends the note to the next iteration's prompt (works for both `carry` — via the continue/stdin envelope — and `reset` — via the fresh-session seed), then clears it. Emit `goal_loop_intervened`.

**2d. Human-gate checkpoints (the heavy piece)**
`LoopSpec` gains a `human_gate` on a new `LoopGate` struct: `{ mode: "off" | "every_n" | "on_exit", n: int = 1 }` (default off; `from_legacy_config` reads `human_gate` from the dict). When the runner reaches a gate (every Nth iteration, or just before a terminal exit when `on_exit`), it sets `awaiting_human`, emits `goal_loop_awaiting_human {iteration, gate_reason}`, and blocks (poll + stop_event) until a decision arrives. New route `POST /{id}/sessions/{sid}/loop/gate-decision {decision: "continue"|"modify"|"abort", message?}`:
- `continue` → clear awaiting, proceed.
- `modify` → store `message` as a `pending_note` (2c), then proceed.
- `abort` → set `stop_event`, emit `goal_loop_ended(reason="human_abort")`.
The decision injection reuses the `send_input`/stdin pattern only when needed (carry mode); the gate hold itself is a runner-thread block, decoupled from the agent process.

**2e. New events**
`goal_loop_paused`, `goal_loop_resumed`, `goal_loop_intervened {message}`, `goal_loop_awaiting_human {iteration, gate_reason}`, `goal_loop_gate_resolved {decision}`. All via `_broadcast`.

### Frontend

**2f. Per-iteration trace panel** — a `LoopTracePanel.vue` (or extend `GoalLoopStatusBanner.vue`) rendering the iterations from `listGoalIterations`: per row → iteration #, verdict, confidence, judge source + version, tokens, cost, ouroboros verdict. Live-appends on `goal_iteration_completed` SSE; backfills from the list endpoint on mount.

**2g. Control bar + live budget** — pause / resume / stop / intervene controls + a budget strip (tokens & cost consumed vs caps, elapsed vs wall, pending exit condition) driven by the enriched `monitor`/state + SSE.

**2h. Human-gate approval UI** — when `goal_loop_awaiting_human` fires, show an inline gate card with **Continue / Modify (textarea→message) / Abort**, calling `gate-decision`. Clears on `goal_loop_gate_resolved`.

**2i. grd.ts client + i18n** — `pauseLoop`/`resumeLoop`/`interveneLoop`/`gateDecision` methods; `human_gate` on the loop-config type; `loopControl.*` i18n (en/ko/ja/zh).

## 3. Out of scope (post-MVP)
- Cyclic workflows (`body.kind=workflow_step`) + the standalone Loop Builder surface.
- Trusted-test-source pinning / container isolation (deeper F9).
- GRD autopilot migration.

## 4. Risks & mitigations
- **Runner-thread blocking (pause/gate)** must remain responsive to `stop_event` → block via a short poll loop (e.g. 0.5s) that also checks `stop_event`, never an unbounded wait; cap gate waits with the existing `max_wall_seconds` so a never-answered gate can't hang forever.
- **Pause/gate vs the agent process** — pausing holds the runner loop, but the underlying agent turn may still be mid-flight; pause takes effect at the iteration boundary (documented). Stop remains the immediate kill.
- **Reset-mode intervene/modify** — the note must seed the *fresh* session; covered by 2c prepending to the next iteration prompt for both policies.
- **Backward-compat** — `human_gate` defaults off; pause/resume routes keep their SSE behavior and gain runner control additively; no migration.

## 5. Open questions (resolve in plan)
- Gate-wait timeout: reuse `max_wall_seconds` as the backstop vs a dedicated `gate_timeout`. Plan: reuse `max_wall_seconds` (no new knob) for MVP.
- Trace panel: extend `GoalLoopStatusBanner.vue` vs a new `LoopTracePanel.vue`. Plan: new focused component, hosted by `ProjectSessionPanel.vue`, to keep the banner lean.

## 6. Verification
`just build`; backend targeted pytest (pause_event hold+resume; intervene note prepend; human-gate hold + continue/modify/abort decisions + stop-event responsiveness; enriched get_runner_state; routes) + #1/#2 + goal-loop/ralph regression suites green; frontend `npm run test:run` at the 7-failure baseline (+ new trace/control/gate component tests).

---
**Next:** on approval → writing-plans → execute (TDD, per-task commits), same cadence as #1/#2.
