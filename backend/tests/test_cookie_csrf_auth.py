"""Cookie session + double-submit CSRF migration tests."""

from litestar import get, post
from litestar.testing import create_test_client

from app_litestar.cookie_auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    csrf_valid,
)


def _make_user(email="cookie@test", password="hunter2hunter2"):
    from app.db.users import create_user, set_password

    uid = create_user(email, "Cookie User")
    set_password(uid, password)
    # Give them a role so bootstrap doesn't apply.
    from app.db.rbac import create_user_role, generate_api_key

    create_user_role(generate_api_key(), label="t", role="admin", user_id=uid)
    return email, password


@get("/api/probe", sync_to_thread=False)
def probe() -> dict:
    return {"ok": True}


@post("/api/probe", sync_to_thread=False)
def probe_write() -> dict:
    return {"written": True}


def _client():
    from app_litestar.middleware import ApiKeyMiddleware
    from app_litestar.routes.auth import auth_router

    return create_test_client(
        route_handlers=[auth_router, probe, probe_write],
        middleware=[ApiKeyMiddleware()],
    )


# --- unit: csrf_valid ---------------------------------------------------------
def test_csrf_valid_safe_method_always_passes():
    assert csrf_valid("GET", {}, None) is True


def test_csrf_valid_requires_matching_header():
    cookies = {CSRF_COOKIE: "abc"}
    assert csrf_valid("POST", cookies, "abc") is True
    assert csrf_valid("POST", cookies, "wrong") is False
    assert csrf_valid("POST", cookies, None) is False
    assert csrf_valid("POST", {}, "abc") is False


# --- integration: full cookie flow -------------------------------------------
def test_login_sets_session_and_csrf_cookies(isolated_db):
    email, password = _make_user()
    with _client() as c:
        resp = c.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code in (200, 201)
    assert SESSION_COOKIE in resp.cookies
    assert CSRF_COOKIE in resp.cookies
    assert resp.json().get("csrf_token")  # echoed in body for the SPA


def test_cookie_auth_get_works_without_csrf(isolated_db):
    email, password = _make_user()
    with _client() as c:
        c.post("/api/auth/login", json={"email": email, "password": password})
        # Session cookie is in the jar; GET needs no CSRF.
        r = c.get("/api/probe")
    assert r.status_code == 200


def test_cookie_mutation_without_csrf_is_forbidden(isolated_db):
    email, password = _make_user()
    with _client() as c:
        c.post("/api/auth/login", json={"email": email, "password": password})
        # POST with the session cookie but NO X-CSRF-Token header → 403.
        r = c.post("/api/probe", headers={"x-csrf-token": ""})
    assert r.status_code == 403


def test_cookie_mutation_with_matching_csrf_passes(isolated_db):
    email, password = _make_user()
    with _client() as c:
        login = c.post("/api/auth/login", json={"email": email, "password": password})
        csrf = login.json()["csrf_token"]
        r = c.post("/api/probe", headers={"x-csrf-token": csrf})
    assert r.status_code in (200, 201)


def test_logout_clears_cookies(isolated_db):
    email, password = _make_user()
    with _client() as c:
        login = c.post("/api/auth/login", json={"email": email, "password": password})
        csrf = login.json()["csrf_token"]
        r = c.post("/api/auth/logout", headers={"x-csrf-token": csrf})
    assert r.status_code == 204
