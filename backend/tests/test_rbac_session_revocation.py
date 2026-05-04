"""v0.5.12: rbac mutations revoke the affected user's sessions."""


def _make_user(user_id: str = "u1") -> str:
    from app.database import get_connection
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, f"{user_id}@test", "x"),
        )
        conn.commit()
    return user_id


class TestRbacRevocation:
    def test_update_user_role_revokes_sessions(self, isolated_db):
        from app.db.rbac import create_user_role, update_user_role
        from app.db.sessions import create_session, get_session_by_token
        _make_user("u1")
        role_id = create_user_role("test-key-1", "t", "editor", user_id="u1")
        sess = create_session("u1")
        update_user_role(role_id, role="viewer")
        assert get_session_by_token(sess["token"]) is None

    def test_rotate_user_role_revokes_sessions(self, isolated_db):
        from app.db.rbac import create_user_role, rotate_user_role
        from app.db.sessions import create_session, get_session_by_token
        _make_user("u1")
        role_id = create_user_role("test-key-2", "t", "editor", user_id="u1")
        sess = create_session("u1")
        rotate_user_role(role_id)
        assert get_session_by_token(sess["token"]) is None

    def test_update_user_role_does_not_revoke_other_users_sessions(self, isolated_db):
        from app.db.rbac import create_user_role, update_user_role
        from app.db.sessions import create_session, get_session_by_token
        _make_user("u1")
        _make_user("u2")
        role_id1 = create_user_role("test-key-3", "r1", "editor", user_id="u1")
        sess2 = create_session("u2")
        update_user_role(role_id1, role="viewer")
        assert get_session_by_token(sess2["token"]) is not None
