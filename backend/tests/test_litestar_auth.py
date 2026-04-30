"""Tests for the Litestar /api/auth/login route (track B, wave 32)."""

from litestar.testing import create_test_client

from app.db.users import create_user, deactivate_user, set_password
from app_litestar.auth import provide_caller
from app_litestar.routes.auth import auth_router
from app_litestar.routes.health import health_router
from app_litestar.routes.rbac import rbac_router


def _client(isolated_db):
    return create_test_client(
        route_handlers=[health_router, rbac_router, auth_router],
        dependencies={"caller": provide_caller},
    )


class TestLogin:
    def test_returns_token_for_valid_credentials(self, isolated_db):
        uid = create_user("login@example.com", "Login")
        set_password(uid, "right-password")
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/api/auth/login",
                json={"email": "login@example.com", "password": "right-password"},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert isinstance(body["token"], str) and len(body["token"]) >= 40
        assert body["user"]["id"] == uid
        assert body["user"]["email"] == "login@example.com"
        assert "password_hash" not in body["user"]

    def test_wrong_password_returns_401(self, isolated_db):
        uid = create_user("wrong@example.com")
        set_password(uid, "real")
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/api/auth/login",
                json={"email": "wrong@example.com", "password": "fake"},
            )
        assert resp.status_code == 401

    def test_unknown_email_returns_401(self, isolated_db):
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/api/auth/login",
                json={"email": "ghost@example.com", "password": "anything"},
            )
        assert resp.status_code == 401

    def test_inactive_user_returns_401(self, isolated_db):
        uid = create_user("inactive@example.com")
        set_password(uid, "right")
        deactivate_user(uid)
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/api/auth/login",
                json={"email": "inactive@example.com", "password": "right"},
            )
        assert resp.status_code == 401

    def test_user_with_no_password_returns_401(self, isolated_db):
        # legacy@local has no password set; can't be hijacked.
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/api/auth/login",
                json={"email": "legacy@local", "password": ""},
            )
        assert resp.status_code == 401

    def test_email_normalized_for_lookup(self, isolated_db):
        uid = create_user("Mixed@Case.COM", "Mixed")
        set_password(uid, "x")
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/api/auth/login",
                json={"email": "MIXED@case.com", "password": "x"},
            )
        assert resp.status_code == 201

    def test_token_authenticates_protected_route(self, isolated_db):
        """Wave 33 — /api/auth/me accepts session-token bearer auth."""
        from app.db.rbac import create_user_role
        # Need at least one role row so we're past bootstrap mode.
        create_user_role("gate-key", "Gate", "admin")

        uid = create_user("bearer@example.com", "Bearer")
        set_password(uid, "x")
        with _client(isolated_db) as ls:
            login_resp = ls.post(
                "/api/auth/login",
                json={"email": "bearer@example.com", "password": "x"},
            )
            token = login_resp.json()["token"]
            me_resp = ls.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert me_resp.status_code == 200
        body = me_resp.json()
        assert body["id"] == uid
        assert body["email"] == "bearer@example.com"
        assert body["auth_method"] == "session"

    def test_me_with_api_key_returns_user(self, isolated_db):
        from app.db.rbac import create_user_role
        uid = create_user("apikey-me@example.com", "ApiKey")
        create_user_role("ak-me-key", "Lbl", "admin", user_id=uid)
        with _client(isolated_db) as ls:
            resp = ls.get(
                "/api/auth/me",
                headers={"X-API-Key": "ak-me-key"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == uid
        assert body["auth_method"] == "api_key"

    def test_me_unauthenticated_returns_401(self, isolated_db):
        from app.db.rbac import create_user_role
        create_user_role("gate-2", "Gate", "admin")  # past bootstrap
        with _client(isolated_db) as ls:
            resp = ls.get("/api/auth/me")
        assert resp.status_code == 401

    def test_logout_revokes_session(self, isolated_db):
        from app.db.rbac import create_user_role
        from app.db.sessions import get_session_by_token
        create_user_role("gate-3", "Gate", "admin")

        uid = create_user("logout@example.com")
        set_password(uid, "x")
        with _client(isolated_db) as ls:
            login_resp = ls.post(
                "/api/auth/login",
                json={"email": "logout@example.com", "password": "x"},
            )
            token = login_resp.json()["token"]
            assert get_session_by_token(token) is not None

            logout_resp = ls.post(
                "/api/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert logout_resp.status_code == 204
        assert get_session_by_token(token) is None

    def test_logout_without_token_still_204(self, isolated_db):
        with _client(isolated_db) as ls:
            resp = ls.post("/api/auth/logout")
        assert resp.status_code == 204

    def test_garbage_authorization_header_falls_through_to_api_key(self, isolated_db):
        from app.db.rbac import create_user_role
        create_user_role("ak-fall", "Lbl", "admin")
        with _client(isolated_db) as ls:
            # Malformed header — wrong scheme, non-bearer.
            resp = ls.get(
                "/api/auth/me",
                headers={
                    "Authorization": "Basic dXNlcjpwYXNz",
                    "X-API-Key": "ak-fall",
                },
            )
        assert resp.status_code == 200

    def test_session_caller_inherits_admin_role(self, isolated_db):
        """Wave 36 — a logged-in user who owns an admin api_key can hit
        admin-only routes via just the session bearer."""
        uid = create_user("admin-user@example.com", "AdminUser")
        set_password(uid, "x")
        # Associate an admin role row with this user.
        from app.db.rbac import create_user_role
        create_user_role("ignored-key", "Owned by admin user", "admin", user_id=uid)
        with _client(isolated_db) as ls:
            login_resp = ls.post(
                "/api/auth/login",
                json={"email": "admin-user@example.com", "password": "x"},
            )
            token = login_resp.json()["token"]
            resp = ls.get(
                "/admin/rbac/roles",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200, resp.text

    def test_session_caller_without_admin_role_blocked(self, isolated_db):
        """Inverse — a logged-in user who only owns viewer rows is 403'd
        from admin endpoints."""
        from app.db.rbac import create_user_role
        uid = create_user("viewer-user@example.com", "ViewerUser")
        set_password(uid, "x")
        create_user_role("vw-only-key", "Viewer only", "viewer", user_id=uid)
        with _client(isolated_db) as ls:
            login_resp = ls.post(
                "/api/auth/login",
                json={"email": "viewer-user@example.com", "password": "x"},
            )
            token = login_resp.json()["token"]
            resp = ls.get(
                "/admin/rbac/roles",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 403

    def test_token_authenticates_subsequent_session_lookup(self, isolated_db):
        from app.db.sessions import get_session_by_token
        uid = create_user("session@example.com")
        set_password(uid, "x")
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/api/auth/login",
                json={"email": "session@example.com", "password": "x"},
            )
        token = resp.json()["token"]
        sess = get_session_by_token(token)
        assert sess is not None
        assert sess["user_id"] == uid
