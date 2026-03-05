"""Tests for the unified ErrorResponse model and Flask error handlers."""

from http import HTTPStatus


class TestErrorResponseHelper:
    """Unit tests for the error_response() helper function."""

    def test_error_response_returns_correct_shape(self, app):
        """error_response() returns (dict, int) with all required fields."""
        from app.models.common import error_response

        with app.test_request_context():
            body, status = error_response("NOT_FOUND", "Bot not found", HTTPStatus.NOT_FOUND)

        assert status == 404
        assert body["code"] == "NOT_FOUND"
        assert body["message"] == "Bot not found"
        assert body["details"] is None
        assert "request_id" in body

    def test_error_field_matches_message_for_backward_compat(self, app):
        """The legacy 'error' field mirrors 'message' for backward compatibility."""
        from app.models.common import error_response

        with app.test_request_context():
            body, _ = error_response("TEST", "Something broke", HTTPStatus.BAD_REQUEST)

        assert body["error"] == body["message"]
        assert body["error"] == "Something broke"

    def test_error_response_with_details(self, app):
        """Optional details dict is included when provided."""
        from app.models.common import error_response

        details = {"field": "name", "reason": "required"}
        with app.test_request_context():
            body, status = error_response(
                "VALIDATION_ERROR", "Invalid input", HTTPStatus.UNPROCESSABLE_ENTITY, details
            )

        assert status == 422
        assert body["details"] == details

    def test_error_response_includes_request_id_from_g(self, app):
        """request_id is pulled from flask.g when available."""
        from flask import g

        from app.models.common import error_response

        with app.test_request_context():
            g.request_id = "test-uuid-1234"
            body, _ = error_response("TEST", "msg", HTTPStatus.BAD_REQUEST)

        assert body["request_id"] == "test-uuid-1234"


class TestFlaskErrorHandlers:
    """Integration tests for Flask-level error handlers returning unified shape."""

    def test_404_returns_unified_shape(self, client):
        """GET to a non-existent route returns 404 with code/message/details fields."""
        resp = client.get("/api/this-does-not-exist-at-all")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["code"] == "NOT_FOUND"
        assert data["message"] == "Not found"
        assert "details" in data
        # Backward compat field
        assert data["error"] == data["message"]

    def test_405_returns_unified_shape(self, client):
        """Wrong HTTP method returns 405 with unified error shape."""
        # PATCH on /admin/commands/ is not registered — triggers 405
        resp = client.patch("/admin/commands/")
        assert resp.status_code == 405
        data = resp.get_json()
        assert data["code"] == "METHOD_NOT_ALLOWED"
        assert data["message"] == "Method not allowed"
        assert data["error"] == data["message"]

    def test_error_response_model_instantiation(self):
        """ErrorResponse Pydantic model can be instantiated with new fields."""
        from app.models.common import ErrorResponse

        err = ErrorResponse(
            code="NOT_FOUND",
            message="Bot not found",
            error="Bot not found",
            details=None,
            request_id="abc-123",
        )
        assert err.code == "NOT_FOUND"
        assert err.message == "Bot not found"
        assert err.request_id == "abc-123"

    def test_error_response_model_optional_fields(self):
        """ErrorResponse works with only required fields (code + message)."""
        from app.models.common import ErrorResponse

        err = ErrorResponse(code="INTERNAL", message="Oops")
        assert err.error is None
        assert err.details is None
        assert err.request_id is None
