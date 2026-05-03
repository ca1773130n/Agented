"""v0.5.12: session lifecycle behavior — idle, rotate, revoke."""
import datetime as dt
import pytest


def _make_user(user_id: str = "user-1") -> str:
    """Insert a users row so foreign-key on sessions.user_id is satisfied."""
    from app.database import get_connection
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, f"{user_id}@test", "x"),
        )
        conn.commit()
    return user_id


class TestRotateSession:
    def test_rotate_returns_new_token_and_preserves_old(self, isolated_db):
        from app.db.sessions import create_session, rotate_session
        _make_user("u1")
        old = create_session("u1")
        new = rotate_session(old["token"])
        assert new is not None
        assert new["token"] != old["token"]
        assert new["rotated_from_token"] == old["token"]
        assert new["id"] == old["id"]  # same row, just new token

    def test_rotate_unknown_token_returns_none(self, isolated_db):
        from app.db.sessions import rotate_session
        assert rotate_session("does-not-exist") is None

    def test_old_token_lookup_within_grace_window_succeeds(self, isolated_db):
        from app.db.sessions import (
            create_session, rotate_session, get_session_by_token,
        )
        _make_user("u1")
        old = create_session("u1")
        rotated = rotate_session(old["token"])
        # Within 5s, the OLD token should still resolve via grace window.
        found = get_session_by_token(old["token"])
        assert found is not None
        assert found["id"] == rotated["id"]

    def test_new_token_lookup_succeeds(self, isolated_db):
        from app.db.sessions import (
            create_session, rotate_session, get_session_by_token,
        )
        _make_user("u1")
        old = create_session("u1")
        new = rotate_session(old["token"])
        found = get_session_by_token(new["token"])
        assert found is not None
        assert found["id"] == new["id"]


class TestRevokeUserSessions:
    def test_revoke_user_sessions_marks_all_as_revoked(self, isolated_db):
        from app.db.sessions import create_session, revoke_user_sessions, get_session_by_token
        _make_user("u1")
        s1 = create_session("u1")
        s2 = create_session("u1")
        n = revoke_user_sessions("u1", reason="role_change")
        assert n == 2
        # Both sessions now return None on lookup.
        assert get_session_by_token(s1["token"]) is None
        assert get_session_by_token(s2["token"]) is None

    def test_revoke_user_sessions_does_not_affect_other_users(self, isolated_db):
        from app.db.sessions import create_session, revoke_user_sessions, get_session_by_token
        _make_user("u1")
        _make_user("u2")
        s1 = create_session("u1")
        s2 = create_session("u2")
        revoke_user_sessions("u1", reason="role_change")
        assert get_session_by_token(s1["token"]) is None
        assert get_session_by_token(s2["token"]) is not None

    def test_revoke_user_sessions_logs_event(self, isolated_db):
        from app.db.sessions import create_session, revoke_user_sessions
        from app.db.session_events import list_session_events
        _make_user("u1")
        s1 = create_session("u1")
        revoke_user_sessions("u1", reason="key_rotation")
        events = list_session_events(session_id=s1["id"])
        types = {e["event_type"] for e in events}
        assert "revoked" in types
        revoke_event = next(e for e in events if e["event_type"] == "revoked")
        assert revoke_event["metadata"]["reason"] == "key_rotation"


class TestIdleExpiry:
    def test_session_idle_past_threshold_returns_none(self, isolated_db):
        from app.db.sessions import create_session, get_session_by_token
        from app.database import get_connection
        _make_user("u1")
        s = create_session("u1")
        # Backdate last_used_at to >30 minutes ago.
        old = (dt.datetime.utcnow() - dt.timedelta(minutes=45)).isoformat()
        with get_connection() as conn:
            conn.execute("UPDATE sessions SET last_used_at = ? WHERE id = ?", (old, s["id"]))
            conn.commit()
        assert get_session_by_token(s["token"]) is None

    def test_idle_expiry_logs_event(self, isolated_db):
        from app.db.sessions import create_session, get_session_by_token
        from app.db.session_events import list_session_events
        from app.database import get_connection
        _make_user("u1")
        s = create_session("u1")
        old = (dt.datetime.utcnow() - dt.timedelta(minutes=45)).isoformat()
        with get_connection() as conn:
            conn.execute("UPDATE sessions SET last_used_at = ? WHERE id = ?", (old, s["id"]))
            conn.commit()
        get_session_by_token(s["token"])  # triggers idle_expired log
        events = list_session_events(session_id=s["id"])
        assert any(e["event_type"] == "idle_expired" for e in events)


class TestRevokedSessionLookup:
    def test_revoked_session_returns_none_and_logs(self, isolated_db):
        from app.db.sessions import create_session, revoke_user_sessions, get_session_by_token
        from app.db.session_events import list_session_events
        _make_user("u1")
        s = create_session("u1")
        revoke_user_sessions("u1", reason="admin")
        get_session_by_token(s["token"])  # triggers used_after_revocation log
        events = list_session_events(session_id=s["id"])
        types = [e["event_type"] for e in events]
        assert "revoked" in types
        assert "used_after_revocation" in types
