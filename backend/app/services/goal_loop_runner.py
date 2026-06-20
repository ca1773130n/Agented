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
from queue import Empty, Queue
from typing import Optional

from app.config import AUTORESEARCH_KERNEL_ENABLED
from app.db import (
    add_goal_loop_dead_end,
    list_goal_loop_dead_ends,
    recent_iteration_verdicts,
    record_goal_loop_iteration_complete,
    record_goal_loop_iteration_start,
)
from app.models.loop_spec import LoopSpec

from . import loop_progress
from .goal_judge_service import GoalJudgeService
from .project_session_manager import ProjectSessionManager

# autoresearch_core.should_promote_dead_end is imported lazily inside
# _maybe_promote_kernel_dead_end so flag-off deployments don't require the
# editable sibling package at import time.

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

# Poll interval for the pause/human-gate hold loops. The blocking
# helpers (``_wait_if_paused``, ``_await_gate``) sleep this long
# between re-checks so they stay responsive to ``stop_event`` (and
# the gate's wall-time bound) without an unbounded wait.
_PAUSE_POLL_SECONDS = 0.5

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


def _token_cap_exceeded(total: int, max_tokens: int) -> bool:
    return max_tokens > 0 and total >= max_tokens


def _met_terminates(*, met: bool, confidence: float, gate) -> bool:
    """Dynamic early-termination gate (v0.6.0 sub-project #2).

    A "met" verdict only terminates the loop when its self-reported
    ``confidence`` clears the gate's ``min_confidence`` floor. With no
    gate (or floor 0.0) this degrades to the legacy ``met`` check.
    """
    if not met:
        return False
    floor = getattr(gate, "min_confidence", 0.0) if gate else 0.0
    return confidence >= floor


def _approach_hash(hypothesis: str) -> str:
    """Stable hash of a hypothesis for the dead-end UNIQUE
    constraint. SHA-1 truncated to 16 hex chars — short enough to
    fit in the UI and collision-resistant for the few hundred
    iterations a long-running goal loop might produce.
    """
    return hashlib.sha1(hypothesis.lower().strip().encode("utf-8")).hexdigest()[:16]


def _maybe_promote_kernel_dead_end(
    session_id: str,
    iteration_no: int,
    hypothesis: Optional[str],
    verdict,
    turn_text: str,
) -> None:
    """Promote a deterministic-refutation kernel verdict to the dead-end registry.

    Guards:
    - AUTORESEARCH_KERNEL_ENABLED must be True (flag-off skips entirely)
    - verdict.source must be "kernel" (not deterministic/llm paths)
    - hypothesis must be non-empty (no hypothesis → nothing to record)
    - verdict.kernel_record must not be None (invalid-spec errors have no record)
    - should_promote_dead_end(kernel_record) must return True (refuted, not inconclusive)
    """
    if not (AUTORESEARCH_KERNEL_ENABLED and verdict.source == "kernel" and hypothesis):
        return
    if verdict.kernel_record is None:
        return
    try:
        from autoresearch_core import should_promote_dead_end
    except ImportError:
        return
    if not should_promote_dead_end(verdict.kernel_record):
        return
    add_goal_loop_dead_end(
        session_id=session_id,
        iteration=iteration_no,
        approach=hypothesis,
        reason=verdict.reason,
        evidence=(turn_text or "")[-1024:] or None,
        approach_hash=_approach_hash(hypothesis),
    )


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


_OUROBOROS_HYPOTHESIS_BLOCK = (
    "Begin your turn with:\n"
    "**Hypothesis:** <one-line claim about what will work>\n"
    "**Predicted outcome:** <one-line testable prediction>\n\n"
    "Then implement and verify."
)


def _result_instruction(metric_spec) -> str:
    """Build the __RESULT__ reporting instruction for the agent prompt."""
    key = metric_spec.get("metric_key", "<metric>") if isinstance(metric_spec, dict) else "<metric>"
    return (
        f"\n\nWhen you have measured the target metric, print it as a final line "
        f'exactly: `__RESULT__ {{"{key}": <number>}}`.'
    )


