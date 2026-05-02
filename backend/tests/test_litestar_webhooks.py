"""Smoke tests for the wave 77 webhook routes (expanded in wave 84).

Covers the GitHub webhook surface that Codex flagged as under-tested:
ping event, valid PR payload, invalid signature, ignored events, plus
the OAuth callback proxy and generic webhook receiver.
"""

import hashlib
import hmac
import json

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.webhooks import (
    github_webhook_router,
    oauth_callback_router,
    webhook_router,
)


_TEST_SECRET = "test-secret-shhh"


def _client(monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(
            "app_litestar.routes.webhooks.GITHUB_WEBHOOK_SECRET", _TEST_SECRET
        )
    return create_test_client(
        route_handlers=[github_webhook_router, oauth_callback_router, webhook_router],
        dependencies={"caller": provide_caller},
    )


def _signed_request(payload: dict, event: str, monkeypatch):
    body = json.dumps(payload).encode()
    sig = (
        "sha256="
        + hmac.new(_TEST_SECRET.encode(), body, hashlib.sha256).hexdigest()
    )
    headers = {
        "X-Hub-Signature-256": sig,
        "X-GitHub-Event": event,
        "Content-Type": "application/json",
    }
    return body, headers


# ---------------------------------------------------------------------------
# GitHub webhook
# ---------------------------------------------------------------------------


def test_github_webhook_unsigned_403(isolated_db):
    """No GITHUB_WEBHOOK_SECRET configured → reject (matches Flask behavior)."""
    with _client() as c:
        resp = c.post(
            "/api/webhooks/github/",
            json={"action": "opened", "pull_request": {}, "repository": {}},
        )
    assert resp.status_code in (400, 403)


def test_github_webhook_invalid_signature_403(isolated_db, monkeypatch):
    """Secret configured but signature doesn't match the body → 403."""
    body = json.dumps({"action": "opened"}).encode()
    with _client(monkeypatch) as c:
        resp = c.post(
            "/api/webhooks/github/",
            content=body,
            headers={
                "X-Hub-Signature-256": "sha256=deadbeef",
                "X-GitHub-Event": "pull_request",
                "Content-Type": "application/json",
            },
        )
    assert resp.status_code == 403


def test_github_webhook_ping_returns_pong(isolated_db, monkeypatch):
    """Valid signature + ping event → pong (GitHub setup uses this)."""
    body, headers = _signed_request({"zen": "Speak like a human."}, "ping", monkeypatch)
    with _client(monkeypatch) as c:
        resp = c.post("/api/webhooks/github/", content=body, headers=headers)
    assert resp.status_code == 201
    assert resp.json() == {"message": "pong"}


def test_github_webhook_ignored_event_acknowledged(isolated_db, monkeypatch):
    """Valid signature + non-PR event → 'event ignored' message."""
    body, headers = _signed_request({"action": "released"}, "release", monkeypatch)
    with _client(monkeypatch) as c:
        resp = c.post("/api/webhooks/github/", content=body, headers=headers)
    assert resp.status_code == 201
    assert "ignored" in resp.json()["message"].lower()


def test_github_webhook_ignored_pr_action_acknowledged(isolated_db, monkeypatch):
    """Valid signature + PR with action that we ignore → message."""
    body, headers = _signed_request(
        {
            "action": "closed",
            "pull_request": {"number": 1, "html_url": "https://x/y/pull/1"},
            "repository": {"full_name": "x/y", "html_url": "https://x/y"},
        },
        "pull_request",
        monkeypatch,
    )
    with _client(monkeypatch) as c:
        resp = c.post("/api/webhooks/github/", content=body, headers=headers)
    assert resp.status_code == 201
    assert "ignored" in resp.json()["message"].lower()


def test_github_webhook_pr_opened_dispatches(isolated_db, monkeypatch):
    """Valid signature + PR opened → dispatches to ExecutionService."""
    monkeypatch.setattr(
        "app_litestar.routes.webhooks.add_pr_review",
        lambda **kw: 7,
    )
    captured: list = []

    def fake_dispatch(repo_url, pr_data):
        captured.append((repo_url, pr_data))
        return ["bot-x"]

    monkeypatch.setattr(
        "app_litestar.routes.webhooks.ExecutionService.dispatch_github_event",
        staticmethod(fake_dispatch),
    )
    body, headers = _signed_request(
        {
            "action": "opened",
            "pull_request": {
                "number": 42,
                "title": "Fix the thing",
                "html_url": "https://github.com/owner/repo/pull/42",
                "user": {"login": "alice"},
            },
            "repository": {
                "full_name": "owner/repo",
                "html_url": "https://github.com/owner/repo",
            },
        },
        "pull_request",
        monkeypatch,
    )
    with _client(monkeypatch) as c:
        resp = c.post("/api/webhooks/github/", content=body, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["review_id"] == 7
    assert body["triggered"] == ["bot-x"]
    assert captured[0][0] == "https://github.com/owner/repo"
    assert captured[0][1]["pr_number"] == 42


# ---------------------------------------------------------------------------
# OAuth callback + generic webhook (existing coverage, kept)
# ---------------------------------------------------------------------------


def test_oauth_callback_proxy_502_when_no_cli(isolated_db):
    with _client() as c:
        resp = c.get("/api/oauth-callback/callback?code=abc&state=xyz")
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
