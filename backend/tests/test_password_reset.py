"""Tests for the forgot-password / reset-password flow (track B, wave 43)."""

import datetime as dt

from litestar.testing import create_test_client

from app.db.password_resets import consume_token, request_reset
from app.db.users import authenticate, create_user, set_password
from app_litestar.auth import provide_caller
from app_litestar.routes.auth import auth_router
from app_litestar.routes.health import health_router
from app_litestar.routes.rbac import rbac_router


def _client(_isolated_db):
    return create_test_client(
        route_handlers=[health_router, rbac_router, auth_router],
        dependencies={"caller": provide_caller},
    )


class TestRequestAndConsume:
    def test_request_returns_token(self, isolated_db):
        uid = create_user("reset@example.com")
        token = request_reset(uid)
        assert token and len(token) >= 40

    def test_consume_returns_user_id(self, isolated_db):
        uid = create_user("reset2@example.com")
        token = request_reset(uid)
        assert consume_token(token) == uid

    def test_consume_is_single_use(self, isolated_db):
        uid = create_user("reset3@example.com")
        token = request_reset(uid)
        assert consume_token(token) == uid
        assert consume_token(token) is None

    def test_consume_unknown_token(self, isolated_db):
        assert consume_token("ghost") is None

    def test_consume_expired(self, isolated_db):
        uid = create_user("reset4@example.com")
        token = request_reset(uid, lifetime=dt.timedelta(seconds=-1))
        assert consume_token(token) is None


class TestForgotPasswordEndpoint:
    def test_returns_204_for_existing_email(self, isolated_db):
        create_user("forgot@example.com")
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/api/auth/forgot-password", json={"email": "forgot@example.com"}
            )
        assert resp.status_code == 204

    def test_returns_204_for_unknown_email_no_enumeration(self, isolated_db):
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/api/auth/forgot-password", json={"email": "nobody@example.com"}
            )
        assert resp.status_code == 204


class TestResetPasswordEndpoint:
    def test_resets_password_and_old_one_no_longer_works(self, isolated_db):
        uid = create_user("rotate@example.com")
        set_password(uid, "oldpass-12345")
        assert authenticate("rotate@example.com", "oldpass-12345") is not None

        token = request_reset(uid)
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/api/auth/reset-password",
                json={"token": token, "password": "newpass-67890"},
            )
        assert resp.status_code == 204
        assert authenticate("rotate@example.com", "oldpass-12345") is None
        assert authenticate("rotate@example.com", "newpass-67890") is not None

    def test_invalid_token_returns_401(self, isolated_db):
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/api/auth/reset-password",
                json={"token": "not-real", "password": "longenough"},
            )
        assert resp.status_code == 401

    def test_short_password_returns_400(self, isolated_db):
        uid = create_user("short@example.com")
        token = request_reset(uid)
        with _client(isolated_db) as ls:
            resp = ls.post(
                "/api/auth/reset-password",
                json={"token": token, "password": "abc"},
            )
        assert resp.status_code == 400
