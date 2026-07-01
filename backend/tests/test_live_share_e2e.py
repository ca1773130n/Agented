"""Two-client live-share end-to-end + policy-checked co-drive (Phase 25, 25-05).

Criterion #5, in ONE test: client A runs a session and mints a CHAT share token;
client B attaches via the SAME subscribe() fan-out and receives a broadcast delta
(read-only); then a co-drive message from B is policy-checked BEFORE it runs —
under a seeded DENY it does NOT reach send_input, under ALLOW it does.
"""

import threading
import time
from collections import deque
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.db.session_shares import mint_share_token
from app.services.policy_service import PolicyDenied, PolicyService
from app.services.project_session_manager import ProjectSessionManager, SessionInfo
from app.services.session_sharing_service import SessionSharingService

SID = "psess-e2e1"


@pytest.fixture(autouse=True)
def _reset():
    ProjectSessionManager._sessions.clear()
    ProjectSessionManager._subscribers.clear()
    ProjectSessionManager._pending_policy_asks.clear()
    yield
    ProjectSessionManager._sessions.clear()
    ProjectSessionManager._subscribers.clear()
    ProjectSessionManager._pending_policy_asks.clear()


def _active_session(session_id=SID):
    now = datetime.now()
    si = SessionInfo(
        session_id=session_id,
        pid=1,
        pgid=1,
        master_fd=99,
        ring_buffer=deque(maxlen=10000),
        reader_thread=MagicMock(spec=threading.Thread),
        status="active",
        created_at=now,
        last_activity_at=now,
    )
    ProjectSessionManager._sessions[session_id] = si
    return si


def test_two_client_live_share_co_drive_policy_checked(isolated_db, monkeypatch):
    # -- Client A: run a session, mint a CHAT share token ---------------------
    _active_session(SID)
    token = mint_share_token(SID, scope="chat", created_by="operator")
    assert SessionSharingService.can_attach(token, SID) == "chat"

    # -- Client B (read): attach over the EXISTING fan-out, receive a delta ---
    received: list[str] = []

    def _teammate():
        for event in ProjectSessionManager.subscribe(SID):
            received.append(event)
            break

    t = threading.Thread(target=_teammate, daemon=True)
    t.start()
    deadline = time.time() + 5
    while time.time() < deadline and not ProjectSessionManager._subscribers.get(SID):
        time.sleep(0.01)
    ProjectSessionManager._broadcast(SID, "output", {"line": "operator output", "timestamp": "t"})
    t.join(timeout=5)
    assert any("operator output" in ev for ev in received), received

    # -- Co-drive is policy-checked BEFORE it runs ---------------------------
    calls: list[tuple] = []
    monkeypatch.setattr(
        ProjectSessionManager,
        "send_input",
        staticmethod(lambda session_id, text: calls.append((session_id, text)) or True),
    )

    # DENY: the co-drive message must NOT reach send_input.
    policy = PolicyService.create_policy(
        scope="session", scope_id=SID, kind="co_drive", effect="deny", enabled=1
    )
    with pytest.raises(PolicyDenied):
        SessionSharingService.co_drive(SID, token, "rm -rf /", actor_user_id="teammate")
    assert calls == []  # blocked before stdin

    # ALLOW: remove the deny → the next co-drive reaches send_input.
    PolicyService.delete_policy(policy["id"])
    ok = SessionSharingService.co_drive(SID, token, "safe cmd", actor_user_id="teammate")
    assert ok is True
    assert calls == [(SID, "safe cmd")]
