"""Smoke tests for the wave 80/81 middleware stack."""

import os

from litestar import Litestar, get
from litestar.config.cors import CORSConfig
from litestar.testing import create_test_client

from app_litestar.exception_handlers import EXCEPTION_HANDLERS
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
        route_handlers=[echo_handler, liveness_handler],
        middleware=[
            mw.SecurityHeadersMiddleware(),
            mw.RateLimitMiddleware(),
            mw.RequestContextMiddleware(),
            mw.ApiKeyMiddleware(),
            mw.RequestLoggingMiddleware(),
        ],
        exception_handlers=EXCEPTION_HANDLERS,
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
