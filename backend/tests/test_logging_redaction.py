"""Tests for SensitiveDataFilter — redacts auth-shaped tokens in log records."""

from __future__ import annotations

import io
import logging

import pytest

from app.logging_config import SensitiveDataFilter


@pytest.fixture()
def captured_logger():
    """Logger wired to a StringIO with SensitiveDataFilter on the handler."""
    logger = logging.getLogger("test.redaction")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(SensitiveDataFilter())
    logger.addHandler(handler)

    yield logger, buf

    logger.handlers.clear()


class TestSensitiveDataFilter:
    def test_redacts_bearer_token_in_message(self, captured_logger):
        logger, buf = captured_logger
        logger.info("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")

        out = buf.getvalue()
        assert "eyJhbGciOiJIUzI1NiJ9" not in out
        assert "[REDACTED]" in out
        assert "Authorization: Bearer" in out

    def test_redacts_x_api_key_header(self, captured_logger):
        logger, buf = captured_logger
        logger.info("X-API-Key: ag-1234567890abcdef1234567890abcdef")

        out = buf.getvalue()
        assert "1234567890abcdef" not in out
        assert "[REDACTED]" in out

    def test_redacts_anthropic_style_key(self, captured_logger):
        logger, buf = captured_logger
        logger.info("calling backend with sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz1234567890")

        out = buf.getvalue()
        assert "AbCdEfGhIj" not in out
        assert "[REDACTED]" in out

    def test_redacts_openai_style_key(self, captured_logger):
        logger, buf = captured_logger
        logger.info("auth header sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz1234")

        out = buf.getvalue()
        assert "AbCdEfGhIj" not in out
        assert "[REDACTED]" in out

    def test_redacts_token_in_query_string(self, captured_logger):
        logger, buf = captured_logger
        logger.info("GET /admin/foo?token=secretvalue123 HTTP/1.1")

        out = buf.getvalue()
        assert "secretvalue123" not in out
        assert "token=[REDACTED]" in out

    def test_redacts_password_query(self, captured_logger):
        logger, buf = captured_logger
        logger.info("login: password=hunter2 user=alice")

        out = buf.getvalue()
        assert "hunter2" not in out
        assert "password=[REDACTED]" in out

    def test_redacts_in_args(self, captured_logger):
        """Format args (e.g. logger.info('hit %s', url)) must also be redacted."""
        logger, buf = captured_logger
        logger.info("hit %s", "https://api/?token=abc123secret&q=foo")

        out = buf.getvalue()
        assert "abc123secret" not in out
        assert "[REDACTED]" in out

    def test_does_not_mangle_unrelated_text(self, captured_logger):
        logger, buf = captured_logger
        logger.info("Bot bot-abc123 finished workflow workflow-xyz789 in 12.3s")

        out = buf.getvalue()
        assert "bot-abc123" in out
        assert "workflow-xyz789" in out
        assert "12.3s" in out
        assert "[REDACTED]" not in out

    def test_filter_returns_true(self):
        """Filter must always allow records through (only mutates content)."""
        filt = SensitiveDataFilter()
        record = logging.LogRecord(
            name="x",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Bearer secret",
            args=None,
            exc_info=None,
        )
        assert filt.filter(record) is True
