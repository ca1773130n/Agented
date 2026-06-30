"""Policy ENFORCEMENT tests (23-03, SC3) — the integration core.

Proves the two enforcement invariants the governance substrate hangs on:

  1. await_decision (Task 1): an ASK verdict blocks the launching call until
     ``submit_policy_decision`` resolves it; an unresolved ASK times out and
     FAILS CLOSED to "deny" (governance fail-safe, distinct from the goal-gate's
     "abort"). The ASK card is broadcast over the EXISTING SSE primitive
     (ProjectSessionManager._broadcast), not a new transport.

  2. ExecutionService Popen boundary (Task 2): a DENY verdict raises PolicyDenied
     and subprocess.Popen is NEVER called (asserted via a mock); an ASK blocks
     then proceeds to Popen on "approve" and raises on "deny".

These are Level 2 (Proxy) tests: Popen and the SSE broadcast are mocked; the real
session pipeline e2e lands in 23-05.
"""

import threading
import time

import pytest


# ---------------------------------------------------------------------------
# Task 1: await_decision / submit_policy_decision round-trip
# ---------------------------------------------------------------------------


def _stub_broadcast(monkeypatch):
    """Replace ProjectSessionManager._broadcast with an event recorder."""
    from app.services.project_session_manager import ProjectSessionManager

    events = []

    def _rec(cls, session_id, event_type, data):
        events.append((session_id, event_type, data))

    monkeypatch.setattr(ProjectSessionManager, "_broadcast", classmethod(_rec))
    return events


def test_await_decision_blocks_until_submit_resolves(monkeypatch):
    from app.services.policy_service import PolicyService

    events = _stub_broadcast(monkeypatch)
    verdict = {
        "decision": "ask",
        "policy_id": "pol-x",
        "kind": "ask_on_os_tools",
        "reason": "approve before shell",
        "scope": "session",
    }
    sid = "sess-await-1"

    result = {}

    def _waiter():
        result["decision"] = PolicyService.await_decision(sid, verdict, max_wall_seconds=10)

    t = threading.Thread(target=_waiter)
    t.start()
    # Give the waiter time to register the pending entry and broadcast the card.
    time.sleep(0.3)
    assert any(e[1] == "policy_ask" for e in events), "policy_ask card must broadcast"
    assert t.is_alive(), "await_decision must still be blocking before a decision arrives"

    pending = PolicyService.submit_policy_decision(sid, "approve")
    assert pending is True, "a wait was pending"
    t.join(timeout=5)
    assert not t.is_alive(), "await_decision must return once a decision is submitted"
    assert result["decision"] == "approve"
    assert any(e[1] == "policy_ask_resolved" for e in events)


def test_await_decision_deny_round_trip(monkeypatch):
    from app.services.policy_service import PolicyService

    _stub_broadcast(monkeypatch)
    verdict = {
        "decision": "ask",
        "policy_id": "pol-y",
        "kind": "cost_budget",
        "reason": "soft cap",
        "scope": "session",
    }
    sid = "sess-await-2"
    result = {}

    def _waiter():
        result["decision"] = PolicyService.await_decision(sid, verdict, max_wall_seconds=10)

    t = threading.Thread(target=_waiter)
    t.start()
    time.sleep(0.3)
    PolicyService.submit_policy_decision(sid, "deny", "operator rejected")
    t.join(timeout=5)
    assert result["decision"] == "deny"


def test_await_decision_timeout_defaults_to_deny(monkeypatch):
    """Governance fail-safe: an unresolved ASK times out → DENY (fail closed)."""
    from app.services.policy_service import PolicyService

    _stub_broadcast(monkeypatch)
    verdict = {
        "decision": "ask",
        "policy_id": "pol-z",
        "kind": "ask_on_os_tools",
        "reason": "noone home",
        "scope": "session",
    }
    # max_wall_seconds=0 → the first poll check trips the timeout immediately.
    decision = PolicyService.await_decision("sess-timeout", verdict, max_wall_seconds=0)
    assert decision == "deny"


