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
    """Replace ProjectSessionManager._broadcast with an event recorder.

    Also records the launch-time ``policy_ask`` card, which (FIX 3) is now emitted
    via the atomic ``register_and_broadcast_policy_ask`` rather than ``_broadcast``.
    The stub records it into ``events`` AND persists the pending ask so
    ``await_decision``'s clear-on-resolve contract is intact — letting a test read
    the minted ``ask_id`` back off the recorded card."""
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
    aid = "ask-await-1"

    result = {}

    def _waiter():
        result["decision"] = PolicyService.await_decision(
            sid, verdict, ask_id=aid, max_wall_seconds=10
        )

    t = threading.Thread(target=_waiter)
    t.start()
    # Give the waiter time to register the pending entry and broadcast the card.
    time.sleep(0.3)
    ask = [e for e in events if e[1] == "policy_ask"]
    assert ask, "policy_ask card must broadcast"
    assert ask[0][2]["ask_id"] == aid, "the card carries the ask_id the decision must echo"
    assert t.is_alive(), "await_decision must still be blocking before a decision arrives"

    pending = PolicyService.submit_policy_decision(sid, "approve", ask_id=aid)
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
    aid = "ask-await-2"
    result = {}

    def _waiter():
        result["decision"] = PolicyService.await_decision(
            sid, verdict, ask_id=aid, max_wall_seconds=10
        )

    t = threading.Thread(target=_waiter)
    t.start()
    time.sleep(0.3)
    PolicyService.submit_policy_decision(sid, "deny", "operator rejected", ask_id=aid)
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
    decision = PolicyService.await_decision(
        "sess-timeout", verdict, ask_id="ask-timeout", max_wall_seconds=0
    )
    assert decision == "deny"


def test_await_decision_empty_session_fails_closed(monkeypatch):
    from app.services.policy_service import PolicyService

    _stub_broadcast(monkeypatch)
    assert PolicyService.await_decision("", {"decision": "ask"}, ask_id="ask-empty") == "deny"


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
    from app.services import execution_service as es_mod
    from app.services.policy_service import PolicyService

    events = _stub_broadcast(monkeypatch)
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
    # enforce_launch mints the ask_id internally; the decision must echo it.
    ask = [e for e in events if e[1] == "policy_ask"]
    assert ask, "a policy_ask card must be broadcast"
    PolicyService.submit_policy_decision("sess-ask-ok", "approve", ask_id=ask[0][2]["ask_id"])
    t.join(timeout=5)
    assert outcome.get("ok") is True, "approve lets the launch proceed (no raise)"


def test_ask_verdict_raises_on_deny(isolated_db, monkeypatch):
    from app.services import execution_service as es_mod
    from app.services.policy_service import PolicyDenied, PolicyService

    events = _stub_broadcast(monkeypatch)
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
    ask = [e for e in events if e[1] == "policy_ask"]
    assert ask, "a policy_ask card must be broadcast"
    PolicyService.submit_policy_decision("sess-ask-no", "deny", ask_id=ask[0][2]["ask_id"])
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


# ---------------------------------------------------------------------------
# Task 2: goal_loop exit-ladder cost budget routes THROUGH PolicyService
# ---------------------------------------------------------------------------


def test_cost_policy_implicit_ceiling_denies(isolated_db):
    """Back-compat: no policy row, but spec max_cost_usd is hit → deny (the old
    inline exit-ladder gate's behaviour, now via _evaluate_cost_policy)."""
    from app.services.goal_loop_runner import _evaluate_cost_policy

    decision, reason = _evaluate_cost_policy(
        session_id="sess-cost",
        team_id=None,
        total_cost_usd=5.0,
        tool_calls=3,
        max_cost_usd=4.0,
    )
    assert decision == "deny"
    assert "cap" in reason


def test_cost_policy_under_ceiling_allows(isolated_db):
    from app.services.goal_loop_runner import _evaluate_cost_policy

    decision, _ = _evaluate_cost_policy(
        session_id="sess-cost",
        team_id=None,
        total_cost_usd=1.0,
        tool_calls=3,
        max_cost_usd=4.0,
    )
    assert decision == "allow"


