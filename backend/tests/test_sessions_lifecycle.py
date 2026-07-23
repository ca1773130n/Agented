"""v0.5.12: session lifecycle behavior — idle, rotate, revoke."""

import datetime as dt


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
            create_session,
            get_session_by_token,
            rotate_session,
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
            create_session,
            get_session_by_token,
            rotate_session,
        )

        _make_user("u1")
        old = create_session("u1")
        new = rotate_session(old["token"])
        found = get_session_by_token(new["token"])
        assert found is not None
        assert found["id"] == new["id"]


class TestRevokeUserSessions:
    def test_revoke_user_sessions_marks_all_as_revoked(self, isolated_db):
        from app.db.sessions import create_session, get_session_by_token, revoke_user_sessions

        _make_user("u1")
        s1 = create_session("u1")
        s2 = create_session("u1")
        n = revoke_user_sessions("u1", reason="role_change")
        assert n == 2
        # Both sessions now return None on lookup.
        assert get_session_by_token(s1["token"]) is None
        assert get_session_by_token(s2["token"]) is None

    def test_revoke_user_sessions_does_not_affect_other_users(self, isolated_db):
        from app.db.sessions import create_session, get_session_by_token, revoke_user_sessions

        _make_user("u1")
        _make_user("u2")
        s1 = create_session("u1")
        s2 = create_session("u2")
        revoke_user_sessions("u1", reason="role_change")
        assert get_session_by_token(s1["token"]) is None
        assert get_session_by_token(s2["token"]) is not None

    def test_revoke_user_sessions_logs_event(self, isolated_db):
        from app.db.session_events import list_session_events
        from app.db.sessions import create_session, revoke_user_sessions

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
        from app.database import get_connection
        from app.db.sessions import create_session, get_session_by_token

        _make_user("u1")
        s = create_session("u1")
        # Backdate last_used_at to >30 minutes ago.
        old = (dt.datetime.utcnow() - dt.timedelta(minutes=45)).isoformat()
        with get_connection() as conn:
            conn.execute("UPDATE sessions SET last_used_at = ? WHERE id = ?", (old, s["id"]))
            conn.commit()
        assert get_session_by_token(s["token"]) is None

    def test_idle_expiry_logs_event(self, isolated_db):
        from app.database import get_connection
        from app.db.session_events import list_session_events
        from app.db.sessions import create_session, get_session_by_token

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
        from app.db.session_events import list_session_events
        from app.db.sessions import create_session, get_session_by_token, revoke_user_sessions

        _make_user("u1")
        s = create_session("u1")
        revoke_user_sessions("u1", reason="admin")
        get_session_by_token(s["token"])  # triggers used_after_revocation log
        events = list_session_events(session_id=s["id"])
        types = [e["event_type"] for e in events]
        assert "revoked" in types
        assert "used_after_revocation" in types


class TestGraceWindowReplayDefense:
    def test_old_token_replay_does_not_extend_grace_window(self, isolated_db):
        """Codex round-3: rotation grace window must NOT slide forward
        on each replay of the old token. Anchor must be rotated_at,
        which is set only by rotate_session, never by per-request touch.
        """
        import datetime as dt

        from app.database import get_connection
        from app.db.sessions import (
            create_session,
            get_session_by_token,
            rotate_session,
        )

        _make_user("u1")
        s = create_session("u1")
        old = s["token"]
        rotate_session(old)

        # Backdate rotated_at past the grace window. last_used_at is freshly
        # NOW because rotate_session also touched it. Pre-fix code checked
        # last_used_at > grace_cutoff → still in window. Post-fix
        # checks rotated_at > grace_cutoff → out of window.
        from app.db.sessions import ROTATION_GRACE_WINDOW

        past = (dt.datetime.utcnow() - ROTATION_GRACE_WINDOW - dt.timedelta(seconds=5)).isoformat()
        with get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET rotated_at = ? WHERE id = ?",
                (past, s["id"]),
            )
            conn.commit()

        # Replay with the OLD token must now miss.
        assert get_session_by_token(old) is None


class TestRotateOldTokenReturnsNone:
    def test_rotate_already_rotated_token_returns_none(self, isolated_db):
        """After rotation, the old token no longer matches any active
        session row. Sequential second-rotate of the original token
        returns None — the proper concurrent CAS path (loser reloads +
        returns winner row) only triggers when two connections see the
        same row before either commits, which is not testable here."""
        from app.db.sessions import create_session, rotate_session

        _make_user("u1")
        s = create_session("u1")
        old = s["token"]
        first = rotate_session(old)
        assert first is not None
        assert rotate_session(old) is None


class TestRotationThrottle:
    def test_recently_rotated_session_is_not_rerotated(self, isolated_db):
        """Rotation is throttled: a session rotated moments ago must not
        rotate again (per-request rotation only multiplied DB writes and
        cookie-desync races during page-load request bursts)."""
        from app.db.sessions import create_session, rotate_session

        _make_user("u1")
        s = create_session("u1")
        first = rotate_session(s["token"])
        assert first is not None
        assert rotate_session(first["token"]) is None

    def test_rotation_resumes_after_min_interval(self, isolated_db):
        import datetime as dt

        from app.database import get_connection
        from app.db.sessions import ROTATION_MIN_INTERVAL, create_session, rotate_session

        _make_user("u1")
        s = create_session("u1")
        first = rotate_session(s["token"])
        stale = (dt.datetime.utcnow() - ROTATION_MIN_INTERVAL - dt.timedelta(seconds=5)).isoformat()
        with get_connection() as conn:
            conn.execute("UPDATE sessions SET rotated_at = ? WHERE id = ?", (stale, s["id"]))
            conn.commit()
        second = rotate_session(first["token"])
        assert second is not None
        assert second["token"] != first["token"]


class TestGraceTokenResync:
    def test_middleware_resyncs_grace_token_cookie_to_current(self, isolated_db):
        """A browser still holding the PREVIOUS token (it missed the rotation
        response — out-of-order Set-Cookie during a page-load burst) must be
        RESYNCED to the current token, not re-rotated: without the resync it
        is silently logged out when the grace window closes."""
        from litestar import get
        from litestar.testing import create_test_client

        from app.db.rbac import create_user_role
        from app.db.sessions import create_session, rotate_session
        from app_litestar.cookie_auth import SESSION_COOKIE
        from app_litestar.middleware import ApiKeyMiddleware

        _make_user("u1")
        create_user_role("k-resync", label="t", role="admin", user_id="u1")
        s = create_session("u1")
        rotated = rotate_session(s["token"])
        assert rotated is not None

        @get("/api/ping", sync_to_thread=False)
        def ping() -> dict:
            return {"ok": True}

        with create_test_client(route_handlers=[ping], middleware=[ApiKeyMiddleware()]) as c:
            # Present the STALE (grace) token as the session cookie.
            resp = c.get("/api/ping", cookies={SESSION_COOKIE: s["token"]})
            assert resp.status_code == 200
            # The response must hand the browser the CURRENT token back.
            assert resp.cookies.get(SESSION_COOKIE) == rotated["token"]
