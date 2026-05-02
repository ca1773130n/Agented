"""Smoke tests for the wave 77 webhook routes."""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.webhooks import (
    github_webhook_router,
    oauth_callback_router,
    webhook_router,
)


def _client():
    return create_test_client(
        route_handlers=[github_webhook_router, oauth_callback_router, webhook_router],
        dependencies={"caller": provide_caller},
    )


def test_github_webhook_unsigned_403(isolated_db):
    with _client() as c:
        resp = c.post(
            "/api/webhooks/github/",
            json={"action": "opened", "pull_request": {}, "repository": {}},
        )
    # Without GITHUB_WEBHOOK_SECRET configured + valid signature, validation fails
    assert resp.status_code in (400, 403)


def test_oauth_callback_proxy_502_when_no_cli(isolated_db):
    with _client() as c:
        resp = c.get("/api/oauth-callback/callback?code=abc&state=xyz")
    # No CLI server running on 127.0.0.1:54545 (default port) → 502
    assert resp.status_code in (502,)


def test_generic_webhook_url_verification(isolated_db):
    with _client() as c:
        resp = c.post(
            "/",
            json={"type": "url_verification", "challenge": "test-challenge"},
        )
    assert resp.status_code == 201
    assert resp.json()["challenge"] == "test-challenge"


def test_generic_webhook_invalid_body(isolated_db):
    with _client() as c:
        resp = c.post(
            "/",
            content=b"not json",
            headers={"Content-Type": "text/plain"},
        )
    assert resp.status_code == 400