def test_cost_policy_session_row_is_source_of_truth(isolated_db):
    """An authored session-scope cost_budget DENY fires even below the implicit
    spec ceiling — PolicyService is the source of truth (consolidation)."""
    from app.services.goal_loop_runner import _evaluate_cost_policy

    _seed("session", "sess-cost-pol", "deny", kind="cost_budget", params={"max_cost_usd": 0.5})
    decision, reason = _evaluate_cost_policy(
        session_id="sess-cost-pol",
        team_id=None,
        total_cost_usd=1.0,
        tool_calls=0,
        max_cost_usd=0.0,  # no implicit ceiling
    )
    assert decision == "deny"
    assert "cost cap" in reason


def test_cost_policy_soft_threshold_asks(isolated_db):
    """A soft cost threshold yields ASK (the goal loop routes it to _await_gate)."""
    from app.services.goal_loop_runner import _evaluate_cost_policy

    _seed(
        "session", "sess-cost-ask", "ask", kind="cost_budget", params={"ask_thresholds_usd": [0.5]}
    )
    decision, _ = _evaluate_cost_policy(
        session_id="sess-cost-ask",
        team_id=None,
        total_cost_usd=0.6,
        tool_calls=0,
        max_cost_usd=0.0,
    )
    assert decision == "ask"


def test_cost_ask_cannot_exceed_hard_cap(isolated_db):
    """BLOCKER 1: a soft cost ASK must NOT let spend cross the configured
    ``max_cost_usd`` ceiling. With a soft ASK policy matched AND spend already
    over the hard cap, the hard cap wins → DENY. An ASK can pause but cannot
    raise the ceiling (the early ``return decision`` on "ask" used to skip the
    cap entirely)."""
    from app.services.goal_loop_runner import _evaluate_cost_policy

    # Soft ASK threshold at $0.5; spend $5 is over the threshold AND the $4 cap.
    _seed("session", "sess-cap", "ask", kind="cost_budget", params={"ask_thresholds_usd": [0.5]})
    decision, reason = _evaluate_cost_policy(
        session_id="sess-cap",
        team_id=None,
        total_cost_usd=5.0,
        tool_calls=0,
        max_cost_usd=4.0,
    )
    assert decision == "deny", "spend over the hard cap must deny even when a soft ASK matched"
    assert "cap" in (reason or "")


def test_cost_ask_continue_proceeds():
    """MAJOR 6: a cost ASK approved via "continue" (the human-gate card's primary
    approve) must PROCEED; only "abort"/unknown/timeout fail closed to a stop."""
    from app.services.goal_loop_runner import _cost_ask_blocks

    assert _cost_ask_blocks("continue") is False, "approve via 'continue' must proceed"
    assert _cost_ask_blocks("modify") is False
    # Fail CLOSED on everything else.
    assert _cost_ask_blocks("abort") is True
    assert _cost_ask_blocks("weird") is True
    assert _cost_ask_blocks(None) is True


# ---------------------------------------------------------------------------
# BLOCKER 4: ProjectSessionManager.create_session — the previously-ungated
# autonomous launch path — now routes through the SAME shared launch gate.
# ---------------------------------------------------------------------------


def test_denied_policy_blocks_create_session_launch(isolated_db, monkeypatch):
    """A server-scope DENY raises PolicyDenied inside create_session BEFORE any
    pty.fork / subprocess.Popen — goal_loop / ralph / team / agent / sketch all
    funnel through this method, so gating it closes the bypass."""
    from app.services import project_session_manager as psm_mod
    from app.services.policy_service import PolicyDenied

    _seed("server", None, "deny", kind="manual")

    spawned = {"n": 0}

    def _boom(*a, **k):
        spawned["n"] += 1
        raise AssertionError("no process may be spawned when policy denies the launch")

    monkeypatch.setattr(psm_mod.subprocess, "Popen", _boom)
    monkeypatch.setattr(psm_mod.os, "fork", _boom)

    with pytest.raises(PolicyDenied):
        psm_mod.ProjectSessionManager.create_session(
            project_id="proj-x",
            cmd=["echo", "hi"],
            cwd=".",
            use_pty=False,
        )
    assert spawned["n"] == 0


