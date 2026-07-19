"""Reproduction: signup then login with the same credentials must succeed."""

from litestar.testing import create_test_client

from app_litestar.routes.auth import auth_router


def _client():
    return create_test_client(route_handlers=[auth_router])


def test_signup_then_login_same_credentials(isolated_db):
    with _client() as c:
        r = c.post(
            "/api/auth/signup",
            json={"email": "op@example.com", "password": "hunter2secret", "display_name": "Op"},
        )
        assert r.status_code in (200, 201), r.text

        r = c.post(
            "/api/auth/login",
            json={"email": "op@example.com", "password": "hunter2secret"},
        )
        assert r.status_code in (200, 201), r.text
        assert r.json()["user"]["email"] == "op@example.com"


def test_login_tolerates_email_case_and_whitespace(isolated_db):
    with _client() as c:
        c.post(
            "/api/auth/signup",
            json={"email": "Case@Example.com", "password": "hunter2secret"},
        )
        r = c.post(
            "/api/auth/login",
            json={"email": "  case@example.com ", "password": "hunter2secret"},
        )
        assert r.status_code in (200, 201), r.text
