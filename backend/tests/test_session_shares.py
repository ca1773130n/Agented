"""Tests for live-share tokens + two-client attach (Phase 25, 25-01)."""

import threading
import time
from collections import deque
from datetime import datetime

import pytest

from app.db.session_shares import (
    list_shares_for_session,
    mint_share_token,
    resolve_share_token,
    revoke_share_token,
)
from app.services.project_session_manager import ProjectSessionManager, SessionInfo
from app.services.session_sharing_service import SessionSharingService


@pytest.fixture(autouse=True)
def _reset_psm():
    ProjectSessionManager._sessions.clear()
    ProjectSessionManager._subscribers.clear()
    yield
    ProjectSessionManager._sessions.clear()
    ProjectSessionManager._subscribers.clear()


def _active_session(session_id="psess-share1"):
    from unittest.mock import MagicMock

    now = datetime.now()
    si = SessionInfo(
        session_id=session_id,
        pid=1234,
        pgid=1234,
        master_fd=99,
        ring_buffer=deque(maxlen=10000),
        reader_thread=MagicMock(spec=threading.Thread),
        status="active",
        created_at=now,
        last_activity_at=now,
    )
    ProjectSessionManager._sessions[session_id] = si
    return si


# ---------------------------------------------------------------------------
# mint / resolve / expire / revoke round-trip (Level 1)
# ---------------------------------------------------------------------------


class TestTokenRoundTrip:
    def test_mint_resolve_returns_scope(self, isolated_db):
        token = mint_share_token("psess-abc", scope="chat", created_by="u1")
        row = resolve_share_token(token)
        assert row is not None
        assert row["session_id"] == "psess-abc"
        assert row["scope"] == "chat"
        assert row["created_by"] == "u1"

    def test_expired_token_resolves_none(self, isolated_db):
        token = mint_share_token("psess-abc", scope="read", ttl_seconds=-5)
        assert resolve_share_token(token) is None

    def test_revoked_token_resolves_none(self, isolated_db):
        token = mint_share_token("psess-abc", scope="read")
        assert resolve_share_token(token) is not None
        assert revoke_share_token(token) is True
        assert resolve_share_token(token) is None
        # A second revoke is a no-op (already revoked).
        assert revoke_share_token(token) is False

    def test_unknown_token_resolves_none(self, isolated_db):
        assert resolve_share_token("does-not-exist") is None
        assert resolve_share_token("") is None

    def test_invalid_scope_rejected(self, isolated_db):
        with pytest.raises(ValueError):
            mint_share_token("psess-abc", scope="admin")

    def test_list_returns_minted_rows(self, isolated_db):
        mint_share_token("psess-list", scope="read")
        mint_share_token("psess-list", scope="chat")
        rows = list_shares_for_session("psess-list")
        assert len(rows) == 2
        assert {r["scope"] for r in rows} == {"read", "chat"}


# ---------------------------------------------------------------------------
# can_attach — token bound to exactly one session
# ---------------------------------------------------------------------------


class TestCanAttach:
    def test_can_attach_returns_scope_for_bound_session(self, isolated_db):
        token = mint_share_token("psess-bound", scope="chat")
        assert SessionSharingService.can_attach(token, "psess-bound") == "chat"

    def test_can_attach_rejects_wrong_session(self, isolated_db):
        token = mint_share_token("psess-bound", scope="chat")
        # A token minted for one session must not attach a DIFFERENT session.
        assert SessionSharingService.can_attach(token, "psess-other") is None

    def test_can_attach_rejects_revoked(self, isolated_db):
        token = mint_share_token("psess-bound", scope="read")
        revoke_share_token(token)
        assert SessionSharingService.can_attach(token, "psess-bound") is None


# ---------------------------------------------------------------------------
# Two-client attach — a second (token) subscriber receives a broadcast delta
# over the EXISTING fan-out (Level 2 proxy, criterion 1)
# ---------------------------------------------------------------------------


class TestTwoClientAttach:
    def test_second_subscriber_receives_broadcast(self, isolated_db):
        si = _active_session("psess-live1")
        token = mint_share_token(si.session_id, scope="chat")
        # The teammate's token is bound to the live session.
        assert SessionSharingService.can_attach(token, si.session_id) == "chat"

        received: list[str] = []

        def _teammate():
            # Attach via the SAME generator the token route joins — one more Queue
            # in _subscribers, no second fan-out. Stop after the first live event.
            for event in ProjectSessionManager.subscribe(si.session_id):
                received.append(event)
                break

        t = threading.Thread(target=_teammate, daemon=True)
        t.start()

        # Wait for the teammate's queue to register before broadcasting.
        deadline = time.time() + 5
        while time.time() < deadline and not ProjectSessionManager._subscribers.get(si.session_id):
            time.sleep(0.01)
        assert ProjectSessionManager._subscribers.get(si.session_id), "subscriber never registered"

        ProjectSessionManager._broadcast(
            si.session_id, "output", {"line": "hello teammate", "timestamp": "t"}
        )
        t.join(timeout=5)

        assert any("hello teammate" in ev for ev in received), received