def test_create_session_routes_through_shared_gate(isolated_db, monkeypatch):
    """Wiring proof: create_session calls the ONE shared
    ``PolicyService.enforce_launch`` (kind=process_launch) at its launch
    boundary, forwarding cmd + backend. We raise from the spy to stop before any
    real spawn while asserting the gate ran with the right arguments — proving no
    autonomous launch can slip past the shared gate."""
    from app.services import project_session_manager as psm_mod
    from app.services.policy_service import PolicyService

    calls = {}

    def _spy(**kwargs):
        calls.update(kwargs)
        raise RuntimeError("stop-after-gate")

    monkeypatch.setattr(PolicyService, "enforce_launch", staticmethod(_spy))

    with pytest.raises(RuntimeError, match="stop-after-gate"):
        psm_mod.ProjectSessionManager.create_session(
            project_id="proj-spy",
            cmd=["claude", "-p"],
            cwd=".",
            use_pty=False,
        )
    assert calls.get("cmd") == ["claude", "-p"]
    assert calls.get("backend") == "claude"


# ---------------------------------------------------------------------------
# Launch-ASK deadlock fix: PERSIST the pending policy_ask + REPLAY it to a LATE
# SSE subscriber (the frontend subscribes only after createSession resolves),
# and make a decision that races AHEAD of the await not get lost.
# ---------------------------------------------------------------------------


def _wait_pending(session_id, timeout=3.0):
    """Block until await_decision has registered the pending ask (the deadlock
    window — the card was broadcast to zero subscribers)."""
    from app.services.project_session_manager import ProjectSessionManager

    deadline = time.time() + timeout
    while time.time() < deadline:
        if session_id in ProjectSessionManager._pending_policy_asks:
            return True
        time.sleep(0.02)
    return False


def test_launch_ask_replayed_to_late_subscriber_and_approve_proceeds(isolated_db):
    """The card is broadcast to NOBODY (frontend not yet subscribed), persisted,
    then REPLAYED to the subscriber that connects late. An approve resolves the
    blocked launch."""
    from app.services.policy_service import PolicyService
    from app.services.project_session_manager import ProjectSessionManager

    sid = "sess-replay-approve"
    aid = "ask-replay-approve"
    verdict = {
        "decision": "ask",
        "policy_id": "pol-replay",
        "kind": "ask_on_os_tools",
        "reason": "approve before launch",
        "scope": "session",
    }
    result = {}

    def _waiter():
        result["decision"] = PolicyService.await_decision(
            sid, verdict, ask_id=aid, max_wall_seconds=10
        )

    t = threading.Thread(target=_waiter)
    t.start()
    assert _wait_pending(sid), "await_decision must persist the pending ask for replay"

    # Connect LATE — after the broadcast already went out to zero subscribers.
    gen = ProjectSessionManager.subscribe(sid)
    first = next(gen)
    assert "policy_ask" in first, f"late subscriber must get the replayed card; got {first!r}"
    assert aid in first, "the replayed card carries the ask_id the decision echoes"

    PolicyService.submit_policy_decision(sid, "approve", ask_id=aid)
    t.join(timeout=5)
    assert result["decision"] == "approve", "approve lets the blocked launch proceed"
    gen.close()
    assert sid not in ProjectSessionManager._pending_policy_asks, "pending ask cleared on resolve"


def test_launch_ask_deny_blocks_launch(isolated_db):
    """A deny resolution makes the blocked launch fail closed."""
    from app.services.policy_service import PolicyService

    sid = "sess-replay-deny"
    aid = "ask-replay-deny"
    verdict = {
        "decision": "ask",
        "policy_id": "pol-replay-d",
        "kind": "ask_on_os_tools",
        "reason": "approve before launch",
        "scope": "session",
    }
    result = {}

    def _waiter():
        result["decision"] = PolicyService.await_decision(
            sid, verdict, ask_id=aid, max_wall_seconds=10
        )

    t = threading.Thread(target=_waiter)
    t.start()
    assert _wait_pending(sid)
    PolicyService.submit_policy_decision(sid, "deny", ask_id=aid)
    t.join(timeout=5)
    assert result["decision"] == "deny"