def _continue_prompt(
    goal: str,
    reason: str,
    *,
    ouroboros: bool = True,
    dead_ends_block: str = "",
    result_block: str = "",
) -> str:
    """Synthesize the user message that drives the next turn.

    v0.7.87 — ``ouroboros`` defaults to ``True`` (was an opt-in
    flag in v0.7.86). When enabled, asks the agent for a fresh
    ``Hypothesis:`` + ``Predicted outcome:`` and injects any
    prior dead-ends. Operators who explicitly disable Ouroboros
    via ``goal_loop_config["ouroboros"]: false`` get the legacy
    plain-continue shape.

    v0.7.88 — ``result_block`` appends the ``__RESULT__`` reporting
    instruction when the kernel is active (non-empty string).
    """
    base = f"Goal: {goal}\n\nLast check: {reason}\n\n"
    if not ouroboros:
        return f"{base}Address the gap and continue.{result_block}"
    if dead_ends_block:
        return f"{base}{dead_ends_block}\n\n{_OUROBOROS_HYPOTHESIS_BLOCK}{result_block}"
    return f"{base}{_OUROBOROS_HYPOTHESIS_BLOCK}{result_block}"


def _initial_prompt(
    goal: str,
    *,
    ouroboros: bool = True,
    result_block: str = "",
    resume_context: Optional[str] = None,
) -> str:
    """First user message that kicks off the goal-loop session.

    v0.7.87 — ``ouroboros`` defaults to ``True``. When enabled,
    requests the first iteration's hypothesis + predicted outcome.

    v0.7.88 — ``result_block`` appends the ``__RESULT__`` reporting
    instruction when the kernel is active (non-empty string).

    Phase 4 — ``resume_context`` prepends accumulated history when
    resuming a previously failed session.
    """
    if not ouroboros:
        prompt = (
            f"Goal: {goal}\n\nStart working toward the goal. Make progress this turn.{result_block}"
        )
    else:
        prompt = f"Goal: {goal}\n\nStart working toward the goal. {_OUROBOROS_HYPOTHESIS_BLOCK}{result_block}"
    if resume_context:
        prompt = f"{resume_context}\n\n{prompt}"
    return prompt


