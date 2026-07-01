"""Co-drive policy gate (Phase 25, 25-02).

A chat-scope teammate's message must be evaluated by the Phase-23 policy engine
BEFORE it reaches the operator's session stdin:
  * DENY  → PolicyDenied, send_input NEVER called,
  * ASK   → pending ask created, blocks until resolved (approve → proceed; deny
            → PolicyDenied),
  * ALLOW → send_input called once with the teammate's text,
  * read-scope token → CoDriveScopeError before any policy/IO.
"""

import threading
import time

import pytest

from app.db.session_shares import mint_share_token
from app.services.policy_service import PolicyDenied, PolicyService
from app.services.project_session_manager import ProjectSessionManager
from app.services.session_sharing_service import CoDriveScopeError, SessionSharingService

SID = "psess-codrive"


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    ProjectSessionManager._sessions.clear()
    ProjectSessionManager._subscribers.clear()
    ProjectSessionManager._pending_policy_asks.clear()
    # Reset the ask-decision registry so a prior test's tuple can't leak.
    import app.services.policy_service as ps

    ps._POLICY_DECISIONS.clear()
    yield
    ProjectSessionManager._sessions.clear()
    ProjectSessionManager._subscribers.clear()
    ProjectSessionManager._pending_policy_asks.clear()
    ps._POLICY_DECISIONS.clear()


def _spy_send_input(monkeypatch):
    calls = []

    def _fake(session_id, text):
        calls.append((session_id, text))
        return True

    monkeypatch.setattr(ProjectSessionManager, "send_input", staticmethod(_fake))
    return calls


def test_read_token_rejected_before_policy(isolated_db, monkeypatch):
    calls = _spy_send_input(monkeypatch)
    token = mint_share_token(SID, scope="read")
    with pytest.raises(CoDriveScopeError):
        SessionSharingService.co_drive(SID, token, "do X", actor_user_id="teammate")
    assert calls == []  # never reached send_input


def test_deny_blocks_send_input(isolated_db, monkeypatch):
    calls = _spy_send_input(monkeypatch)
    token = mint_share_token(SID, scope="chat")
    PolicyService.create_policy(
        scope="session", scope_id=SID, kind="co_drive", effect="deny", enabled=1
    )
    with pytest.raises(PolicyDenied):
        SessionSharingService.co_drive(SID, token, "rm -rf", actor_user_id="teammate")
    assert calls == []  # DENY → send_input NEVER called


def test_allow_proceeds(isolated_db, monkeypatch):
    calls = _spy_send_input(monkeypatch)
    token = mint_share_token(SID, scope="chat")
    # No policy authored → default ALLOW.
    ok = SessionSharingService.co_drive(SID, token, "hello", actor_user_id="teammate")
    assert ok is True
    assert calls == [(SID, "hello")]


def test_ask_blocks_then_resolves(isolated_db, monkeypatch):
    calls = _spy_send_input(monkeypatch)
    token = mint_share_token(SID, scope="chat")
    PolicyService.create_policy(
        scope="session", scope_id=SID, kind="co_drive", effect="ask", enabled=1
    )

    result: dict = {}

    def _drive():
        try:
            result["ok"] = SessionSharingService.co_drive(
                SID, token, "approved cmd", actor_user_id="teammate", max_wall_seconds=10
            )
        except Exception as exc:  # noqa: BLE001
            result["exc"] = exc

    t = threading.Thread(target=_drive, daemon=True)
    t.start()

    # Wait for the ASK card to register, then approve it by its ask_id.
    deadline = time.time() + 5
    while time.time() < deadline and SID not in ProjectSessionManager._pending_policy_asks:
        time.sleep(0.02)
    pending = ProjectSessionManager._pending_policy_asks.get(SID)
    assert pending is not None, "ASK never created a pending card"
    # While blocked on the ASK, send_input must NOT have run yet.
    assert calls == []
    PolicyService.submit_policy_decision(SID, "approve", ask_id=pending["ask_id"])

    t.join(timeout=8)
    assert result.get("ok") is True
    assert calls == [(SID, "approved cmd")]


def test_ask_denied_raises(isolated_db, monkeypatch):
    calls = _spy_send_input(monkeypatch)
    token = mint_share_token(SID, scope="chat")
    PolicyService.create_policy(
        scope="session", scope_id=SID, kind="co_drive", effect="ask", enabled=1
    )

    result: dict = {}

    def _drive():
        try:
            SessionSharingService.co_drive(
                SID, token, "bad cmd", actor_user_id="teammate", max_wall_seconds=10
            )
        except Exception as exc:  # noqa: BLE001
            result["exc"] = exc

    t = threading.Thread(target=_drive, daemon=True)
    t.start()
    deadline = time.time() + 5
    while time.time() < deadline and SID not in ProjectSessionManager._pending_policy_asks:
        time.sleep(0.02)
    pending = ProjectSessionManager._pending_policy_asks.get(SID)
    assert pending is not None
    PolicyService.submit_policy_decision(SID, "deny", ask_id=pending["ask_id"])

    t.join(timeout=8)
    assert isinstance(result.get("exc"), PolicyDenied)
    assert calls == []  # a denied ASK never reaches send_input
