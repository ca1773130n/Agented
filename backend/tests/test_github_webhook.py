"""Tests for GitHub webhook handling."""

import hashlib
import hmac
import json

import pytest


def compute_signature(payload: bytes, secret: str) -> str:
    """Compute GitHub-style HMAC-SHA256 signature."""
    signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={signature}"


class TestGitHubWebhookSignature:
    """Tests for signature verification."""

    def test_ping_event(self, client, monkeypatch):
        """GitHub ping event should return pong."""
        secret = "test-secret"
        from app.routes import github_webhook

        monkeypatch.setattr(github_webhook, "GITHUB_WEBHOOK_SECRET", secret)

        payload = json.dumps({"zen": "test"}).encode()
        signature = compute_signature(payload, secret)

        response = client.post(
            "/api/webhooks/github/",
            data=payload,
            content_type="application/json",
            headers={
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": signature,
            },
        )
        assert response.status_code == 200
        assert response.get_json()["message"] == "pong"

    def test_invalid_signature_rejected(self, client, monkeypatch):
        """Request with invalid signature should be rejected."""
        # Patch the module-level constant directly
        from app.routes import github_webhook

        monkeypatch.setattr(github_webhook, "GITHUB_WEBHOOK_SECRET", "test-secret")

        payload = json.dumps({"action": "opened"}).encode()
        response = client.post(
            "/api/webhooks/github/",
            data=payload,
            content_type="application/json",
            headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": "sha256=invalid"},
        )
        assert response.status_code == 401

    def test_valid_signature_accepted(self, client, monkeypatch):
        """Request with valid signature should be accepted."""
        secret = "test-secret"
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)

        # Need to reload the module to pick up the env var
        from app.routes import github_webhook

        monkeypatch.setattr(github_webhook, "GITHUB_WEBHOOK_SECRET", secret)

        payload = json.dumps(
            {
                "action": "opened",
                "pull_request": {
                    "number": 1,
                    "title": "Test PR",
                    "html_url": "https://github.com/owner/repo/pull/1",
                    "user": {"login": "testuser"},
                },
                "repository": {
                    "full_name": "owner/repo",
                    "html_url": "https://github.com/owner/repo",
                },
            }
        ).encode()

        signature = compute_signature(payload, secret)

        response = client.post(
            "/api/webhooks/github/",
            data=payload,
            content_type="application/json",
            headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": signature},
        )
        assert response.status_code == 200


class TestGitHubWebhookPREvents:
    """Tests for PR event handling."""

    SECRET = "test-secret"

    @pytest.fixture(autouse=True)
    def setup_webhook_secret(self, monkeypatch):
        """Set up webhook secret for all tests in this class."""
        from app.routes import github_webhook

        monkeypatch.setattr(github_webhook, "GITHUB_WEBHOOK_SECRET", self.SECRET)

    def test_pr_opened_creates_review_record(self, client):
        """PR opened event should create a review record."""
        payload = json.dumps(
            {
                "action": "opened",
                "pull_request": {
                    "number": 123,
                    "title": "Add new feature",
                    "html_url": "https://github.com/owner/repo/pull/123",
                    "user": {"login": "developer"},
                },
                "repository": {
                    "full_name": "owner/repo",
                    "html_url": "https://github.com/owner/repo",
                },
            }
        ).encode()
        signature = compute_signature(payload, self.SECRET)

        response = client.post(
            "/api/webhooks/github/",
            data=payload,
            content_type="application/json",
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["message"] == "PR event processed"
        assert data["review_id"] is not None

    def test_pr_synchronize_creates_review_record(self, client):
        """PR synchronize event should create a review record."""
        payload = json.dumps(
            {
                "action": "synchronize",
                "pull_request": {
                    "number": 456,
                    "title": "Update feature",
                    "html_url": "https://github.com/owner/repo/pull/456",
                    "user": {"login": "developer"},
                },
                "repository": {
                    "full_name": "owner/repo",
                    "html_url": "https://github.com/owner/repo",
                },
            }
        ).encode()
        signature = compute_signature(payload, self.SECRET)

        response = client.post(
            "/api/webhooks/github/",
            data=payload,
            content_type="application/json",
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["review_id"] is not None

    def test_pr_closed_ignored(self, client):
        """PR closed event should be ignored."""
        payload = json.dumps(
            {
                "action": "closed",
                "pull_request": {
                    "number": 789,
                    "title": "Old PR",
                    "html_url": "https://github.com/owner/repo/pull/789",
                    "user": {"login": "developer"},
                },
                "repository": {
                    "full_name": "owner/repo",
                    "html_url": "https://github.com/owner/repo",
                },
            }
        ).encode()
        signature = compute_signature(payload, self.SECRET)

        response = client.post(
            "/api/webhooks/github/",
            data=payload,
            content_type="application/json",
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "ignored" in data["message"]

    def test_non_pr_event_ignored(self, client):
        """Non-PR events should be ignored."""
        payload = json.dumps({"action": "created"}).encode()
        signature = compute_signature(payload, self.SECRET)

        response = client.post(
            "/api/webhooks/github/",
            data=payload,
            content_type="application/json",
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-Hub-Signature-256": signature,
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "ignored" in data["message"]


class TestTriggerSourceFiltering:
    """Tests for trigger source filtering."""

    def test_get_triggers_by_trigger_source(self, isolated_db):
        """get_triggers_by_trigger_source should return matching triggers."""
        from app.database import get_triggers_by_trigger_source

        # Get GitHub-triggered triggers
        github_triggers = get_triggers_by_trigger_source("github")
        assert len(github_triggers) == 1
        assert github_triggers[0]["id"] == "bot-pr-review"

        # Get webhook-triggered triggers
        webhook_triggers = get_triggers_by_trigger_source("webhook")
        assert len(webhook_triggers) == 1
        assert webhook_triggers[0]["id"] == "bot-security"

    def test_add_trigger_with_trigger_source(self, isolated_db):
        """add_trigger should accept trigger_source parameter."""
        from app.database import add_trigger, get_trigger

        trigger_id = add_trigger(
            name="Manual Trigger",
            prompt_template="/test",
            backend_type="claude",
            trigger_source="manual",
        )

        assert trigger_id is not None
        trigger = get_trigger(trigger_id)
        assert trigger["trigger_source"] == "manual"

    def test_update_trigger_trigger_source(self, isolated_db):
        """update_trigger should update trigger_source."""
        from app.database import add_trigger, get_trigger, update_trigger

        trigger_id = add_trigger(
            name="Test Trigger",
            prompt_template="/test",
            trigger_source="webhook",
        )

        update_trigger(trigger_id, trigger_source="scheduled")
        trigger = get_trigger(trigger_id)
        assert trigger["trigger_source"] == "scheduled"
