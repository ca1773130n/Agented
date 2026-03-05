"""Tests for Slack slash command endpoint.

Covers signature verification, command parsing, and async execution dispatch.
All external API calls are mocked.
"""

import hashlib
import hmac
import time
from unittest.mock import patch
from urllib.parse import urlencode

from app.routes.integrations import _parse_run_command
from app.services.integrations.slack_adapter import SlackAdapter

# =============================================================================
# Signature verification tests
# =============================================================================


class TestSlackSignatureVerification:
    """Test Slack HMAC-SHA256 request signature verification."""

    SIGNING_SECRET = "test_signing_secret_abc123"

    def _make_signature(self, timestamp: str, body: str) -> str:
        """Compute a valid Slack signature for test data."""
        sig_basestring = f"v0:{timestamp}:{body}"
        computed = hmac.new(
            self.SIGNING_SECRET.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"v0={computed}"

    def test_valid_signature_passes(self):
        """A correctly computed HMAC-SHA256 signature is accepted."""
        ts = str(int(time.time()))
        body = "command=/agented&text=run+security-audit+on+payments"
        sig = self._make_signature(ts, body)

        assert SlackAdapter.verify_slack_signature(self.SIGNING_SECRET, ts, body, sig) is True

    def test_invalid_signature_rejected(self):
        """A wrong signature is rejected."""
        ts = str(int(time.time()))
        body = "command=/agented&text=test"

        assert (
            SlackAdapter.verify_slack_signature(self.SIGNING_SECRET, ts, body, "v0=bad_signature")
            is False
        )

    def test_expired_timestamp_rejected(self):
        """A timestamp older than 5 minutes is rejected (replay protection)."""
        old_ts = str(int(time.time()) - 600)  # 10 minutes ago
        body = "command=/agented&text=test"
        sig = self._make_signature(old_ts, body)

        assert SlackAdapter.verify_slack_signature(self.SIGNING_SECRET, old_ts, body, sig) is False

    def test_invalid_timestamp_format(self):
        """Non-numeric timestamp is rejected."""
        assert (
            SlackAdapter.verify_slack_signature(
                self.SIGNING_SECRET, "not-a-number", "body", "v0=sig"
            )
            is False
        )

    def test_empty_timestamp_rejected(self):
        """Empty timestamp is rejected."""
        assert (
            SlackAdapter.verify_slack_signature(self.SIGNING_SECRET, "", "body", "v0=sig") is False
        )


# =============================================================================
# Command parsing tests
# =============================================================================


class TestCommandParsing:
    """Test slash command text parsing."""

    def test_valid_run_command(self):
        """Parse 'run security-audit on payments-service' correctly."""
        trigger, target, error = _parse_run_command("run security-audit on payments-service")
        assert trigger == "security-audit"
        assert target == "payments-service"
        assert error is None

    def test_run_with_spaces_in_trigger(self):
        """Parse trigger names with spaces."""
        trigger, target, error = _parse_run_command("run Weekly Security Audit on /path/to/repo")
        assert trigger == "Weekly Security Audit"
        assert target == "/path/to/repo"
        assert error is None

    def test_empty_text_returns_usage(self):
        """Empty command text returns usage error."""
        _, _, error = _parse_run_command("")
        assert error is not None
        assert "Usage" in error

    def test_no_run_prefix_returns_usage(self):
        """Command without 'run' prefix returns usage error."""
        _, _, error = _parse_run_command("start something on target")
        assert error is not None
        assert "Usage" in error

    def test_no_on_keyword_returns_usage(self):
        """Command without 'on' returns usage error."""
        _, _, error = _parse_run_command("run security-audit payments")
        assert error is not None
        assert "Usage" in error


# =============================================================================
# Slash command endpoint tests
# =============================================================================


class TestSlashCommandEndpoint:
    """Test POST /api/integrations/slack/command endpoint."""

    SIGNING_SECRET = "test_secret"

    def _build_request(self, text="run security-audit on payments", timestamp=None):
        """Build a signed Slack slash command request."""
        ts = timestamp or str(int(time.time()))
        body = urlencode(
            {
                "command": "/agented",
                "text": text,
                "user_id": "U12345",
                "channel_id": "C12345",
                "response_url": "https://hooks.slack.com/response/test",
            }
        )
        sig_basestring = f"v0:{ts}:{body}"
        computed = hmac.new(
            self.SIGNING_SECRET.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
        signature = f"v0={computed}"
        return body, ts, signature

    @patch("app.routes.integrations._get_slack_signing_secret")
    def test_invalid_signature_returns_401(self, mock_secret, client):
        """Invalid signature returns 401 Unauthorized."""
        mock_secret.return_value = self.SIGNING_SECRET
        ts = str(int(time.time()))
        body = "command=/agented&text=test"

        resp = client.post(
            "/api/integrations/slack/command",
            data=body,
            content_type="application/x-www-form-urlencoded",
            headers={
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": "v0=invalid_sig",
            },
        )
        assert resp.status_code == 401

    @patch("app.routes.integrations._get_slack_signing_secret")
    def test_expired_timestamp_returns_401(self, mock_secret, client):
        """Expired timestamp returns 401."""
        mock_secret.return_value = self.SIGNING_SECRET
        old_ts = str(int(time.time()) - 600)
        body, _, sig = self._build_request(timestamp=old_ts)

        resp = client.post(
            "/api/integrations/slack/command",
            data=body,
            content_type="application/x-www-form-urlencoded",
            headers={
                "X-Slack-Request-Timestamp": old_ts,
                "X-Slack-Signature": sig,
            },
        )
        assert resp.status_code == 401

    @patch("app.routes.integrations._dispatch_slash_command_execution")
    @patch("app.routes.integrations._get_slack_signing_secret")
    def test_unknown_trigger_returns_error(self, mock_secret, mock_dispatch, client):
        """Unknown trigger name returns ephemeral error message."""
        mock_secret.return_value = self.SIGNING_SECRET
        body, ts, sig = self._build_request(text="run nonexistent-trigger on target")

        resp = client.post(
            "/api/integrations/slack/command",
            data=body,
            content_type="application/x-www-form-urlencoded",
            headers={
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["response_type"] == "ephemeral"
        assert "Unknown trigger" in data["text"]
        mock_dispatch.assert_not_called()

    @patch("app.routes.integrations._dispatch_slash_command_execution")
    @patch("app.routes.integrations._get_slack_signing_secret")
    def test_valid_command_dispatches_execution(self, mock_secret, mock_dispatch, client):
        """Valid command dispatches execution and returns immediate ephemeral response."""
        mock_secret.return_value = self.SIGNING_SECRET
        # Use a known predefined trigger name
        body, ts, sig = self._build_request(text="run Weekly Security Audit on /path/repo")

        resp = client.post(
            "/api/integrations/slack/command",
            data=body,
            content_type="application/x-www-form-urlencoded",
            headers={
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": sig,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["response_type"] == "ephemeral"
        assert "Starting" in data["text"]

    @patch("app.routes.integrations._get_slack_signing_secret")
    def test_no_signing_secret_returns_error(self, mock_secret, client):
        """Missing signing secret returns server error."""
        mock_secret.return_value = ""
        ts = str(int(time.time()))

        resp = client.post(
            "/api/integrations/slack/command",
            data="command=/agented&text=test",
            content_type="application/x-www-form-urlencoded",
            headers={
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": "v0=anything",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "configuration error" in data["text"].lower()
