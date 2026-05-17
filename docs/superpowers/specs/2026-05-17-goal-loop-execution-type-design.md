# `goal_loop` Execution Type — Autonomous Goal-Driven Sessions

**Date:** 2026-05-17
**Status:** Approved — ready to implement
**Depends on:** v0.7.70 (Forge context injection — merged as `0bda955`)

## Decisions (settled — do not re-litigate during implementation)

1. **Goal check mechanism:** both deterministic (operator-supplied
   shell command, exit-0 ⇒ met) and LLM judge (fallback when no
   check command is supplied; sanity layer on long unmet streaks).
2. **UX placement:** new `goal_loop` execution type in
   SessionStartDialog, sibling to direct / ralph_loop / team_spawn.
3. **Judge backend:** all four CLI backends supported
   (claude / codex / gemini / opencode). Per-backend default
   judge model; operator override per session. Default backend
   matches the primary session's backend. See
   [[feedback_llm_features_support_all_backends]].
4. **Continue prompt wording:** fixed template, see "Continue
   prompt synthesis" below.
5. **Forge context bindings:** inherited automatically via the
   existing v0.7.70 path — no goal-loop-specific code needed.

## Problem

Claude Code's `/goal` slash command installs a session-scoped Stop
hook that blocks the session from ending until a natural-language
condition holds. It works beautifully in interactive mode and is
the primary "run until X is done" UX for in-IDE work.

It does **not** work in headless `claude -p` mode: the one-shot
flow has no turn loop for the Stop hook to gate. Agented's
project sessions are exactly that headless-with-a-driver shape
(`ProjectSessionManager` spawns `claude --print --input-format
stream-json …` and feeds user messages over stdin). Today there's
no way to give an Agented session a goal and have it iterate.

Ralph loop (existing execution type) covers the autonomous-loop
shape but terminates on a fixed iteration count, not on a
goal-met predicate. The remaining gap is goal-driven termination.

## Goal

A new execution type, **`goal_loop`**, joins `direct`,
`ralph_loop`, and `team_spawn`. The operator sets a goal in
plain English at session-start, optionally provides a
deterministic check command, and the session auto-continues until
either:

* the goal is met (deterministic check exit 0, OR the LLM judge
  returns "met"), OR
* the iteration cap is reached, OR
* the wall-time cap is reached.

## Scope (v1)

* **Goal predicate sources:**
  * **Deterministic** — operator-supplied shell command run in
    the project cwd. Exit code 0 ⇒ met. Anything else ⇒ not met.
    Stdout captured for the audit log; never injected into
    claude's prompt.
  * **LLM judge** — fired after every assistant turn when no
    deterministic check is configured (or as a sanity layer when
    one IS configured but returns "not met" too many times in a
    row — see "Stale-check protection" below). Reuses the
    existing CLIProxyAPI path; default model `claude-haiku-4-5`
    (cheap + fast); operator can override.
* **Continue prompt synthesis** — when the goal is not yet met,
  the next user message is auto-generated using this template:

  ```
  Goal: <goal>

  Last check: <reason>

  Address the gap and continue.
  ```

  Design notes on the wording (these are settled, not open):
  * Lead with `Goal:` not `Continue toward:`. The goal is fact;
    the verb is implied.
  * `Last check:` is neutral — works for both deterministic
    output (`exit 1: pytest 3 failed`) and LLM verdicts
    (`tests pass but the auth.service still imports from
    ui.middleware`). Avoid `Judge says:` because deterministic
    runs don't go through the judge.
  * Final imperative is `Address the gap and continue` — gives
    claude a clear action without micromanaging method choice.
  * No iteration counter in the prompt. The model doesn't need
    to know it's iteration 7 of 20; surfacing that would risk
    biasing toward giving up. The cap is enforced externally.
  * Same template every turn is intentional. Claude treats it
    as routine; the variable content (`reason`) drives the
    behavior change. Repetition risk is low because the model
    is also seeing its own prior output in the context window.