def test_await_decision_empty_session_fails_closed(monkeypatch):
    from app.services.policy_service import PolicyService

    _stub_broadcast(monkeypatch)
    assert PolicyService.await_decision("", {"decision": "ask"}) == "deny"


# ---------------------------------------------------------------------------
# Task 2: ExecutionService Popen boundary enforcement
# ---------------------------------------------------------------------------


def _seed(scope, scope_id, effect, *, kind="manual", priority=0, params=None):
    from app.services.policy_service import PolicyService

    return PolicyService.create_policy(
        scope=scope,
        scope_id=scope_id,
        kind=kind,
        effect=effect,
        priority=priority,
        params=params,
    )


def test_deny_verdict_prevents_popen(isolated_db, monkeypatch):
    """A DENY verdict raises PolicyDenied and subprocess.Popen is NEVER called."""
    from app.services import execution_service as es_mod
    from app.services.policy_service import PolicyDenied

    # Seed a server-scope DENY that any process_launch will hit.
    _seed("server", None, "deny", kind="manual")

    popen_called = {"n": 0}

    def _fake_popen(*a, **k):
        popen_called["n"] += 1
        raise AssertionError("Popen must NOT be called on a DENY verdict")

    monkeypatch.setattr(es_mod.subprocess, "Popen", _fake_popen)

    with pytest.raises(PolicyDenied):
        es_mod.ExecutionService._enforce_launch_policy(
            session_id="sess-deny",
            team_id=None,
            cmd=["echo", "hi"],
            backend="claude",
        )
    assert popen_called["n"] == 0


def test_ask_verdict_blocks_then_proceeds_on_approve(isolated_db, monkeypatch):
    """An ASK verdict blocks the launch boundary until approved, then returns
    (allowing the caller to proceed to Popen)."""
    from app.services.policy_service import PolicyService
    from app.services import execution_service as es_mod

    _stub_broadcast(monkeypatch)
    # ask_on_os_tools → process_launch yields an ASK verdict.
    _seed("session", "sess-ask-ok", "ask", kind="ask_on_os_tools")

    outcome = {}

    def _runner():
        try:
            es_mod.ExecutionService._enforce_launch_policy(
                session_id="sess-ask-ok",
                team_id=None,
                cmd=["echo", "hi"],
                backend="claude",
            )
            outcome["ok"] = True
        except Exception as e:  # noqa: BLE001
            outcome["err"] = e

    t = threading.Thread(target=_runner)
    t.start()
    time.sleep(0.3)
    assert t.is_alive(), "enforce must block while ASK is unresolved"
    PolicyService.submit_policy_decision("sess-ask-ok", "approve")
    t.join(timeout=5)
    assert outcome.get("ok") is True, "approve lets the launch proceed (no raise)"


def test_ask_verdict_raises_on_deny(isolated_db, monkeypatch):
    from app.services.policy_service import PolicyService, PolicyDenied
    from app.services import execution_service as es_mod

    _stub_broadcast(monkeypatch)
    _seed("session", "sess-ask-no", "ask", kind="ask_on_os_tools")

    outcome = {}

    def _runner():
        try:
            es_mod.ExecutionService._enforce_launch_policy(
                session_id="sess-ask-no",
                team_id=None,
                cmd=["echo", "hi"],
                backend="claude",
            )
        except PolicyDenied as e:
            outcome["denied"] = e

    t = threading.Thread(target=_runner)
    t.start()
    time.sleep(0.3)
    PolicyService.submit_policy_decision("sess-ask-no", "deny")
    t.join(timeout=5)
    assert "denied" in outcome, "operator deny must raise PolicyDenied"


def test_allow_verdict_returns_cleanly(isolated_db, monkeypatch):
    """No matching policy → default ALLOW → enforce returns without raising."""
    from app.services import execution_service as es_mod

    es_mod.ExecutionService._enforce_launch_policy(
        session_id="sess-allow",
        team_id=None,
        cmd=["echo", "hi"],
        backend="claude",
    )
