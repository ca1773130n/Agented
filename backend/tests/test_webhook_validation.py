"""Tests for unified WebhookValidationService.

Covers HMAC signature validation, timestamp-based replay protection,
full validation pipeline, and route-level integration (403 responses).
"""

import hashlib
import hmac
import json
import time

import pytest


# ---------------------------------------------------------------------------
# Unit tests: validate_signature
# ---------------------------------------------------------------------------


class TestValidateSignature:
    """Tests for WebhookValidationService.validate_signature()."""

    def _sign(self, payload: bytes, secret: str, algo: str = "sha256") -> str:
        """Helper to compute a valid HMAC signature header."""
        hash_func = hashlib.sha256 if algo == "sha256" else hashlib.sha1
        digest = hmac.new(secret.encode("utf-8"), payload, hash_func).hexdigest()
        return f"{algo}={digest}"

    def test_valid_sha256_signature(self):
        from app.services.webhook_validation_service import WebhookValidationService

        payload = b'{"event": "test"}'
        secret = "test-secret-123"
        sig = self._sign(payload, secret, "sha256")

        assert WebhookValidationService.validate_signature(payload, sig, secret) is True

    def test_invalid_sha256_signature(self):
        from app.services.webhook_validation_service import WebhookValidationService

        payload = b'{"event": "test"}'
        secret = "test-secret-123"
        sig = "sha256=0000000000000000000000000000000000000000000000000000000000000000"

        assert WebhookValidationService.validate_signature(payload, sig, secret) is False

    def test_missing_signature_header(self):
        from app.services.webhook_validation_service import WebhookValidationService

        payload = b'{"event": "test"}'
        assert WebhookValidationService.validate_signature(payload, "", "secret") is False
        assert WebhookValidationService.validate_signature(payload, None, "secret") is False

    def test_wrong_algorithm_prefix(self):
        from app.services.webhook_validation_service import WebhookValidationService

        payload = b'{"event": "test"}'
        # Header says md5= but we only support sha256 and sha1
        sig = "md5=abcdef1234567890"
        assert WebhookValidationService.validate_signature(payload, sig, "secret") is False

    def test_sha1_algorithm_legacy(self):
        from app.services.webhook_validation_service import WebhookValidationService

        payload = b'{"event": "test"}'
        secret = "legacy-secret"
        sig = self._sign(payload, secret, "sha1")

        assert (
            WebhookValidationService.validate_signature(payload, sig, secret, algorithm="sha1")
            is True
        )

    def test_empty_secret_rejected(self):
        from app.services.webhook_validation_service import WebhookValidationService

        payload = b'{"event": "test"}'
        sig = "sha256=anything"
        assert WebhookValidationService.validate_signature(payload, sig, "") is False

    def test_tampered_payload_rejected(self):
        from app.services.webhook_validation_service import WebhookValidationService

        payload = b'{"event": "test"}'
        secret = "test-secret"
        sig = self._sign(payload, secret)

        tampered = b'{"event": "hacked"}'
        assert WebhookValidationService.validate_signature(tampered, sig, secret) is False


# ---------------------------------------------------------------------------
# Unit tests: validate_timestamp
# ---------------------------------------------------------------------------


class TestValidateTimestamp:
    """Tests for WebhookValidationService.validate_timestamp()."""

    def test_within_tolerance(self):
        from app.services.webhook_validation_service import WebhookValidationService

        ts = str(int(time.time()))
        assert WebhookValidationService.validate_timestamp(ts, tolerance_seconds=300) is True

    def test_outside_tolerance(self):
        from app.services.webhook_validation_service import WebhookValidationService

        old_ts = str(int(time.time()) - 600)  # 10 minutes ago
        assert WebhookValidationService.validate_timestamp(old_ts, tolerance_seconds=300) is False

    def test_no_header_returns_true(self):
        """No timestamp header + not required = True (passthrough)."""
        from app.services.webhook_validation_service import WebhookValidationService

        assert WebhookValidationService.validate_timestamp(None) is True
        assert WebhookValidationService.validate_timestamp("") is True

    def test_iso8601_timestamp(self):
        from datetime import datetime, timezone

        from app.services.webhook_validation_service import WebhookValidationService

        now_iso = datetime.now(timezone.utc).isoformat()
        assert WebhookValidationService.validate_timestamp(now_iso, tolerance_seconds=300) is True

    def test_future_timestamp_within_tolerance(self):
        from app.services.webhook_validation_service import WebhookValidationService

        future_ts = str(int(time.time()) + 60)  # 1 minute in the future
        assert (
            WebhookValidationService.validate_timestamp(future_ts, tolerance_seconds=300) is True
        )

    def test_future_timestamp_outside_tolerance(self):
        from app.services.webhook_validation_service import WebhookValidationService

        far_future = str(int(time.time()) + 600)  # 10 minutes in the future
        assert (
            WebhookValidationService.validate_timestamp(far_future, tolerance_seconds=300) is False
        )


# ---------------------------------------------------------------------------
# Unit tests: validate_webhook (full pipeline with Flask test request)
# ---------------------------------------------------------------------------


