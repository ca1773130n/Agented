"""Policy END-TO-END tests (23-06 / 23-05 Task 3, SC5).

Drives a real session through the two enforcement boundaries the governance
substrate hangs on — proving the operator-visible behaviour end to end:

  - DENY: a configured deny BLOCKS the action (PolicyDenied raised at the
    ExecutionService Popen boundary BEFORE subprocess.Popen is reached).
  - ASK : a configured ask PAUSES the launching call (broadcasting a ``policy_ask``
    card over the EXISTING SSE primitive), then RESUMES on operator approve and
    ABORTS on deny.
  - ALLOW: no matching deny/ask policy → the action PASSES THROUGH unchanged.

Both real enforcement points are exercised:
  - ``ExecutionService._enforce_launch_policy`` (action.kind == process_launch)
  - ``goal_loop_runner._evaluate_cost_policy`` (the exit-ladder cost/tool gate)

Unlike test_policy_enforcement.py (Level 2 unit), this asserts the full
ALLOW/DENY/ASK matrix AND the ``policy_ask`` event payload contract the frontend
PolicyAskCard consumes (policy_id / kind / reason / scope).
"""

from __future__ import annotations

import threading
import time

import pytest


def _seed(scope, scope_id, effect, *, kind="custom", priority=0, params=None):
    from app.services.policy_service import PolicyService

    return PolicyService.create_policy(
        scope=scope,
        scope_id=scope_id,
        kind=kind,
        effect=effect,
        priority=priority,
        params=params,
    )


def _stub_broadcast(monkeypatch):
    """Replace ProjectSessionManager._broadcast with an event recorder.

    Also records the launch-time ``policy_ask`` card, which (FIX 3) is now emitted
    via the atomic ``register_and_broadcast_policy_ask`` rather than ``_broadcast``,
    and persists the pending ask so ``await_decision``'s clear-on-resolve contract
    is intact (a test can read the minted ``ask_id`` back off the recorded card)."""
    from app.services.project_session_manager import ProjectSessionManager

    events = []

    def _rec(cls, session_id, event_type, data):
        events.append((session_id, event_type, data))

    def _rec_ask(cls, session_id, payload):
        cls._pending_policy_asks[session_id] = payload
        events.append((session_id, "policy_ask", payload))

    monkeypatch.setattr(ProjectSessionManager, "_broadcast", classmethod(_rec))
    monkeypatch.setattr(
        ProjectSessionManager, "register_and_broadcast_policy_ask", classmethod(_rec_ask)
    )
    return events


# ---------------------------------------------------------------------------
# ALLOW — passes through the launch boundary
# ---------------------------------------------------------------------------


def test_allow_passes_through(isolated_db, monkeypatch):
    """No matching deny/ask policy → enforce returns cleanly (caller proceeds to
    Popen). subprocess.Popen would be reachable — enforce never blocks it."""
    from app.services import execution_service as es_mod

    popen_calls = {"n": 0}
    monkeypatch.setattr(
        es_mod.subprocess,
        "Popen",
        lambda *a, **k: popen_calls.__setitem__("n", popen_calls["n"] + 1),
    )

    # No raise == ALLOW passed through.
    es_mod.ExecutionService._enforce_launch_policy(
        session_id="sess-e2e-allow",
        team_id=None,
        cmd=["echo", "hi"],
        backend="claude",
    )


# ---------------------------------------------------------------------------
# DENY — blocks the action before Popen
# ---------------------------------------------------------------------------


def test_deny_blocks_action(isolated_db, monkeypatch):
    """A configured session-scope DENY blocks the action: PolicyDenied is raised
    and subprocess.Popen is NEVER reached."""
    from app.services import execution_service as es_mod
    from app.services.policy_service import PolicyDenied

    _seed("session", "sess-e2e-deny", "deny", kind="custom")

    def _fail_popen(*a, **k):
        raise AssertionError("Popen must NOT be called when the action is DENIED")

    monkeypatch.setattr(es_mod.subprocess, "Popen", _fail_popen)

    with pytest.raises(PolicyDenied):
        es_mod.ExecutionService._enforce_launch_policy(
            session_id="sess-e2e-deny",
            team_id=None,
            cmd=["rm", "-rf", "/"],
            backend="claude",
        )


# ---------------------------------------------------------------------------
# ASK — pauses for an approval card, then resumes / aborts
# ---------------------------------------------------------------------------


