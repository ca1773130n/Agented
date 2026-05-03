"""Tests for app.db.sessions (track B, wave 32)."""

import datetime as dt

from app.db.sessions import (
    create_session,
    get_session_by_token,
    purge_expired_sessions,
    revoke_session,
)
from app.db.users import create_user


class TestCreateSession:
    def test_returns_row_with_token(self, isolated_db):
        uid = create_user("sess1@example.com")
        sess = create_session(uid)
        assert sess is not None
        assert sess["user_id"] == uid
        assert isinstance(sess["token"], str)
        assert len(sess["token"]) >= 40
        assert sess["id"].startswith("sess-")

    def test_each_call_produces_a_unique_token(self, isolated_db):
        uid = create_user("sess2@example.com")
        a = create_session(uid)
        b = create_session(uid)
        assert a["token"] != b["token"]


class TestGetSessionByToken:
    def test_valid_token_returns_session(self, isolated_db):
        uid = create_user("getsess@example.com")
        sess = create_session(uid)
        found = get_session_by_token(sess["token"])
        assert found is not None
        assert found["id"] == sess["id"]

    def test_unknown_token_returns_none(self, isolated_db):
        assert get_session_by_token("not-a-real-token") is None

    def test_empty_token_returns_none(self, isolated_db):
        assert get_session_by_token("") is None

    def test_expired_session_returns_none(self, isolated_db):
        uid = create_user("expired@example.com")
        sess = create_session(uid, lifetime=dt.timedelta(seconds=-1))
        assert get_session_by_token(sess["token"]) is None


class TestRevokeSession:
    def test_revoke_soft_deletes_session(self, isolated_db):
        """revoke_session now soft-deletes (sets revoked_at) instead of hard DELETE."""
        from app.database import get_connection
        uid = create_user("revoke@example.com")
        sess = create_session(uid)
        assert revoke_session(sess["token"]) is True
        # Token lookup returns None (revoked).
        assert get_session_by_token(sess["token"]) is None
        # Row still exists with revoked_at set (soft-delete, not hard DELETE).
        with get_connection() as conn:
            row = conn.execute(
                "SELECT revoked_at FROM sessions WHERE id = ?", (sess["id"],)
            ).fetchone()
        assert row is not None
        assert row[0] is not None  # revoked_at populated

    def test_revoke_unknown_returns_false(self, isolated_db):
        assert revoke_session("ghost") is False

    def test_revoke_empty_returns_false(self, isolated_db):
        assert revoke_session("") is False


class TestPurgeExpired:
    def test_removes_expired_sessions(self, isolated_db):
        uid = create_user("purge@example.com")
        live = create_session(uid)
        dead = create_session(uid, lifetime=dt.timedelta(seconds=-1))

        removed = purge_expired_sessions()
        assert removed >= 1
        assert get_session_by_token(live["token"]) is not None
        assert get_session_by_token(dead["token"]) is None
