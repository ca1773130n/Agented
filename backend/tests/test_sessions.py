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

    def test_v061_soft_delete_preserves_row_for_audit(self, isolated_db):
        """v0.6.1: expire_sessions soft-deletes (sets revoked_at) rather
        than hard-deleting, so the session_events audit log can still
        reference the row and operators can see expiry history."""
        from app.database import get_connection
        from app.db.sessions import expire_sessions

        uid = create_user("expire@example.com")
        dead = create_session(uid, lifetime=dt.timedelta(seconds=-1))
        n = expire_sessions()
        assert n >= 1
        # Lookup returns None (revoked) but the row still exists.
        assert get_session_by_token(dead["token"]) is None
        with get_connection() as conn:
            row = conn.execute(
                "SELECT revoked_at, revoke_reason FROM sessions WHERE id = ?",
                (dead["id"],),
            ).fetchone()
        assert row is not None
        assert row[0] is not None  # revoked_at populated
        assert row[1] == "expired"  # reason set

    def test_v061_alias_to_purge_expired_sessions(self, isolated_db):
        """The old name still resolves for backwards compat."""
        from app.db.sessions import expire_sessions, purge_expired_sessions

        assert expire_sessions is purge_expired_sessions