def test_ask_pauses_then_resumes_on_approve(isolated_db, monkeypatch):
    """An ASK pauses the launching call until the operator approves, broadcasting
    a policy_ask card; approve lets the launch proceed."""
    from app.services import execution_service as es_mod
    from app.services.policy_service import PolicyService

    events = _stub_broadcast(monkeypatch)
    _seed("session", "sess-e2e-ask-ok", "ask", kind="ask_on_os_tools")

    outcome = {}

    def _runner():
        try:
            es_mod.ExecutionService._enforce_launch_policy(
                session_id="sess-e2e-ask-ok",
                team_id=None,
                cmd=["bash", "-c", "echo hi"],
                backend="claude",
            )
            outcome["ok"] = True
        except Exception as exc:  # noqa: BLE001
            outcome["err"] = exc

    t = threading.Thread(target=_runner)
    t.start()
    time.sleep(0.3)
    assert t.is_alive(), "the ASK must PAUSE the launching call until resolved"

    # The approval card was broadcast over the existing SSE primitive, carrying
    # the exact payload the frontend PolicyAskCard renders.
    ask_events = [e for e in events if e[1] == "policy_ask"]
    assert ask_events, "a policy_ask card must be broadcast"
    _, _, payload = ask_events[0]
    assert set(payload) >= {"ask_id", "policy_id", "kind", "reason", "scope"}
    assert payload["kind"] == "ask_on_os_tools"
    assert payload["scope"] == "session"
    assert payload["ask_id"], "the card must carry the unique ask_id the decision echoes"

    # The decision must echo the card's ask_id (FIX 2 — ask-scoped).
    PolicyService.submit_policy_decision("sess-e2e-ask-ok", "approve", ask_id=payload["ask_id"])
    t.join(timeout=5)
    assert outcome.get("ok") is True, "approve must let the launch proceed"

    resolved = [e for e in events if e[1] == "policy_ask_resolved"]
    assert resolved and resolved[-1][2]["decision"] == "approve"


def test_ask_aborts_on_deny(isolated_db, monkeypatch):
    """Operator deny on an ASK aborts the action (PolicyDenied)."""
    from app.services import execution_service as es_mod
    from app.services.policy_service import PolicyDenied, PolicyService

    events = _stub_broadcast(monkeypatch)
    _seed("session", "sess-e2e-ask-no", "ask", kind="ask_on_os_tools")

    outcome = {}

    def _runner():
        try:
            es_mod.ExecutionService._enforce_launch_policy(
                session_id="sess-e2e-ask-no",
                team_id=None,
                cmd=["bash", "-c", "echo hi"],
                backend="claude",
            )
        except PolicyDenied as exc:
            outcome["denied"] = exc

    t = threading.Thread(target=_runner)
    t.start()
    time.sleep(0.3)
    assert t.is_alive()
    ask_events = [e for e in events if e[1] == "policy_ask"]
    assert ask_events, "a policy_ask card must be broadcast"
    ask_id = ask_events[0][2]["ask_id"]
    PolicyService.submit_policy_decision("sess-e2e-ask-no", "deny", ask_id=ask_id)
    t.join(timeout=5)
    assert "denied" in outcome, "operator deny must raise PolicyDenied"

    resolved = [e for e in events if e[1] == "policy_ask_resolved"]
    assert resolved and resolved[-1][2]["decision"] == "deny"


# ---------------------------------------------------------------------------
# Exit-ladder cost boundary (goal_loop) — the second enforcement point
# ---------------------------------------------------------------------------


def test_cost_budget_deny_via_goal_loop(isolated_db):
    """A session-scope cost_budget hard cap DENIES the iteration through the real
    goal-loop exit-ladder gate."""
    from app.services.goal_loop_runner import _evaluate_cost_policy

    _seed("session", "sess-e2e-cost", "deny", kind="cost_budget", params={"max_cost_usd": 0.5})
    decision, reason = _evaluate_cost_policy(
        session_id="sess-e2e-cost",
        team_id=None,
        total_cost_usd=1.0,
        tool_calls=0,
        max_cost_usd=0.0,
    )
    assert decision == "deny"
    assert reason


def test_cost_budget_ask_via_goal_loop(isolated_db):
    """A soft cost threshold yields ASK through the goal-loop exit-ladder gate."""
    from app.services.goal_loop_runner import _evaluate_cost_policy

    _seed(
        "session",
        "sess-e2e-cost-ask",
        "ask",
        kind="cost_budget",
        params={"ask_thresholds_usd": [0.5]},
    )
    decision, _ = _evaluate_cost_policy(
        session_id="sess-e2e-cost-ask",
        team_id=None,
        total_cost_usd=0.6,
        tool_calls=0,
        max_cost_usd=0.0,
    )
    assert decision == "ask"


def test_allow_via_goal_loop_no_policy(isolated_db):
    """No policy + under the implicit ceiling → ALLOW through the exit ladder."""
    from app.services.goal_loop_runner import _evaluate_cost_policy

    decision, _ = _evaluate_cost_policy(
        session_id="sess-e2e-cost-allow",
        team_id=None,
        total_cost_usd=0.1,
        tool_calls=0,
        max_cost_usd=4.0,
    )
    assert decision == "allow"
