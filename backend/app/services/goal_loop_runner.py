"""Goal-loop runner (v0.7.74).

Background thread that drives one ``goal_loop`` session: subscribes
to the underlying claude session's raw event stream, fires
``GoalJudgeService.judge`` after each turn, and either synthesizes
a continue prompt or stops the session.

Decoupled from ``ProjectSessionManager`` so PSM stays a pure PTY +
SSE broadcaster — the goal-loop policy (judge → continue → cap)
lives here. ``RalphMonitorService`` is the sibling pattern for the
ralph_loop execution type.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from queue import Empty
from typing import Optional

from app.db import (
    record_goal_loop_iteration_complete,
    record_goal_loop_iteration_start,
)

from .goal_judge_service import GoalJudgeService
from .project_session_manager import ProjectSessionManager

logger = logging.getLogger(__name__)


# After ``_NO_PROGRESS_STREAK`` deterministic "not met" verdicts in a
# row, fire the LLM judge as a sanity layer (see spec § "Stale-check
# protection"). The LLM verdict doesn't override the deterministic
# stop decision — it raises a ``goal_check_disagreement`` event so
# the operator knows their check command might be wrong while the
# goal is actually met.
_STALE_CHECK_STREAK = 5

# How long the runner thread will block waiting for the next event
# before checking whether the wall-time cap has elapsed. A short
# interval keeps the cap responsive without burning CPU.
_QUEUE_POLL_SECONDS = 1.0


def _continue_prompt(goal: str, reason: str) -> str:
    """Synthesize the user message that drives the next turn.

    Wording is fixed per the spec — short, neutral, imperative.
    Leading with ``Goal:`` keeps the constraint visible across
    turns; ``Last check:`` works for both deterministic and LLM
    judge sources without revealing which one fired. No iteration
    counter — the model shouldn't bias toward giving up.
    """
    return (
        f"Goal: {goal}\n\n"
        f"Last check: {reason}\n\n"
        f"Address the gap and continue."
    )


def _initial_prompt(goal: str) -> str:
    """First user message that kicks off the goal-loop session.

    Without this, the runner subscribes and waits for a
    ``turn_done`` event that never arrives — claude has nothing
    to respond to. The initial prompt is shorter than the
    continue prompt (no "last check" line yet) and uses an
    explicit start verb so the model treats this as the
    instruction, not a status update.
    """
    return (
        f"Goal: {goal}\n\n"
        f"Start working toward the goal. Make progress this turn."
    )


@dataclass
class _RunnerState:
    session_id: str
    config: dict
    started_at: float
    iteration: int = 0
    not_met_streak: int = 0
    stop_event: threading.Event = field(default_factory=threading.Event)


_runners: dict[str, _RunnerState] = {}
_runners_lock = threading.Lock()


def start_runner(session_id: str, config: dict, cwd: Optional[str]) -> None:
    """Spawn the goal-loop runner thread for a session.

    Idempotent — calling twice for the same session is a no-op so
    the route can safely re-trigger on retry.
    """
    with _runners_lock:
        if session_id in _runners:
            return
        state = _RunnerState(
            session_id=session_id,
            config=config,
            started_at=time.time(),
        )
        _runners[session_id] = state

    thread = threading.Thread(
        target=_run,
        args=(state, cwd),
        name=f"goal-loop-{session_id}",
        daemon=True,
    )
    thread.start()


def stop_runner(session_id: str) -> None:
    """Signal the runner thread to exit. Safe to call multiple times."""
    with _runners_lock:
        state = _runners.get(session_id)
    if state:
        state.stop_event.set()


def get_runner_state(session_id: str) -> Optional[dict]:
    """Snapshot the runner state for UI/monitor consumers."""
    with _runners_lock:
        state = _runners.get(session_id)
    if not state:
        return None
    return {
        "iteration": state.iteration,
        "max_iterations": state.config.get("max_iterations", 20),
        "max_wall_seconds": state.config.get("max_wall_seconds", 1800),
        "elapsed_seconds": int(time.time() - state.started_at),
        "not_met_streak": state.not_met_streak,
    }


def _run(state: _RunnerState, cwd: Optional[str]) -> None:
    """Main runner loop. Subscribes once; loops on turn boundaries.

    Termination paths (in priority order):
    1. ``stop_event`` set externally (handler.stop / session
       termination from elsewhere).
    2. PSM emits ``__end__`` (the underlying claude process died).
    3. Judge returns ``met=True`` → request session stop, emit
       ``goal_loop_ended``.
    4. Iteration cap reached.
    5. Wall-time cap reached.
    """
    session_id = state.session_id
    config = state.config
    goal = (config.get("goal") or "").strip()
    if not goal:
        logger.warning("goal_loop: session %s has empty goal; runner exits", session_id)
        _cleanup(session_id)
        return

    check_cmd = config.get("check_cmd")
    backend_kind = config.get("judge_backend_kind", "claude")
    model_override = config.get("judge_model_override")
    max_iterations = int(config.get("max_iterations") or 20)
    max_wall_seconds = int(config.get("max_wall_seconds") or 1800)

    queue = ProjectSessionManager.subscribe_raw(session_id)
    try:
        # Kick off the first turn by sending the goal as the
        # initial user message. Without this the runner would
        # block on ``queue.get`` forever — claude has nothing to
        # respond to until something hits its stdin. The reply
        # will trigger the first ``turn_done`` and the normal
        # judge-then-continue loop takes over from there.
        _send_initial(session_id, goal)
        while not state.stop_event.is_set():
            if time.time() - state.started_at > max_wall_seconds:
                _broadcast_end(
                    session_id,
                    reason="wall_time_cap",
                    detail=f"exceeded {max_wall_seconds}s",
                )
                ProjectSessionManager.stop_session(session_id)
                break

            try:
                event_type, data = queue.get(timeout=_QUEUE_POLL_SECONDS)
            except Empty:
                continue

            if event_type == "__end__":
                # Session ended for some external reason — runner
                # piggybacks on the existing complete event; no need
                # to emit goal_loop_ended (the operator already sees
                # session 'completed').
                logger.info(
                    "goal_loop: session %s ended externally; runner exits",
                    session_id,
                )
                break

            if event_type != "turn_done":
                continue

            # New turn boundary — judge it.
            state.iteration += 1
            iteration_no = state.iteration
            turn_text = data.get("text", "") if isinstance(data, dict) else ""
            row_id = record_goal_loop_iteration_start(session_id, iteration_no)
            ProjectSessionManager._broadcast(
                session_id,
                "goal_iteration_started",
                {"iteration": iteration_no, "max_iterations": max_iterations},
            )

            verdict = GoalJudgeService.judge(
                goal,
                turn_text,
                check_cmd=check_cmd,
                cwd=cwd,
                backend_kind=backend_kind,
                model_override=model_override,
            )

            # If the operator clicked Stop while the judge was
            # running, abort before we record a misleading
            # ``completed`` audit row — the iteration didn't
            # really finish from the operator's POV. Mark the
            # iteration ``stopped`` so the row is still
            # accounted for (no orphan ``pending`` row), but
            # don't broadcast the completion event.
            if state.stop_event.is_set():
                record_goal_loop_iteration_complete(
                    row_id,
                    verdict="not_met",
                    judge_source="stopped",
                    judge_reason="operator stopped session mid-judge",
                )
                break

            record_goal_loop_iteration_complete(
                row_id,
                verdict="met" if verdict.met else "not_met",
                judge_source=verdict.source,
                judge_reason=verdict.reason,
                judge_stdout=verdict.stdout,
                tokens_in=verdict.tokens_in,
                tokens_out=verdict.tokens_out,
                cost_usd=verdict.cost_usd,
            )
            ProjectSessionManager._broadcast(
                session_id,
                "goal_iteration_completed",
                {
                    "iteration": iteration_no,
                    "verdict": "met" if verdict.met else "not_met",
                    "reason": verdict.reason,
                    "source": verdict.source,
                },
            )

            if verdict.met:
                _broadcast_end(session_id, reason="met", detail=verdict.reason)
                ProjectSessionManager.stop_session(session_id)
                break

            state.not_met_streak += 1
            _maybe_stale_check(
                session_id,
                state,
                check_cmd,
                goal,
                turn_text,
                backend_kind,
                model_override,
            )

            if iteration_no >= max_iterations:
                _broadcast_end(
                    session_id,
                    reason="iteration_cap",
                    detail=f"reached {max_iterations} iterations",
                )
                ProjectSessionManager.stop_session(session_id)
                break

            _send_continue(session_id, goal, verdict.reason)
    except Exception:
        logger.error("goal_loop runner crashed for %s", session_id, exc_info=True)
    finally:
        ProjectSessionManager.unsubscribe_raw(session_id, queue)
        _cleanup(session_id)


def _send_continue(session_id: str, goal: str, reason: str) -> None:
    """Write the synthetic continue prompt to claude's stdin."""
    _send_user_text(session_id, _continue_prompt(goal, reason))