def test_decision_arriving_before_await_is_not_lost(isolated_db, monkeypatch):
    """FIX 2 (b) RACE: an operator decision submitted BEFORE the launch registers
    its waiter — for the SAME ask_id — must still resolve the await (store the
    resolution, don't clobber it to the pending sentinel). With the pre-fix code,
    await_decision overwrote the stored tuple with None and timed out → fail-closed
    deny, losing a real approve."""
    from app.services.policy_service import PolicyService

    _stub_broadcast(monkeypatch)
    sid = "sess-race-before-await"
    aid = "ask-race-before"

    # Decision arrives FIRST — no waiter registered yet — keyed by ask_id.
    pending = PolicyService.submit_policy_decision(sid, "approve", ask_id=aid)
    assert pending is False, "no waiter was registered when the decision arrived"

    # The launch now awaits the SAME ask_id: it must pick up the already-stored
    # approve, not clobber it and time out. Short max_wall makes a regression
    # (timeout→deny) observable without a long hang.
    decision = PolicyService.await_decision(
        sid, {"decision": "ask"}, ask_id=aid, max_wall_seconds=2
    )
    assert decision == "approve", "a decision racing ahead of the await must not be lost"


def test_decision_for_one_ask_does_not_approve_a_later_ask(isolated_db, monkeypatch):
    """FIX 2 (a) — the stale no-waiter auto-approve bug. A decision resolving ask A
    (stored with NO waiter) must NOT satisfy a LATER, DIFFERENT ask B on the same
    session. Pre-fix: both keyed by session_id, so B consumed A's stored approve
    and auto-approved an un-answered ask. Now each is ask_id-scoped."""
    from app.services.policy_service import PolicyService

    _stub_broadcast(monkeypatch)
    sid = "sess-scope"

    # Resolve ask A (approve) — it sits in the registry keyed by its own ask_id.
    PolicyService.submit_policy_decision(sid, "approve", ask_id="ask-A")

    # A later, DIFFERENT ask B awaits on the SAME session. It must NOT pick up A's
    # decision; with no decision of its own it times out → fail-closed DENY.
    decision = PolicyService.await_decision(
        sid, {"decision": "ask"}, ask_id="ask-B", max_wall_seconds=0
    )
    assert decision == "deny", "a decision for ask A must not auto-approve a later ask B"


# ---------------------------------------------------------------------------
# FIX 3 (MINOR): a subscriber gets the launch-time policy_ask card EXACTLY once.
# The persist (for late-subscriber replay) and the live push (for an already-
# connected subscriber) happen in ONE atomic step, so a subscriber lands in
# exactly one delivery path — never both (the old register-then-broadcast pair
# double-delivered to a subscriber connecting in the gap).
# ---------------------------------------------------------------------------


def test_policy_ask_delivered_exactly_once(isolated_db):
    from queue import Queue

    from app.services.project_session_manager import ProjectSessionManager as PSM

    sid = "sess-once"
    payload = {
        "ask_id": "ask-1",
        "policy_id": "pol-1",
        "kind": "ask_on_os_tools",
        "reason": "approve before launch",
        "scope": "session",
    }

    # An ALREADY-CONNECTED browser subscriber. In the real flow it read
    # ``pending=None`` at connect time, so it will NOT replay — it must get the
    # card solely from the live push.
    q: Queue = Queue()
    with PSM._lock:
        PSM._subscribers.setdefault(sid, []).append(q)
    try:
        PSM.register_and_broadcast_policy_ask(sid, payload)

        delivered = []
        while not q.empty():
            delivered.append(q.get_nowait())
        asks = [m for m in delivered if "event: policy_ask\n" in m]
        assert len(asks) == 1, f"connected subscriber must get exactly one policy_ask, got {asks!r}"
        assert payload["ask_id"] in asks[0]

        # And the pending card is persisted so a LATE subscriber replays it once
        # (never in addition to a live push — it was not connected for the push).
        assert PSM._pending_policy_asks.get(sid) == payload
    finally:
        with PSM._lock:
            PSM._subscribers.pop(sid, None)
            PSM._pending_policy_asks.pop(sid, None)