class TestValidateWebhook:
    """Tests for validate_webhook() and validate_github() full pipeline."""

    @pytest.fixture
    def app(self, isolated_db):
        """Create a minimal Flask app for test requests."""
        from app import create_app

        app = create_app()
        return app

    def _sign(self, payload: bytes, secret: str, algo: str = "sha256") -> str:
        hash_func = hashlib.sha256 if algo == "sha256" else hashlib.sha1
        digest = hmac.new(secret.encode("utf-8"), payload, hash_func).hexdigest()
        return f"{algo}={digest}"

    def test_valid_webhook_pipeline(self, app):
        from app.services.webhook_validation_service import WebhookValidationService

        payload = b'{"test": true}'
        secret = "pipeline-secret"
        sig = self._sign(payload, secret)

        with app.test_request_context(
            "/webhook",
            method="POST",
            data=payload,
            content_type="application/json",
            headers={"X-Webhook-Signature-256": sig},
        ):
            from flask import request

            is_valid, reason = WebhookValidationService.validate_webhook(request, secret)
            assert is_valid is True
            assert reason == ""

    def test_invalid_signature_returns_error(self, app):
        from app.services.webhook_validation_service import WebhookValidationService

        payload = b'{"test": true}'
        secret = "pipeline-secret"

        with app.test_request_context(
            "/webhook",
            method="POST",
            data=payload,
            content_type="application/json",
            headers={"X-Webhook-Signature-256": "sha256=bad"},
        ):
            from flask import request

            is_valid, reason = WebhookValidationService.validate_webhook(request, secret)
            assert is_valid is False
            assert "Invalid webhook signature" in reason

    def test_require_timestamp_missing_rejected(self, app):
        from app.services.webhook_validation_service import WebhookValidationService

        payload = b'{"test": true}'
        secret = "pipeline-secret"
        sig = self._sign(payload, secret)

        with app.test_request_context(
            "/webhook",
            method="POST",
            data=payload,
            content_type="application/json",
            headers={"X-Webhook-Signature-256": sig},
        ):
            from flask import request

            is_valid, reason = WebhookValidationService.validate_webhook(
                request, secret, require_timestamp=True
            )
            assert is_valid is False
            assert "Missing required timestamp" in reason

    def test_replay_detected_with_stale_timestamp(self, app):
        from app.services.webhook_validation_service import WebhookValidationService

        payload = b'{"test": true}'
        secret = "pipeline-secret"
        sig = self._sign(payload, secret)
        old_ts = str(int(time.time()) - 600)

        with app.test_request_context(
            "/webhook",
            method="POST",
            data=payload,
            content_type="application/json",
            headers={
                "X-Webhook-Signature-256": sig,
                "X-Webhook-Timestamp": old_ts,
            },
        ):
            from flask import request

            is_valid, reason = WebhookValidationService.validate_webhook(request, secret)
            assert is_valid is False
            assert "replay" in reason.lower()

    def test_validate_github_valid(self, app):
        from app.services.webhook_validation_service import WebhookValidationService

        payload = b'{"action": "opened"}'
        secret = "gh-secret"
        sig = self._sign(payload, secret)

        with app.test_request_context(
            "/api/webhooks/github",
            method="POST",
            data=payload,
            content_type="application/json",
            headers={"X-Hub-Signature-256": sig},
        ):
            from flask import request

            is_valid, reason = WebhookValidationService.validate_github(request, secret)
            assert is_valid is True

    def test_validate_github_no_secret(self, app):
        from app.services.webhook_validation_service import WebhookValidationService

        payload = b'{"action": "opened"}'

        with app.test_request_context(
            "/api/webhooks/github",
            method="POST",
            data=payload,
            content_type="application/json",
            headers={"X-Hub-Signature-256": "sha256=anything"},
        ):
            from flask import request

            is_valid, reason = WebhookValidationService.validate_github(request, "")
            assert is_valid is False
            assert "not configured" in reason.lower()


# ---------------------------------------------------------------------------
# Route-level integration: 403 on invalid signature
# ---------------------------------------------------------------------------


class TestRouteIntegration:
    """Route-level tests ensuring 403 responses on invalid signatures."""

    @pytest.fixture
    def client(self, isolated_db):
        from app import create_app

        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def _sign(self, payload: bytes, secret: str) -> str:
        digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def test_github_webhook_invalid_signature_returns_403(self, client, monkeypatch):
        """GitHub webhook with invalid signature returns 403."""
        monkeypatch.setattr(
            "app.routes.github_webhook.GITHUB_WEBHOOK_SECRET", "real-secret"
        )

        payload = json.dumps({"action": "opened"}).encode()
        resp = client.post(
            "/api/webhooks/github/",
            data=payload,
            content_type="application/json",
            headers={"X-Hub-Signature-256": "sha256=invalid"},
        )
        assert resp.status_code == 403

    def test_github_webhook_valid_signature_passes(self, client, monkeypatch):
        """GitHub webhook with valid signature passes through to event processing."""
        secret = "test-gh-secret"
        monkeypatch.setattr("app.routes.github_webhook.GITHUB_WEBHOOK_SECRET", secret)

        payload = json.dumps({"action": "opened"}).encode()
        sig = self._sign(payload, secret)
        resp = client.post(
            "/api/webhooks/github/",
            data=payload,
            content_type="application/json",
            headers={
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "ping",
            },
        )
        # ping event returns 200 with pong
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "pong"