def _send_initial(session_id: str, goal: str) -> None:
    """Write the initial kickoff prompt to claude's stdin.

    Called once per goal-loop session before the polling loop
    begins so claude has something to respond to and the first
    ``turn_done`` actually arrives.
    """
    _send_user_text(session_id, _initial_prompt(goal))


def _send_user_text(session_id: str, text: str) -> None:
    """Wrap ``text`` in the stream-json user envelope shape claude
    expects with ``--input-format stream-json`` and write to stdin.

    Shape mirrors ``grd_routes.session_input`` so the runner's
    synthesized messages are indistinguishable from operator-typed
    ones on the wire.
    """
    envelope = {
        "type": "user",
        "session_id": "",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": text}],
        },
        "parent_tool_use_id": None,
    }
    payload = json.dumps(envelope, ensure_ascii=False)
    if not ProjectSessionManager.send_input(session_id, payload):
        logger.warning(
            "goal_loop: failed to deliver user text to %s "
            "(session not active); runner will exit on __end__",
            session_id,
        )


def _maybe_stale_check(
    session_id: str,
    state: _RunnerState,
    check_cmd: Optional[str],
    goal: str,
    turn_text: str,
    backend_kind: str,
    model_override: Optional[str],
) -> None:
    """Stale-check sanity layer.

    Only relevant when a deterministic check is configured. If the
    deterministic check has returned ``not_met`` ``_STALE_CHECK_STREAK``
    times in a row, fire an LLM judge once. If the two disagree
    (LLM says met, deterministic says not met), emit a
    ``goal_check_disagreement`` event so the operator can decide
    whether to stop manually. We do NOT auto-stop on disagreement —
    the deterministic check is still the source of truth for caps.
    """
    if not check_cmd:
        return
    if state.not_met_streak < _STALE_CHECK_STREAK:
        return
    sanity = GoalJudgeService.judge(
        goal,
        turn_text,
        check_cmd=None,
        backend_kind=backend_kind,
        model_override=model_override,
    )
    if sanity.met:
        ProjectSessionManager._broadcast(
            session_id,
            "goal_check_disagreement",
            {
                "iteration": state.iteration,
                "deterministic_reason": "check still returning non-zero",
                "llm_reason": sanity.reason,
                "streak": state.not_met_streak,
            },
        )
    # Reset the streak whichever way the sanity layer landed.
    # Resetting on disagreement is essential (we just told the
    # operator; firing again next turn is noise). Resetting on
    # agreement is also right: leaving the streak high would
    # re-fire the LLM judge EVERY subsequent turn, wasting
    # tokens worse than the once-per-5-turns cadence. The
    # original code did this; the fixed cadence is the right
    # tradeoff.
    state.not_met_streak = 0


def _broadcast_end(session_id: str, *, reason: str, detail: str) -> None:
    ProjectSessionManager._broadcast(
        session_id,
        "goal_loop_ended",
        {"reason": reason, "detail": detail},
    )


def _cleanup(session_id: str) -> None:
    with _runners_lock:
        _runners.pop(session_id, None)
