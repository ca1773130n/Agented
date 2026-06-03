"""Regression tests for the MEDIUM/LOW hardening cleanup batch."""

import hashlib
import hmac

import pytest


def test_clamp_limit_caps_and_floors():
    from app_litestar.route_helpers import MAX_LIST_LIMIT, clamp_limit

    assert clamp_limit(10_000_000) == MAX_LIST_LIMIT
    assert clamp_limit(0, default=50) == 50
    assert clamp_limit(None, default=20) == 20
    assert clamp_limit(-5, default=10) == 10
    assert clamp_limit(42) == 42


def test_wal_mode_enabled_on_connection(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"


class TestWebhookSha1:
    def _sig(self, algo, secret, body):
        h = hmac.new(secret.encode(), body, getattr(hashlib, algo)).hexdigest()
        return f"{algo}={h}"

    def test_sha256_still_accepted(self):
        from app.services.webhook_validation_service import WebhookValidationService as W

        body = b'{"x":1}'
        assert W.validate_signature(body, self._sig("sha256", "s3cr3t", body), "s3cr3t") is True

    def test_sha1_rejected_by_default(self, monkeypatch):
        monkeypatch.delenv("AGENTED_WEBHOOK_ALLOW_SHA1", raising=False)
        # Re-import to rebuild the class-level algorithm map under the env.
        import importlib

        import app.services.webhook_validation_service as mod

        importlib.reload(mod)
        W = mod.WebhookValidationService
        body = b'{"x":1}'
        # A valid sha1 signature must NOT validate (algorithm not accepted).
        assert W.validate_signature(body, self._sig("sha1", "s3cr3t", body), "s3cr3t") is False
        importlib.reload(mod)  # restore default state for other tests


def test_max_body_bytes_default_and_override(monkeypatch):
    from app_litestar.main import _max_body_bytes

    monkeypatch.delenv("AGENTED_MAX_BODY_BYTES", raising=False)
    assert _max_body_bytes() == 10 * 1024 * 1024
    monkeypatch.setenv("AGENTED_MAX_BODY_BYTES", "1048576")
    assert _max_body_bytes() == 1048576
    monkeypatch.setenv("AGENTED_MAX_BODY_BYTES", "garbage")
    assert _max_body_bytes() == 10 * 1024 * 1024
