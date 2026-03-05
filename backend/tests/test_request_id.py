"""Tests for request ID propagation and rate limit 429 response format."""

import re

import pytest

from app import create_app


@pytest.fixture()
def rate_app(isolated_db):
    """Create a fresh app with a low-limit test route for rate limit testing."""
    app = create_app({"TESTING": True})

    limiter = app.extensions.get("limiter")

    @app.route("/test-rate-limit")
    @limiter.limit("2/minute")
    def _test_rate_limited():
        return {"ok": True}

    @app.route("/test-rate-limit-rid")
    @limiter.limit("1/minute")
    def _test_rl_rid():
        return {"ok": True}

    return app


@pytest.fixture()
def rate_client(rate_app):
    """Test client for the rate-limited app."""
    return rate_app.test_client()


class TestRequestIdHeader:
    """Verify X-Request-ID header is present on all responses."""

    def test_response_includes_request_id_header(self, client):
        """Every response includes an X-Request-ID header."""
        resp = client.get("/health/readiness")
        assert resp.status_code == 200
        rid = resp.headers.get("X-Request-ID")
        assert rid is not None
        # Should be a UUID-v4 format
        assert re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            rid,
        ), f"X-Request-ID is not UUID format: {rid}"

    def test_request_id_on_error_response(self, client):
        """Error responses also include X-Request-ID header."""
        resp = client.get("/api/this-route-does-not-exist")
        assert resp.status_code == 404
        rid = resp.headers.get("X-Request-ID")
        assert rid is not None

    def test_client_supplied_request_id_is_honoured(self, client):
        """If client sends X-Request-ID, server uses it instead of generating one."""
        custom_id = "my-custom-trace-id-999"
        resp = client.get("/health/readiness", headers={"X-Request-ID": custom_id})
        assert resp.headers.get("X-Request-ID") == custom_id

    def test_request_id_appears_in_error_body(self, client):
        """The unified error response body includes request_id field."""
        resp = client.get("/api/this-route-does-not-exist")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "request_id" in data
        # Should match the header
        assert data["request_id"] == resp.headers.get("X-Request-ID")


class TestRateLimitResponse:
    """Verify 429 responses have structured error format and Retry-After header."""

    def test_rate_limit_returns_429_with_retry_after(self, rate_client):
        """Exceeding rate limit returns 429 with Retry-After header and structured body."""
        # First two requests should succeed
        resp1 = rate_client.get("/test-rate-limit")
        assert resp1.status_code == 200

        resp2 = rate_client.get("/test-rate-limit")
        assert resp2.status_code == 200

        # Third request should be rate-limited
        resp3 = rate_client.get("/test-rate-limit")
        assert resp3.status_code == 429

        # Check Retry-After header
        retry_after = resp3.headers.get("Retry-After")
        assert retry_after is not None, "429 response missing Retry-After header"
        assert int(retry_after) > 0

        # Check structured error body
        data = resp3.get_json()
        assert data["code"] == "RATE_LIMITED"
        assert "Rate limit exceeded" in data["message"]
        # Backward compat
        assert data["error"] == data["message"]

    def test_rate_limit_response_has_request_id(self, rate_client):
        """429 response body includes request_id for tracing."""
        rate_client.get("/test-rate-limit-rid")  # Use the one allowed request
        resp = rate_client.get("/test-rate-limit-rid")  # Trigger 429
        assert resp.status_code == 429
        data = resp.get_json()
        assert "request_id" in data
        # Should match header
        assert data["request_id"] == resp.headers.get("X-Request-ID")


class TestRequestIdInLogs:
    """Verify request_id appears in structured log output."""

    def test_request_id_in_log_output(self, client, caplog):
        """Request ID appears in log records from app.request logger."""
        import logging

        with caplog.at_level(logging.INFO, logger="app.request"):
            resp = client.get("/health/readiness")

        rid = resp.headers.get("X-Request-ID")
        assert rid is not None

        # The request logger should have at least one record
        request_logs = [r for r in caplog.records if r.name == "app.request"]
        assert len(request_logs) > 0, "No log records from app.request logger"
