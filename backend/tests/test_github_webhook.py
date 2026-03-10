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
        assert response.status_code == 403

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
        """Unknown event types (not pull_request or issue_comment) should be ignored."""
        payload = json.dumps({"action": "created"}).encode()
        signature = compute_signature(payload, self.SECRET)

        response = client.post(
            "/api/webhooks/github/",
            data=payload,
            content_type="application/json",
            headers={
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": signature,
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "ignored" in data["message"]


class TestPRCommentSlashCommands:
    """Tests for PR comment slash command dispatch."""

    SECRET = "test-secret"

    @pytest.fixture(autouse=True)
    def setup_webhook_secret(self, monkeypatch):
        """Set up webhook secret for all tests in this class."""
        from app.routes import github_webhook

        monkeypatch.setattr(github_webhook, "GITHUB_WEBHOOK_SECRET", self.SECRET)

    def _make_issue_comment_payload(
        self,
        comment_body: str,
        is_pr: bool = True,
        action: str = "created",
    ) -> bytes:
        payload = {
            "action": action,
            "issue": {
                "number": 42,
                "title": "Test PR",
                "html_url": "https://github.com/owner/repo/pull/42",
                "user": {"login": "testuser"},
                "pull_request": {"html_url": "https://github.com/owner/repo/pull/42"} if is_pr else None,
            },
            "comment": {
                "body": comment_body,
                "user": {"login": "reviewer"},
            },
            "repository": {
                "full_name": "owner/repo",
                "html_url": "https://github.com/owner/repo",
            },
        }
        if not is_pr:
            del payload["issue"]["pull_request"]
        return json.dumps(payload).encode()

    def _post_comment(self, client, payload: bytes, *, secret: str = SECRET):
        signature = compute_signature(payload, secret)
        return client.post(
            "/api/webhooks/github/",
            data=payload,
            content_type="application/json",
            headers={
                "X-GitHub-Event": "issue_comment",
                "X-Hub-Signature-256": signature,
            },
        )

    def test_issue_comment_on_plain_issue_ignored(self, client):
        """Comments on plain issues (not PRs) should be ignored."""
        payload = self._make_issue_comment_payload("/review", is_pr=False)
        response = self._post_comment(client, payload)
        assert response.status_code == 200
        data = response.get_json()
        assert "not PR" in data["message"] or "ignored" in data["message"]

    def test_issue_comment_deleted_action_ignored(self, client):
        """Deleted comment actions should be ignored."""
        payload = self._make_issue_comment_payload("/review", action="deleted")
        response = self._post_comment(client, payload)
        assert response.status_code == 200
        data = response.get_json()
        assert "ignored" in data["message"]

    def test_comment_without_slash_command_ignored(self, client):
        """Comments without a slash command should produce 'no slash command' response."""
        payload = self._make_issue_comment_payload("Looks good to me!")
        response = self._post_comment(client, payload)
        assert response.status_code == 200
        data = response.get_json()
        assert "no slash command" in data["message"]

    def test_slash_command_detected_and_processed(self, client, monkeypatch):
        """A PR comment with a slash command should be processed."""
        from app.services import execution_service

        dispatched = []

        def fake_dispatch(repo_url, commands, pr_data):
            dispatched.extend(commands)
            return True

        monkeypatch.setattr(
            execution_service.ExecutionService,
            "dispatch_pr_comment_commands",
            staticmethod(fake_dispatch),
        )

        payload = self._make_issue_comment_payload("/review")
        response = self._post_comment(client, payload)
        assert response.status_code == 200
        data = response.get_json()
        assert data["commands"] == ["/review"]
        assert "/review" in dispatched

    def test_multiple_slash_commands_in_one_comment(self, client, monkeypatch):
        """Multiple slash commands in a single comment body are all detected."""
        from app.services import execution_service

        dispatched = []

        def fake_dispatch(repo_url, commands, pr_data):
            dispatched.extend(commands)
            return True

        monkeypatch.setattr(
            execution_service.ExecutionService,
            "dispatch_pr_comment_commands",
            staticmethod(fake_dispatch),
        )

        body = "Please run:\n/review\n/security-scan"
        payload = self._make_issue_comment_payload(body)
        response = self._post_comment(client, payload)
        assert response.status_code == 200
        data = response.get_json()
        assert "/review" in data["commands"]
        assert "/security-scan" in data["commands"]


class TestTriggerSourceFiltering:
    """Tests for trigger source filtering."""

    def test_get_triggers_by_trigger_source(self, isolated_db):
        """get_triggers_by_trigger_source should return matching triggers."""
        from app.database import get_triggers_by_trigger_source

        # Get GitHub-triggered triggers (bot-pr-review, bot-test-coverage, bot-pr-summary)
        github_triggers = get_triggers_by_trigger_source("github")
        assert len(github_triggers) == 3
        github_ids = {t["id"] for t in github_triggers}
        assert "bot-pr-review" in github_ids
        assert "bot-test-coverage" in github_ids
        assert "bot-pr-summary" in github_ids

        # Get webhook-triggered triggers
        webhook_triggers = get_triggers_by_trigger_source("webhook")
        assert len(webhook_triggers) == 1
        assert webhook_triggers[0]["id"] == "bot-security"

    def test_add_trigger_with_trigger_source(self, isolated_db):
        """create_trigger should accept trigger_source parameter."""
        from app.database import create_trigger, get_trigger

        trigger_id = create_trigger(
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
        from app.database import create_trigger, get_trigger, update_trigger

        trigger_id = create_trigger(
            name="Test Trigger",
            prompt_template="/test",
            trigger_source="webhook",
        )

        update_trigger(trigger_id, trigger_source="scheduled")
        trigger = get_trigger(trigger_id)
        assert trigger["trigger_source"] == "scheduled"