@dataclass
class _RunnerState:
    session_id: str
    config: dict
    started_at: float
    iteration: int = 0
    not_met_streak: int = 0
    total_cost_usd: float = 0.0
    stop_event: threading.Event = field(default_factory=threading.Event)
    spec: Optional[LoopSpec] = None  # parsed once at start; ladder reads from here
    total_tokens: int = 0
    no_progress_streak: int = 0
    last_commit: Optional[str] = None
    pause_event: threading.Event = field(default_factory=threading.Event)
    pending_note: Optional[str] = None
    awaiting_human: bool = False
    gate_decision: Optional[tuple] = None  # (decision, message)


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
        execution_type = config.get("_execution_type") or "goal_loop"
        state = _RunnerState(
            session_id=session_id,
            config=config,
            started_at=time.time(),
            spec=LoopSpec.from_legacy_config(config, execution_type=execution_type),
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


def _get_state(session_id: str) -> Optional[_RunnerState]:
    with _runners_lock:
        return _runners.get(session_id)


def pause_runner(session_id: str) -> bool:
    st = _get_state(session_id)
    if st:
        st.pause_event.set()
    return st is not None


def resume_runner(session_id: str) -> bool:
    st = _get_state(session_id)
    if st:
        st.pause_event.clear()
    return st is not None


def intervene_runner(session_id: str, message: str) -> bool:
    st = _get_state(session_id)
    if st:
        st.pending_note = message
    return st is not None


def submit_gate_decision(session_id: str, decision: str, message: Optional[str] = None) -> bool:
    st = _get_state(session_id)
    if st:
        st.gate_decision = (decision, message)
    return st is not None


def _wait_if_paused(state, session_id: str) -> None:
    """Block at the iteration boundary while paused. Always re-checks
    stop_event so a paused loop stays stoppable (never an unbounded wait)."""
    if not state.pause_event.is_set():
        return
    ProjectSessionManager._broadcast(session_id, "goal_loop_paused", {"iteration": state.iteration})
    while state.pause_event.is_set() and not state.stop_event.is_set():
        time.sleep(_PAUSE_POLL_SECONDS)
    if not state.stop_event.is_set():
        ProjectSessionManager._broadcast(
            session_id, "goal_loop_resumed", {"iteration": state.iteration}
        )


def _apply_pending_note(state, reason: str) -> str:
    """Consume an operator intervene/modify note (if any), prepending it to the
    next iteration's prompt reason so both carry and reset policies pick it up."""
    note = getattr(state, "pending_note", None)
    if not note:
        return reason
    state.pending_note = None
    return f"Operator note: {note}\n\n{reason}"


def get_runner_state(session_id: str) -> Optional[dict]:
    """Snapshot the runner state for UI/monitor consumers."""
    with _runners_lock:
        state = _runners.get(session_id)
    if not state:
        return None
    return {
        "iteration": state.iteration,
        "max_iterations": state.spec.exit.max_iterations,
        "max_wall_seconds": state.spec.exit.max_wall_seconds,
        "elapsed_seconds": int(time.time() - state.started_at),
        "not_met_streak": state.not_met_streak,
        "total_cost_usd": state.total_cost_usd,
        "total_tokens": state.total_tokens,
        "max_cost_usd": state.spec.exit.max_cost_usd,
        "max_tokens": state.spec.exit.max_tokens,
        "paused": state.pause_event.is_set(),
        "awaiting_human": state.awaiting_human,
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
    # The runner registry is keyed by the ORIGINAL session_id. Under
    # context_policy=reset the loop re-points ``session_id`` to freshly-spawned
    # child processes, but the registry key (and the route's stop_runner target)
    # must stay stable — so cleanup/teardown always use this captured key.
    registry_key = session_id
    config = state.config
    goal = (config.get("goal") or "").strip()
    if not goal:
        logger.warning("goal_loop: session %s has empty goal; runner exits", session_id)
        _cleanup(registry_key)
        return

    check_cmd = config.get("check_cmd")
    metric_spec = config.get("metric_spec")
    backend_kind = config.get("judge_backend_kind", "claude")
    model_override = config.get("judge_model_override")
    max_iterations = state.spec.exit.max_iterations
    max_wall_seconds = state.spec.exit.max_wall_seconds
    # Optional cost ceiling (USD). 0/unset disables — the loop is then bounded
    # only by iteration + wall caps (06 H1). Each judge verdict records cost_usd.
    max_cost_usd = state.spec.exit.max_cost_usd
    # v0.7.87 — Ouroboros is the default goal-loop mode. The
    # config flag is preserved so operators can disable it
    # (``"ouroboros": false``) when the agent backend is a poor
    # fit for structured hypothesis emission, but the implicit
    # default is now ``True`` (was ``False`` in v0.7.86). When
    # enabled, every iteration asks the agent for a hypothesis +
    # predicted outcome, judges them in 4-state mode, records
    # falsified approaches into ``goal_loop_dead_ends``, and
    # terminates on verdict-stagnation convergence. Agents that
    # don't follow the hypothesis markers degrade gracefully —
    # ``_extract_hypothesis`` returns ``(None, None)`` and the
    # judge falls back to its legacy binary mode for that
    # iteration without losing the audit row.
    ouroboros = state.spec.exit.convergence
    # v0.6.0 sub-project #2 — the quality-gate (test/metric/llm-judge with
    # rubric/version/min_confidence) and the sandbox mode for the eval boundary
    # are carried on the parsed LoopSpec. Both are forwarded to the judge so the
    # deterministic check runs isolated (default) and the LLM judge gets the
    # rubric/version; ``gate.min_confidence`` then gates termination.
    gate = state.spec.exit.quality_gate
    sandbox = state.spec.state.sandbox
    if metric_spec is not None and not AUTORESEARCH_KERNEL_ENABLED:
        # Operator configured a metric_spec but the kernel flag is off — it's
        # silently ignored. Log once so this isn't a confusing no-op.
        logger.warning(
            "goal_loop %s has metric_spec but AUTORESEARCH_KERNEL_ENABLED is off; ignoring it",
            session_id,
        )
    result_block = (
        _result_instruction(metric_spec)
        if (AUTORESEARCH_KERNEL_ENABLED and metric_spec is not None)
        else ""
    )

    queue = ProjectSessionManager.subscribe_raw(session_id)
    try:
        # Kick off the first turn by sending the goal as the
        # initial user message. Without this the runner would
        # block on ``queue.get`` forever — claude has nothing to
        # respond to until something hits its stdin. The reply
        # will trigger the first ``turn_done`` and the normal
        # judge-then-continue loop takes over from there.
        _send_initial(
            session_id,
            goal,
            ouroboros=ouroboros,
            result_block=result_block,
            resume_context=(state.config or {}).get("resume_context"),
        )
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

            # v0.7.87 — extract this turn's hypothesis + predicted
            # outcome when Ouroboros is enabled. If the agent
            # omitted the markers, both values are ``None`` and the
            # judge falls back to its legacy binary path
            # automatically. Disabled-Ouroboros sessions skip
            # extraction entirely.
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
                metric_spec=metric_spec,
                quality_gate=gate,
                sandbox=sandbox,
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
                body_kind=state.spec.body.kind,
                confidence=verdict.confidence,
                judge_version=verdict.judge_version,
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

            if _met_terminates(met=verdict.met, confidence=verdict.confidence, gate=gate):
                _broadcast_end(session_id, reason="met", detail=verdict.reason)
                ProjectSessionManager.stop_session(session_id)
                break

            # Budget guard (06 H1): accumulate judge cost and stop if a
            # configured ceiling is exceeded, so a misconfigured large
            # max_iterations × expensive model can't burn unbounded spend
            # within the wall-clock window. Checked AFTER the met-break so a
            # successful final iteration is never denied.
            state.total_cost_usd += float(verdict.cost_usd or 0.0)
            if max_cost_usd > 0 and state.total_cost_usd >= max_cost_usd:
                _broadcast_end(
                    session_id,
                    reason="budget_cap",
                    detail=f"cost ${state.total_cost_usd:.4f} reached cap ${max_cost_usd:.4f}",
                )
                ProjectSessionManager.stop_session(session_id)
                break

            # Token-budget circuit breaker (v0.6.0 unified loops): accumulate
            # tokens_in+out across iterations and stop once a configured
            # ``max_tokens`` ceiling is reached. 0/unset disables. Checked after
            # the cost-cap so both budgets are enforced last in the ladder.
            state.total_tokens += int((verdict.tokens_in or 0) + (verdict.tokens_out or 0))
            if _token_cap_exceeded(state.total_tokens, state.spec.exit.max_tokens):
                _broadcast_end(
                    session_id,
                    reason="token_cap",
                    detail=f"tokens {state.total_tokens} reached cap {state.spec.exit.max_tokens}",
                )
                ProjectSessionManager.stop_session(session_id)
                break

            # v0.7.87 — record falsified hypotheses into the
            # session's dead-end registry whenever Ouroboros is
            # on and the agent emitted a hypothesis the judge
            # could falsify. The ``UNIQUE(session_id, approach_hash)``
            # constraint keeps repeat attempts of the same approach
            # from multiplying rows.
            if ouroboros and hypothesis and verdict.ouroboros_verdict == "falsified":
                add_goal_loop_dead_end(
                    session_id=session_id,
                    iteration=iteration_no,
                    approach=hypothesis,
                    reason=verdict.reason,
                    evidence=(turn_text or "")[-1024:] or None,
                    approach_hash=_approach_hash(hypothesis),
                )

            _maybe_promote_kernel_dead_end(session_id, iteration_no, hypothesis, verdict, turn_text)

            state.not_met_streak += 1
            if not (AUTORESEARCH_KERNEL_ENABLED and metric_spec is not None):
                _maybe_stale_check(
                    session_id,
                    state,
                    check_cmd,
                    goal,
                    turn_text,
                    backend_kind,
                    model_override,
                )

            # If the operator stopped the session concurrently, don't also
            # broadcast a cap/convergence end (avoids a double end event) (06 M7).
            if state.stop_event.is_set():
                break

            if iteration_no >= max_iterations:
                _broadcast_end(
                    session_id,
                    reason="iteration_cap",
                    detail=f"reached {max_iterations} iterations",
                )
                ProjectSessionManager.stop_session(session_id)
                break

            # v0.7.87 — convergence termination runs only when
            # Ouroboros is enabled AND the iteration produced an
            # actual verdict to compare. Iterations that ran in
            # the degraded binary fallback (no hypothesis emitted)
            # have ``ouroboros_verdict=None`` and are excluded by
            # ``recent_iteration_verdicts``. So convergence only
            # fires when the agent has been consistently producing
            # hypotheses but they're stuck.
            if ouroboros and verdict.ouroboros_verdict:
                recent = recent_iteration_verdicts(session_id, limit=_OUROBOROS_CONVERGENCE_WINDOW)
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

            # Generic stagnation circuit breaker (v0.6.0 unified loops): when a
            # ``stagnation_no_progress_for`` threshold is configured, stop once
            # the loop has made no progress for that many iterations. agent_task
            # bodies (Ralph) detect progress via a new git commit landing;
            # eval_refine bodies reuse the existing not-met streak. 0 = off.
            threshold = state.spec.exit.stagnation_no_progress_for
            if threshold > 0:
                if state.spec.body.kind == "agent_task":
                    cur = loop_progress.head_commit(cwd or ".")
                    if loop_progress.made_progress(state.last_commit, cur):
                        state.no_progress_streak = 0
                    else:
                        state.no_progress_streak += 1
                    state.last_commit = cur
                    streak = state.no_progress_streak
                else:
                    streak = state.not_met_streak
                if streak >= threshold:
                    _broadcast_end(
                        session_id,
                        reason="stagnation",
                        detail=f"no progress for {threshold} iterations",
                    )
                    ProjectSessionManager.stop_session(session_id)
                    break

            _wait_if_paused(state, session_id)
            if state.stop_event.is_set():
                break

            fresh_session_id = _next_iteration(
                policy=state.spec.state.context_policy,
                session_id=session_id,
                cwd=cwd,
                goal=goal,
                reason=_apply_pending_note(state, verdict.reason),
                ouroboros=ouroboros,
                dead_ends_block=_dead_ends_context(session_id) if ouroboros else "",
                result_block=result_block,
            )
            # context_policy=reset spawned a fresh claude process (clean context
            # window). Re-point the loop's polling to the new child so subsequent
            # turn boundaries come from it, and release the old subscription. The
            # SAME _RunnerState keeps accumulating budgets/iteration counts.
            if fresh_session_id and fresh_session_id != session_id:
                new_queue = _repoint_runner_to_fresh_session(registry_key, fresh_session_id)
                if new_queue is not None:
                    ProjectSessionManager.unsubscribe_raw(session_id, queue)
                    session_id = fresh_session_id
                    queue = new_queue
    except Exception as exc:
        # The normal termination paths (met / iteration_cap / convergence /
        # operator stop) all break out of the loop and reach `finally`, never
        # here. Reaching this except means an UNHANDLED error — without an end
        # broadcast the operator is left with a "stuck" session that never
        # progresses (H5). Emit an error end and stop the session so the failure
        # is visible rather than silent.
        logger.error("goal_loop runner crashed for %s", session_id, exc_info=True)
        try:
            _broadcast_end(session_id, reason="error", detail=str(exc)[:300])
            ProjectSessionManager.stop_session(session_id)
        except Exception:
            logger.error("goal_loop: failed to emit error-end for %s", session_id, exc_info=True)
    finally:
        ProjectSessionManager.unsubscribe_raw(session_id, queue)
        _cleanup(registry_key)


def _send_continue(
    session_id: str,
    goal: str,
    reason: str,
    *,
    ouroboros: bool = True,
    dead_ends_block: str = "",
    result_block: str = "",
) -> None:
    """Write the synthetic continue prompt to claude's stdin."""
    _send_user_text(
        session_id,
        _continue_prompt(
            goal,
            reason,
            ouroboros=ouroboros,
            dead_ends_block=dead_ends_block,
            result_block=result_block,
        ),
    )


def _repoint_runner_to_fresh_session(registry_key: str, fresh_session_id: str) -> Optional["Queue"]:
    """Re-point the live ``_RunnerState`` at the freshly-spawned child process.

    The runner registry stays keyed by the ORIGINAL session_id (``registry_key``,
    so the route's ``stop_runner`` / ``stop_session`` keep working), but
    ``state.session_id`` is swapped to the fresh child so per-iteration tracking
    (iteration rows, broadcasts, stop checks) target the clean-context process.
    Returns a freshly-subscribed raw queue for the new session so the ``_run``
    loop polls the fresh process's turn boundaries; ``None`` if the runner has
    already been torn down."""
    with _runners_lock:
        state = _runners.get(registry_key)
        if state is None:
            return None
        state.session_id = fresh_session_id
    return ProjectSessionManager.subscribe_raw(fresh_session_id)


def _advance_iteration(
    *,
    session_id: str,
    cwd,
    goal: str,
    reason: str = "",
    ouroboros: bool = True,
    dead_ends_block: str = "",
    result_block: str = "",
    **_kw,
) -> Optional[str]:
    """``context_policy=reset`` advance: tear down the carried-context process and
    START A NEW claude OS process with a CLEAN context window.

    Reuses the ``_spawn_resumed_session`` recipe (``_create_fresh_loop_child`` — a
    fresh, no-PTY, stream-json ``claude`` subprocess) so the next iteration begins
    from an empty context rather than ``_send_continue``-ing into the same
    long-lived process (which would retain the full conversation history and defeat
    the reset). The fresh process is re-seeded from durable iteration history via
    ``_build_resume_context`` plus the goal prompt; the OLD process is stopped.

    Budgets/tracking continue to accumulate on the SAME ``_RunnerState`` (the
    registry key is unchanged); the runner re-points its polling to the fresh
    child via ``_repoint_runner_to_fresh_session``. Returns the new session_id so
    the caller (``_run``) can swap which queue it polls. Falls back to a continue
    prompt (returning ``None``) only when no origin row exists to spawn from."""
    from ..db.connection import get_connection

    with get_connection() as conn:
        row = conn.execute("SELECT * FROM project_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        logger.warning(
            "goal_loop: cannot reset-advance %s (session row missing); falling back to continue",
            session_id,
        )
        _send_continue(
            session_id,
            goal,
            reason,
            ouroboros=ouroboros,
            dead_ends_block=dead_ends_block,
            result_block=result_block,
        )
        return None

    origin_session = dict(row)
    resume_context = _build_resume_context(session_id)

    # Spawn a genuinely fresh process (clean context window). Provenance is
    # recorded so the new child traces back to the origin in the session graph.
    new_session_id = _create_fresh_loop_child(origin_session, cwd)
    with get_connection() as conn:
        conn.execute(
            "UPDATE project_sessions SET resumed_from = ? WHERE id = ?",
            (session_id, new_session_id),
        )
        conn.commit()

    # Stop the carried-context process — its conversation history is exactly what
    # we are discarding. (After re-pointing the runner key still maps to the same
    # state, so an external stop continues to work.)
    try:
        ProjectSessionManager.stop_session(session_id)
    except Exception:
        logger.debug("goal_loop: failed to stop origin %s during reset", session_id, exc_info=True)

    # Seed the FRESH child with accumulated knowledge + the goal — never the
    # origin process (that would write into the discarded context window).
    _send_initial(
        new_session_id,
        goal,
        ouroboros=ouroboros,
        result_block=result_block,
        resume_context=resume_context,
    )
    return new_session_id


def _next_iteration(*, policy: str, session_id: str, cwd, goal: str, **kw) -> Optional[str]:
    """Advance one iteration under the active ``context_policy``.

    ``carry`` (default) writes a synthetic continue prompt into the same
    long-lived process (byte-identical to the prior behavior). ``reset`` drops
    the carried conversation by spawning a fresh claude process and returns its
    new session_id so the caller can re-point polling. ``carry`` returns ``None``."""
    if policy == "reset":
        return _advance_iteration(session_id=session_id, cwd=cwd, goal=goal, **kw)
    _send_continue(session_id, goal=goal, **kw)
    return None


def _send_initial(
    session_id: str,
    goal: str,
    *,
    ouroboros: bool = True,
    result_block: str = "",
    resume_context: Optional[str] = None,
) -> None:
    """Write the initial kickoff prompt to claude's stdin.

    Called once per goal-loop session before the polling loop
    begins so claude has something to respond to and the first
    ``turn_done`` actually arrives.

    Phase 4 — ``resume_context`` is forwarded to ``_initial_prompt``
    so re-entry sessions are seeded with prior iteration knowledge.
    """
    _send_user_text(
        session_id,
        _initial_prompt(
            goal, ouroboros=ouroboros, result_block=result_block, resume_context=resume_context
        ),
    )


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


# ---------------------------------------------------------------------------
# Phase 4, Unit C — goal-loop re-entry from persisted iteration knowledge
# ---------------------------------------------------------------------------

# In-flight resume origins: closes the concurrent no-fan-out race (workers=1).
# The DB resumed_from check covers restarts.
_resume_lock = threading.Lock()
_resume_in_flight: set = set()


def _build_resume_context(session_id: str) -> str:
    """Re-entry context block from durable history: iteration count, verdicts,
    known dead ends. The fresh loop continues from accumulated knowledge —
    a dead PTY cannot be reattached or replayed (Phase 4, Unit C)."""
    from ..db.connection import get_connection

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT iteration, verdict, judge_reason FROM goal_loop_iterations "
            "WHERE session_id = ? ORDER BY iteration ASC",
            (session_id,),
        ).fetchall()
    last_iter = rows[-1]["iteration"] if rows else 0
    verdict_lines = [
        f"- iteration {r['iteration']}: {r['verdict'] or 'unknown'}"
        f"{(' — ' + r['judge_reason']) if r['judge_reason'] else ''}"
        for r in rows
    ]
    dead_ends = _dead_ends_context(session_id)
    parts = [
        f"RESUMING after interruption at iteration {last_iter}.",
        "Prior iteration verdicts:" if verdict_lines else "",
        *verdict_lines,
        dead_ends or "",
    ]
    return "\n".join(p for p in parts if p)


def _create_fresh_loop_child(origin_session: dict, cwd: Optional[str]) -> str:
    """Spawn a brand-new claude OS process with a CLEAN context window.

    This is the shared fresh-session recipe — a no-PTY, stream-json ``claude``
    subprocess that mirrors ``GoalLoopSessionHandler.start()``. It carries no
    conversation history from any prior process, which is exactly what both the
    resume route and ``context_policy=reset`` need: the new process starts from
    an empty context and is re-seeded from durable iteration knowledge.

    Returns the new session_id. Does NOT persist provenance, set config, or
    start a runner — callers compose those steps so the same recipe serves both
    "spawn + own runner" (resume) and "spawn + re-point existing runner" (reset).
    """
    cmd = [
        "claude",
        "--output-format",
        "stream-json",
        "--input-format",
        "stream-json",
        "-p",
        "--verbose",
    ]
    return ProjectSessionManager.create_session(
        project_id=origin_session["project_id"],
        cmd=cmd,
        cwd=cwd or ".",
        phase_id=origin_session.get("phase_id"),
        plan_id=origin_session.get("plan_id"),
        agent_id=origin_session.get("agent_id"),
        worktree_path=origin_session.get("worktree_path"),
        execution_type="goal_loop",
        execution_mode=origin_session.get("execution_mode") or "autonomous",
        stream_json=True,
        use_pty=False,
        # Preserve the origin's yolo mode: a non-yolo respawn would activate
        # the permission-hook overlay and block the unattended loop. The
        # original handler expresses yolo solely via this flag — mirror it.
        yolo_mode=bool(origin_session.get("yolo_mode")),
    )


def _spawn_resumed_session(origin_session_id: str, goal_config: dict, origin_session: dict) -> str:
    """Create and start a fresh goal-loop session seeded with the origin's config.

    Mirrors GoalLoopSessionHandler.start()'s spawn recipe. Module-level so tests
    can patch it. cwd: use origin row's worktree_path when set, else resolve via
    ProjectWorkspaceService (Phase 4, Unit C).
    """
    from ..db.connection import get_connection
    from ..db.goal_loop import set_goal_loop_config
    from .project_workspace_service import ProjectWorkspaceService

    # cwd derivation: prefer the worktree the origin ran in, fall back to project workspace
    cwd: Optional[str] = origin_session.get("worktree_path") or None
    if not cwd:
        try:
            cwd = ProjectWorkspaceService.resolve_working_directory(origin_session["project_id"])
        except Exception:
            cwd = None

    new_session_id = _create_fresh_loop_child(origin_session, cwd)

    # Persist resumed_from provenance (direct UPDATE — not in update_project_session allowlist)
    with get_connection() as conn:
        conn.execute(
            "UPDATE project_sessions SET resumed_from = ? WHERE id = ?",
            (origin_session_id, new_session_id),
        )
        conn.commit()

    set_goal_loop_config(new_session_id, goal_config)
    start_runner(new_session_id, goal_config, cwd=cwd)

    # Audit
    try:
        from .audit_log_service import AuditLogService

        AuditLogService.log(
            action="session.loop_resumed",
            entity_type="project_session",
            entity_id=new_session_id,
            outcome="spawned",
            details={"origin_session_id": origin_session_id},
        )
    except Exception:
        logger.debug("goal_loop resume audit failed for %s", new_session_id, exc_info=True)

    return new_session_id


def resume_goal_loop(session_id: str) -> dict:
    """Resume a dead goal-loop session by spawning a FRESH session seeded with
    the persisted goal config + accumulated knowledge. Eligible: execution_type
    goal_loop ONLY (ralph_loop persists no resumable state), status 'failed',
    no prior resume child."""
    from ..db.connection import get_connection
    from ..db.goal_loop import get_goal_loop_config

    with get_connection() as conn:
        row = conn.execute("SELECT * FROM project_sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return {"error": "not_found"}
        session = dict(row)
        child = conn.execute(
            "SELECT id FROM project_sessions WHERE resumed_from = ? LIMIT 1", (session_id,)
        ).fetchone()

    # goal_loop ONLY: ralph_loop persists no goal-loop config/iterations to
    # re-enter from (its ralph_config is start-only) — excluded this phase.
    if session.get("execution_type") != "goal_loop":
        return {"error": "not_eligible"}
    if session.get("status") != "failed":
        return {"error": "not_eligible"}
    if child:
        return {"error": "already_resumed"}

    config = get_goal_loop_config(session_id)
    if not config or not config.get("goal"):
        return {"error": "config_missing"}
    config["resume_context"] = _build_resume_context(session_id)

    # No-fan-out guard, claimed LAST (after every early return): create_session
    # starts the subprocess before resumed_from persists, so the DB child check
    # alone is racy for concurrent calls. Spawn is synchronous here — release
    # in finally, after which the DB provenance covers restarts. workers=1.
    with _resume_lock:
        if session_id in _resume_in_flight:
            return {"error": "already_resumed"}
        _resume_in_flight.add(session_id)
    try:
        new_session_id = _spawn_resumed_session(session_id, config, session)
    finally:
        with _resume_lock:
            _resume_in_flight.discard(session_id)
    return {"session_id": new_session_id, "resumed_from": session_id}
