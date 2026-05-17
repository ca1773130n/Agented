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

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from queue import Empty
from typing import Optional

from app.db import (
    add_goal_loop_dead_end,
    list_goal_loop_dead_ends,
    recent_iteration_verdicts,
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

# v0.7.86 — Ouroboros convergence threshold. When the last
# ``_OUROBOROS_CONVERGENCE_WINDOW`` Ouroboros verdicts are all the
# same value (typically ``falsified``), the runner terminates with
# ``reason=ouroboros_convergence`` instead of grinding to the
# iteration cap. Mirrors GRD's ontology-similarity termination
# (Tier-3 #10 in the integration proposal) at a smaller scale —
# we don't compute embedding similarity, just track verdict
# stagnation as a coarse proxy.
_OUROBOROS_CONVERGENCE_WINDOW = 3

# Capture the agent's hypothesis + predicted outcome from the
# turn text. Permissive regex — accepts ``**Hypothesis:**`` or
# ``Hypothesis:`` and similar variations; stops at the next blank
# line so multi-paragraph values stay inside one field.
_HYPOTHESIS_RE = re.compile(
    r"(?:^|\n)\**\s*Hypothesis\s*[:\-]\s*\**\s*(.+?)(?:\n\n|\n\**\s*Predicted|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_PREDICTED_RE = re.compile(
    r"(?:^|\n)\**\s*Predicted(?:\s+outcome)?\s*[:\-]\s*\**\s*(.+?)(?:\n\n|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _extract_hypothesis(turn_text: str) -> tuple[Optional[str], Optional[str]]:
    """Parse ``Hypothesis:`` and ``Predicted outcome:`` from an
    agent turn. Returns ``(hypothesis, predicted_outcome)``; either
    can be None when the agent didn't follow the Ouroboros prompt
    shape (which is fine — we just fall back to the binary judge).
    """
    if not turn_text:
        return None, None
    hyp_match = _HYPOTHESIS_RE.search(turn_text)
    pred_match = _PREDICTED_RE.search(turn_text)
    hypothesis = hyp_match.group(1).strip() if hyp_match else None
    predicted = pred_match.group(1).strip() if pred_match else None
    return hypothesis, predicted


def _approach_hash(hypothesis: str) -> str:
    """Stable hash of a hypothesis for the dead-end UNIQUE
    constraint. SHA-1 truncated to 16 hex chars — short enough to
    fit in the UI and collision-resistant for the few hundred
    iterations a long-running goal loop might produce.
    """
    return hashlib.sha1(hypothesis.lower().strip().encode("utf-8")).hexdigest()[:16]


def _dead_ends_context(session_id: str, limit: int = 5) -> str:
    """Render the last few dead-ends as a bullet list the agent can
    read in its next prompt. Returns empty string when the registry
    is empty so the prompt assembler can no-op cleanly.
    """
    rows = list_goal_loop_dead_ends(session_id)
    if not rows:
        return ""
    lines = ["Previously falsified approaches (do NOT retry these):"]
    for row in rows[:limit]:
        lines.append(f"- {row['approach']} — {row['reason']}")
    return "\n".join(lines)


def _continue_prompt(
    goal: str,
    reason: str,
    *,
    ouroboros: bool = False,
    dead_ends_block: str = "",
) -> str:
    """Synthesize the user message that drives the next turn.

    v0.7.86 — in Ouroboros mode, asks the agent to state its next
    ``Hypothesis:`` and ``Predicted outcome:`` so the judge can
    score them. Also injects the session's dead-end registry so
    the agent can avoid known-bad approaches.
    """
    base = (
        f"Goal: {goal}\n\n"
        f"Last check: {reason}\n\n"
    )
    if ouroboros:
        oboros_tail = (
            "Address the gap and continue. Begin your turn with:\n"
            "**Hypothesis:** <one-line claim about what will work>\n"
            "**Predicted outcome:** <one-line testable prediction>\n\n"
            "Then implement and verify."
        )
        if dead_ends_block:
            return f"{base}{dead_ends_block}\n\n{oboros_tail}"
        return f"{base}{oboros_tail}"
    return f"{base}Address the gap and continue."


def _initial_prompt(goal: str, *, ouroboros: bool = False) -> str:
    """First user message that kicks off the goal-loop session.

    v0.7.86 — in Ouroboros mode, requests the first iteration's
    hypothesis + predicted outcome so the judge can score from
    turn one.
    """
    base = f"Goal: {goal}\n\n"
    if ouroboros:
        return (
            f"{base}"
            "Start working toward the goal. Begin your turn with:\n"
            "**Hypothesis:** <one-line claim about what will work>\n"
            "**Predicted outcome:** <one-line testable prediction>\n\n"
            "Then implement and verify."
        )
    return f"{base}Start working toward the goal. Make progress this turn."


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
    # v0.7.86 — opt-in Ouroboros mode. When enabled, the runner
    # asks the agent for a per-iteration hypothesis + predicted
    # outcome, judges them in 4-state mode, records falsified
    # approaches into ``goal_loop_dead_ends``, and terminates on
    # verdict-stagnation convergence instead of grinding to the
    # iteration cap.
    ouroboros = bool(config.get("ouroboros"))

    queue = ProjectSessionManager.subscribe_raw(session_id)
    try:
        # Kick off the first turn by sending the goal as the
        # initial user message. Without this the runner would
        # block on ``queue.get`` forever — claude has nothing to
        # respond to until something hits its stdin. The reply
        # will trigger the first ``turn_done`` and the normal
        # judge-then-continue loop takes over from there.
        _send_initial(session_id, goal, ouroboros=ouroboros)
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

            # v0.7.86 — Ouroboros mode: extract this turn's
            # hypothesis + predicted outcome so the judge can
            # score the agent's own claim, not just goal vs. turn.
            hypothesis, predicted_outcome = (
                _extract_hypothesis(turn_text) if ouroboros else (None, None)
            )
            verdict = GoalJudgeService.judge(
                goal,
                turn_text,
                check_cmd=check_cmd,
                cwd=cwd,
                backend_kind=backend_kind,
                model_override=model_override,
                hypothesis=hypothesis,
                predicted_outcome=predicted_outcome,
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
                hypothesis=hypothesis,
                predicted_outcome=predicted_outcome,
                ouroboros_verdict=verdict.ouroboros_verdict,
            )
            ProjectSessionManager._broadcast(
                session_id,
                "goal_iteration_completed",
                {
                    "iteration": iteration_no,
                    "verdict": "met" if verdict.met else "not_met",
                    "reason": verdict.reason,
                    "source": verdict.source,
                    "ouroboros_verdict": verdict.ouroboros_verdict,
                },
            )

            if verdict.met:
                _broadcast_end(session_id, reason="met", detail=verdict.reason)
                ProjectSessionManager.stop_session(session_id)
                break

            # v0.7.86 — Ouroboros: record falsified hypotheses
            # into the session's dead-end registry. The UNIQUE
            # constraint on (session_id, approach_hash) keeps
            # repeat attempts of the same approach from
            # multiplying rows.
            if (
                ouroboros
                and hypothesis
                and verdict.ouroboros_verdict == "falsified"
            ):
                add_goal_loop_dead_end(
                    session_id=session_id,
                    iteration=iteration_no,
                    approach=hypothesis,
                    reason=verdict.reason,
                    evidence=(turn_text or "")[-1024:] or None,
                    approach_hash=_approach_hash(hypothesis),
                )

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

            # v0.7.86 — convergence termination. If the last N
            # Ouroboros verdicts are identical (and not
            # ``confirmed``), the agent is stuck in a stagnation
            # pattern; bail out with a distinct reason rather than
            # burning the rest of the iteration cap.
            if ouroboros and verdict.ouroboros_verdict:
                recent = recent_iteration_verdicts(
                    session_id, limit=_OUROBOROS_CONVERGENCE_WINDOW
                )
                if (
                    len(recent) >= _OUROBOROS_CONVERGENCE_WINDOW
                    and len(set(recent)) == 1
                    and recent[0] != "confirmed"
                ):
                    _broadcast_end(
                        session_id,
                        reason="ouroboros_convergence",
                        detail=(
                            f"last {_OUROBOROS_CONVERGENCE_WINDOW} iterations "
                            f"converged on '{recent[0]}' — stopping to avoid "
                            f"further wasted attempts"
                        ),
                    )
                    ProjectSessionManager.stop_session(session_id)
                    break

            dead_ends_block = _dead_ends_context(session_id) if ouroboros else ""
            _send_continue(
                session_id,
                goal,
                verdict.reason,
                ouroboros=ouroboros,
                dead_ends_block=dead_ends_block,
            )
    except Exception:
        logger.error("goal_loop runner crashed for %s", session_id, exc_info=True)
    finally:
        ProjectSessionManager.unsubscribe_raw(session_id, queue)
        _cleanup(session_id)


def _send_continue(
    session_id: str,
    goal: str,
    reason: str,
    *,
    ouroboros: bool = False,
    dead_ends_block: str = "",
) -> None:
    """Write the synthetic continue prompt to claude's stdin."""
    _send_user_text(
        session_id,
        _continue_prompt(
            goal, reason, ouroboros=ouroboros, dead_ends_block=dead_ends_block
        ),
    )


def _send_initial(session_id: str, goal: str, *, ouroboros: bool = False) -> None:
    """Write the initial kickoff prompt to claude's stdin.

    Called once per goal-loop session before the polling loop
    begins so claude has something to respond to and the first
    ``turn_done`` actually arrives.
    """
    _send_user_text(session_id, _initial_prompt(goal, ouroboros=ouroboros))


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
