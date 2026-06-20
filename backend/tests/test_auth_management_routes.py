"""v0.5.12: auth-management routes — logout, admin revoke, session events read."""


def _setup_user_with_role(role: str, email: str = "u@test"):
    """Returns (user_id, api_key, session_token)."""
    from app.database import get_connection
    from app.db.rbac import create_user_role, generate_api_key
    from app.db.sessions import create_session

    user_id = email
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, password_hash, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, email, "x"),
        )
        conn.commit()
    api_key = generate_api_key()
    role_id = create_user_role(api_key, label="t", role=role, user_id=user_id)
    assert role_id is not None
    sess = create_session(user_id)
    return user_id, api_key, sess["token"]


def _client():
    from litestar.testing import create_test_client

    from app_litestar.middleware import ApiKeyMiddleware
    from app_litestar.routes.auth_management import auth_management_router

    return create_test_client(
        route_handlers=[auth_management_router],
        middleware=[ApiKeyMiddleware()],
    )


class TestLogout:
    def test_logout_revokes_caller_sessions(self, isolated_db):
        from app.db.sessions import get_session_by_token

        _, _, token = _setup_user_with_role("viewer")
        with _client() as c:
            resp = c.post(
                "/admin/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        # After logout, the original bearer token is revoked (note middleware
        # rotated it, but revoke-by-user clears all the caller's sessions).
        assert get_session_by_token(token) is None


class TestAdminRevoke:
    def test_admin_can_revoke_target_user_sessions(self, isolated_db):
        from app.db.sessions import create_session, get_session_by_token

        target_user, _, _ = _setup_user_with_role("editor", email="t@test")
        target_session = create_session(target_user)
        _, admin_key, _ = _setup_user_with_role("admin", email="a@test")
        with _client() as c:
            resp = c.post(
                f"/admin/users/{target_user}/sessions/revoke",
                headers={"X-API-Key": admin_key},
            )
        assert resp.status_code in (200, 201)
        assert get_session_by_token(target_session["token"]) is None

    def test_non_admin_cannot_revoke(self, isolated_db):
        target_user, _, _ = _setup_user_with_role("editor", email="t@test")
        _, viewer_key, _ = _setup_user_with_role("viewer", email="v@test")
        with _client() as c:
            resp = c.post(
                f"/admin/users/{target_user}/sessions/revoke",
                headers={"X-API-Key": viewer_key},
            )
        assert resp.status_code == 403


class TestSessionEventsRead:
    def test_admin_can_list_session_events(self, isolated_db):
        from app.db.session_events import log_session_event

        log_session_event("sess-1", "user-1", "created")
        _, admin_key, _ = _setup_user_with_role("admin", email="a@test")
        with _client() as c:
            resp = c.get(
                "/admin/auth/session-events",
                headers={"X-API-Key": admin_key},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "events" in body
        assert any(e["session_id"] == "sess-1" for e in body["events"])

    def test_non_admin_cannot_list_session_events(self, isolated_db):
        _, viewer_key, _ = _setup_user_with_role("viewer")
        with _client() as c:
            resp = c.get(
                "/admin/auth/session-events",
                headers={"X-API-Key": viewer_key},
            )
        assert resp.status_code == 403