* **Caps:** iterations (default 20, max 100), wall time (default
  30 min, max 4 h). Either cap stops the loop with a clear status
  reason.
* **UI:** SessionStartDialog gets a new option in the
  execution-type select. When `goal_loop` is picked, the dialog
  reveals: Goal textarea, deterministic-check input
  (placeholder/optional), iteration cap, wall-time cap. The chat
  panel grows a status banner during the run showing
  iteration count + last judge verdict.

Out of scope for v1: branching/backtracking when the judge says
"partial", concurrent goal_loops on one project, plan-mode
integration, human-in-the-loop pause/resume during a goal loop
(the operator can stop the session manually — that's enough).

## Data model

```sql
-- Migration v122: per-session goal config + iteration audit.

ALTER TABLE project_sessions ADD COLUMN goal_loop_config TEXT;
-- JSON: {
--   "goal": "...",
--   "check_cmd": null | "pytest -x",
--   "max_iterations": 20,
--   "max_wall_seconds": 1800,
--   "judge_backend_kind": "claude" | "codex" | "gemini" | "opencode",
--   "judge_model_override": null | "<model name>"
-- }
-- judge_model_override defaults to null; resolution falls back to
-- _DEFAULT_JUDGE_MODEL[judge_backend_kind] at runtime so adding a
-- new default model doesn't require touching stored rows.

CREATE TABLE goal_loop_iterations (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id      TEXT NOT NULL,
  iteration       INTEGER NOT NULL,
  started_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ended_at        TIMESTAMP,
  verdict         TEXT,           -- 'met'|'not_met'|'partial'|'error'
  judge_source    TEXT NOT NULL,  -- 'deterministic'|'llm'|'cap'
  judge_reason    TEXT,
  judge_stdout    TEXT,           -- deterministic check stdout (truncated 4KB)
  tokens_in       INTEGER,
  tokens_out      INTEGER,
  cost_usd        REAL,
  UNIQUE(session_id, iteration)
);
CREATE INDEX idx_goal_iter_session ON goal_loop_iterations(session_id, iteration);
```

`project_sessions.goal_loop_config` is JSON for forward
compatibility (no schema migration for adding goal-related
fields). The iteration table is the audit trail the operator
inspects when figuring out "why did it stop on turn 7?"

## Backend architecture

`backend/app/services/goal_judge_service.py` (new)

```python
# Per-backend default judge model. Each picks the cheapest /
# fastest small model that can handle a two-paragraph yes/no
# prompt — the judge call is fire-and-forget, not the place to
# spend operator dollars.
_DEFAULT_JUDGE_MODEL = {
    "claude":   "claude-haiku-4-5",
    "codex":    "o4-mini",
    "gemini":   "gemini-2.5-flash",
    "opencode": "auto",
}

@dataclass
class JudgeVerdict:
    met: bool
    source: str           # 'deterministic' | 'llm' | 'cap'
    reason: str
    stdout: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0

class GoalJudgeService:
    @classmethod
    def judge(
        cls,
        goal: str,
        last_assistant_text: str,
        *,
        check_cmd: Optional[str] = None,
        cwd: Optional[str] = None,
        backend_kind: str = "claude",
        model_override: Optional[str] = None,
    ) -> JudgeVerdict: ...
```

Behavior:

* If `check_cmd` is set, run it with a 30 s timeout in `cwd`.
  Exit 0 → `JudgeVerdict(met=True, source='deterministic',
  reason='check command exited 0')`. Non-zero → `met=False` with
  stdout in the reason. The LLM judge does NOT run when a
  deterministic check exists (except for the
  stale-check sanity layer described below).
* Else fire the judge prompt against the resolved model. Model
  resolution: `model_override or _DEFAULT_JUDGE_MODEL[backend_kind]`.
  Routing goes through the existing CLIProxyAPI path (its
  OpenAI-compatible endpoint serves all four backends). The
  prompt returns JSON `{met: bool, reason: str}`; parsing is
  forgiving (regex-extract the JSON block from any surrounding
  prose). When parsing fails, `met=False` and `reason="judge
  output unparseable (treated as not_met)"` so the loop
  continues rather than terminating spuriously.
* **All four backends supported.** The operator picks
  `backend_kind` in the dialog; the default is whatever backend
  their primary session uses (so a codex session's judge runs
  on codex by default). See
  [[feedback_llm_features_support_all_backends]] for the
  project-wide rule.

`backend/app/services/execution_type_handler.py` (extend)

```python
class GoalLoopSessionHandler(ExecutionTypeHandler):
    def start(self, session_config: dict) -> dict: ...
    def monitor(self, session_id: str) -> dict: ...
    def stop(self, session_id: str) -> bool: ...
```

Behavior:

* `start` creates the underlying PTY-less stream-json session
  via `ProjectSessionManager.create_session(..., stream_json=True,
  use_pty=False)` — same as a `direct` session, with `claude
  --print --input-format stream-json …`.
* Persists `goal_loop_config` onto the row.
* Spawns a background worker thread (`GoalLoopRunner`) that:
  1. Watches PSM's reader thread for `assistant` events on this
     session_id (subscribe via a new `psm.subscribe(session_id,
     event_filter)` hook OR poll the session's ring buffer —
     decision below).
  2. After each assistant event, calls
     `GoalJudgeService.judge(...)` with the just-emitted text.
  3. Writes a `goal_loop_iterations` row.
  4. If `met` → calls `psm.stop_session(session_id, reason='goal
     met')`. Done.
  5. If not met and caps OK → synthesizes a `user` event
     envelope with the continue prompt and writes to PSM's
     `send_input`.
  6. If caps hit → `stop_session(session_id, reason='iteration
     cap reached'|'wall-time cap reached')`.

**Watching for `assistant` events** — two approaches:

| Approach | Pro | Con |
|---|---|---|
| Add a `subscribe(session_id, callback)` hook to PSM | Clean; goal loop reacts instantly to each turn | Modifies PSM's event-dispatch surface; tests need updating |
| Poll `get_output(last_n=...)` from the runner | Zero PSM changes; isolated to the runner | Latency ~500 ms; awkward to detect "turn boundary vs. mid-turn delta" |

**Pick: subscribe hook.** Latency matters for autonomous loops
(every poll cycle is operator wall-time waiting for the next
iteration to kick off), and the change to PSM is small —
`_reader_thread` already iterates events; add an
in-process subscriber list keyed by session_id.

`backend/app_litestar/routes/grd_routes.py` — `create_session`
already accepts `execution_type`; just register the new handler
and pass `goal_loop_config` through. New route
`GET /api/projects/{id}/sessions/{sid}/goal-iterations` returns
the iteration audit for the inspector panel.

## Frontend

`SessionStartDialog.vue` — extend `executionType` select to
include `goal_loop`. New conditional form group below it shows
when picked:

* **Goal** textarea (required, 5+ chars)
* **Check command** input (optional, monospace, placeholder
  `pytest -x  # exit 0 ⇒ goal met`)
* **Max iterations** numeric input (default 20, range 1–100)
* **Max wall time (minutes)** numeric input (default 30, range
  1–240)
* **Judge backend** select (`claude` / `codex` / `gemini` /
  `opencode`). Default: same backend as the primary session
  (so a codex session's judge runs on codex by default).
* **Judge model** select (optional override; default is the
  per-backend pick from `_DEFAULT_JUDGE_MODEL`). Options drawn
  from `model_discovery_cache` filtered by the picked backend
  kind. Blank value = "use default for this backend".

Confirm payload extends to `goalLoopConfig: { goal, checkCmd,
maxIterations, maxWallSeconds, judgeModel }`. The panel's
`onDialogConfirm` forwards into a new `goal_loop_config` field
on `CreateSessionRequest`.

`ProjectSessionPanel.vue` — when the active session is a
goal loop, render a status banner above the chat:

```
[goal] Refactor auth into modules · iter 4/20 · 18 min left
       Last judge: not_met — "tests pass but module boundary
       still leaks; auth.service imports from ui.middleware"
```

New component `GoalLoopStatusBanner.vue` reads from the new
SSE event types `goal_iteration_started` and
`goal_iteration_completed` (broadcast by `GoalLoopRunner` via
PSM's event channel) and updates live.

`useProjectSession.ts` adds SSE handlers + a `goalLoopState` ref.

## SSE events (new)

| Event | Payload | When |
|---|---|---|
| `goal_iteration_started` | `{iteration, max_iterations, started_at}` | Before judge fires |
| `goal_iteration_completed` | `{iteration, verdict, reason, source}` | After judge returns |
| `goal_loop_ended` | `{reason: 'met'|'iteration_cap'|'wall_time_cap'|'stopped'}` | Loop terminates |

Reuses the existing SSE channel on `/sessions/{sid}/stream`.

## Stale-check protection

If the deterministic check returns "not met" for 5 iterations in
a row, fire the LLM judge as a sanity check on iteration 6. If
LLM judge says "met" but check says "not met", surface a warning
event (`goal_check_disagreement`) and continue the loop — the
operator can decide whether to stop manually. This catches the
case where the check command is wrong but the goal is actually
achieved.

## Testing

* `tests/services/test_goal_judge_service.py` — deterministic
  check timeout / non-zero / zero; LLM judge parsing of
  well-formed + malformed JSON; cost telemetry capture.
* `tests/services/test_goal_loop_runner.py` — fixture session,
  feed mocked assistant events, assert continue-prompt
  synthesis + caps + termination path.
* `tests/routes/test_goal_loop_routes.py` — create session
  with `goal_loop_config`, list iterations, monitor returns
  goal-aware status.
* Frontend: `SessionStartDialog.test.ts` — picking `goal_loop`
  reveals the form; payload shape correct.

## Forge context bindings — inherited automatically

`goal_loop` sessions go through the same
`grd_routes.create_session` path as `direct` sessions, so the
existing v0.7.70 wiring fires for free:

* Project-bound rules / skills compile into
  `--append-system-prompt` on the spawned claude (so the agent
  knows the operator's persona + skill pointers from turn 1).
* Hooks / commands / MCP servers / plugins materialize into the
  per-session `CLAUDE_CONFIG_DIR` overlay via
  `claude_config_overlay.apply_forge_bundle` after PSM creates
  it.
* `SessionStartDialog`'s Forge section (inherited toggles +
  session-only adds + first-prompt attachments) works on goal
  loops too — it's part of the dialog, not specific to direct
  sessions.

This is a free property of the existing architecture — no
goal-loop-specific code needed for Forge context to flow.

## Migration / rollout

Additive. The new execution type defaults to off (operator must
pick it). Existing `direct` / `ralph_loop` / `team_spawn` paths
are unchanged. Migration v122 adds the new column +
table without touching existing data.

## Implementation scope estimate

- Backend: ~600 LOC (judge service ~150, runner ~250, handler
  ~80, route ~50, PSM subscribe hook ~70)
- Migration: ~40 LOC
- Frontend: ~250 LOC (dialog extension ~120, status banner ~80,
  composable additions ~50)
- Tests: ~400 LOC (3 backend suites + 1 frontend)

Single PR, ~1300 LOC net, no breaking changes.

## Out of scope (Phase 2 ideas)

- Plan-mode aware goal loop (judge each `ExitPlanMode` proposal
  against the goal, auto-approve when on-track)
- Branching / backtracking on `partial` verdict
- Cross-session goal: same goal hands off across operator-
  triggered restarts via `project_sessions.parent_session_id`
- Slack/Discord notification on `goal_loop_ended`
