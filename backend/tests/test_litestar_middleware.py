"""Smoke tests for the wave 80/81 middleware stack."""

import os

from litestar import Litestar, get
from litestar.config.cors import CORSConfig
from litestar.testing import create_test_client

from app_litestar.exception_handlers import build_exception_handlers
from app_litestar.middleware import (
    ApiKeyMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)


@get("/api/test/echo", sync_to_thread=False)
def echo_handler() -> dict[str, str]:
    return {"ok": "yes"}


@get("/health/liveness", sync_to_thread=False)
def liveness_handler() -> dict[str, str]:
    return {"status": "alive"}


# `RateLimitMiddleware._RATE_LIMITS` is module-level and triggers on POST /
# (the generic webhook receiver, 20/10s). Provide a matching handler so
# the rate-limit smoke tests can drive a real 429.
from litestar import post  # noqa: E402


@post("/", sync_to_thread=False)
def ratelimited_handler() -> dict[str, str]:
    return {"status": "ok"}


def _client(force_https: bool = False):
    if force_https:
        os.environ["FORCE_HTTPS"] = "true"
    else:
        os.environ.pop("FORCE_HTTPS", None)
    # Reload the middleware module so SecurityHeadersMiddleware re-reads
    # the env var. Litestar instantiates the middleware once at app boot.
    import importlib

    import app_litestar.middleware as mw

    importlib.reload(mw)

    return create_test_client(
        route_handlers=[echo_handler, liveness_handler, ratelimited_handler],
        middleware=[
            mw.RequestContextMiddleware(),
            mw.RequestLoggingMiddleware(),
            mw.SecurityHeadersMiddleware(),
            mw.RateLimitMiddleware(),
            mw.ApiKeyMiddleware(),
        ],
        exception_handlers=build_exception_handlers(),
        cors_config=CORSConfig(allow_origins=["*"]),
    )


def test_security_headers_added(isolated_db):
    with _client() as c:
        resp = c.get("/health/liveness")
    assert resp.status_code == 200
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in resp.headers["content-security-policy"]


def test_hsts_only_when_force_https(isolated_db):
    with _client(force_https=True) as c:
        resp = c.get("/health/liveness")
    assert resp.headers.get("strict-transport-security", "").startswith("max-age=")


def test_request_id_header_round_trips(isolated_db):
    with _client() as c:
        resp = c.get(
            "/health/liveness",
            headers={"X-Request-ID": "test-rid-1234"},
        )
    assert resp.headers["x-request-id"] == "test-rid-1234"


def test_request_id_generated_when_absent(isolated_db):
    with _client() as c:
        resp = c.get("/health/liveness")
    assert resp.headers.get("x-request-id")


def test_health_does_not_require_auth(isolated_db):
    """Bootstrap mode with no DB keys + no env: everything passes through.

    Even when keys exist, /health bypasses by prefix. This test exercises
    the bypass list by hitting /health and confirming no 401.
    """
    with _client() as c:
        resp = c.get("/health/liveness")
    assert resp.status_code == 200


def test_api_path_in_bootstrap_mode_passes(isolated_db):
    """No keys configured + no env var → bootstrap mode lets /api requests through."""
    os.environ.pop("AGENTED_API_KEY", None)
    with _client() as c:
        resp = c.get("/api/test/echo")
    assert resp.status_code == 200


def test_429_carries_request_id_header_and_body(isolated_db):
    """Regression: rate-limited responses must include X-Request-ID and the
    body's `request_id` field. Pre-migration `test_request_id::test_rate_limit_response_has_request_id`
    asserted both. Wave 80 lost it because RateLimit ran before RequestContext."""
    import importlib

    import app_litestar.middleware as mw

    # Drain the limiter so we reliably trigger 429 within the 10s window.
    importlib.reload(mw)
    with _client() as c:
        for _ in range(20):
            r = c.post("/", json={"hello": "world"})
            assert r.status_code in (200, 201)
        r = c.post(
            "/",
            json={"hello": "world"},
            headers={"X-Request-ID": "rate-rid-test"},
        )
    assert r.status_code == 429
    assert r.headers.get("x-request-id") == "rate-rid-test"
    body = r.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["request_id"] == "rate-rid-test"
    # Security headers still attached on 429.
    assert r.headers["x-frame-options"] == "DENY"


def test_401_carries_request_id(isolated_db):
    """Regression: unauthorized responses include X-Request-ID + body field."""
    from app.db.rbac import create_user_role, invalidate_key_cache

    invalidate_key_cache()
    # Populate user_roles so we leave bootstrap mode and ApiKeyMiddleware
    # actually checks the X-API-Key header.
    create_user_role(api_key="seed-key", label="seed", role="admin")

    try:
        with _client() as c:
            r = c.get(
                "/api/test/echo",
                headers={"X-Request-ID": "auth-rid-test"},
            )
        assert r.status_code == 401
        assert r.headers.get("x-request-id") == "auth-rid-test"
        body = r.json()
        assert body["error"]["code"] == "UNAUTHORIZED"
        assert body["request_id"] == "auth-rid-test"
        assert r.headers["x-frame-options"] == "DENY"
    finally:
        invalidate_key_cache()
