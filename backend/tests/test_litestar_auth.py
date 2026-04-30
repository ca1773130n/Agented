"""Tests for the Litestar /api/auth/login route (track B, wave 32)."""

from litestar.testing import create_test_client

from app.db.users import create_user, deactivate_user, set_password
from app_litestar.auth import provide_caller
from app_litestar.main import liveness
from app_litestar.routes.auth import auth_router
from app_litestar.routes.rbac import rbac_router


def _client(isolated_db):
    return create_test_client(
        route_handlers=[liveness, rbac_router, auth_router],
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
