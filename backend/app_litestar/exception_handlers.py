"""Litestar exception handlers (wave 80).

Mirror the Flask error handlers in app/__init__.py so JSON shape stays
consistent and 500s feed into the same error_capture sink.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import traceback
from http import HTTPStatus
from pathlib import Path
from typing import Any

from litestar import Request, Response
from litestar.exceptions import (
    HTTPException,
    NotAuthorizedException,
    NotFoundException,
    PermissionDeniedException,
    ValidationException,
)

logger = logging.getLogger(__name__)


# SPA fallback — serves backend/static/index.html for non-API 404s so the
# Vue frontend can deep-link in production. Mirrors the wave-79 spa.py.
_SPA_INDEX = Path(__file__).resolve().parent.parent / "static" / "index.html"
_API_PREFIXES = ("/api/", "/admin/", "/health/", "/docs/", "/openapi/", "/schema/")


def _error_body(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _json_response(code: str, message: str, status: int) -> Response:
    return Response(content=_error_body(code, message), status_code=status, media_type="application/json")


def http_exception_handler(_: Request, exc: HTTPException) -> Response:
    code_map = {
        HTTPStatus.NOT_FOUND: "NOT_FOUND",
        HTTPStatus.METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
        HTTPStatus.REQUEST_ENTITY_TOO_LARGE: "PAYLOAD_TOO_LARGE",
        HTTPStatus.TOO_MANY_REQUESTS: "RATE_LIMITED",
        HTTPStatus.UNAUTHORIZED: "UNAUTHORIZED",
        HTTPStatus.FORBIDDEN: "FORBIDDEN",
        HTTPStatus.CONFLICT: "CONFLICT",
        HTTPStatus.SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
        HTTPStatus.UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
        HTTPStatus.BAD_REQUEST: "BAD_REQUEST",
    }
    status = exc.status_code
    code = code_map.get(HTTPStatus(status), "HTTP_ERROR") if status in {s.value for s in HTTPStatus} else "HTTP_ERROR"
    return _json_response(code, exc.detail or HTTPStatus(status).phrase, status)


def not_authorized_handler(_: Request, exc: NotAuthorizedException) -> Response:
    return _json_response("UNAUTHORIZED", exc.detail or "Unauthorized", HTTPStatus.UNAUTHORIZED)


def permission_denied_handler(_: Request, exc: PermissionDeniedException) -> Response:
    return _json_response("FORBIDDEN", exc.detail or "Permission denied", HTTPStatus.FORBIDDEN)


def not_found_handler(request: Request, exc: NotFoundException) -> Response:
    """Serve SPA index.html for non-API 404s; JSON for API 404s."""
    path = request.url.path
    is_api = any(path == p.rstrip("/") or path.startswith(p) for p in _API_PREFIXES)
    if not is_api and _SPA_INDEX.exists():
        try:
            return Response(
                content=_SPA_INDEX.read_bytes(),
                status_code=HTTPStatus.OK,
                media_type="text/html",
            )
        except OSError:
            pass
    return _json_response("NOT_FOUND", exc.detail or "Not found", HTTPStatus.NOT_FOUND)


def validation_handler(_: Request, exc: ValidationException) -> Response:
    return _json_response(
        "VALIDATION_ERROR",
        exc.detail or "Validation failed",
        HTTPStatus.UNPROCESSABLE_ENTITY,
    )


def value_error_handler(_: Request, exc: ValueError) -> Response:
    return _json_response(
        "VALIDATION_ERROR",
        f"Validation failed: {exc}",
        HTTPStatus.UNPROCESSABLE_ENTITY,
    )


def permission_error_handler(_: Request, exc: PermissionError) -> Response:
    del exc
    return _json_response("FORBIDDEN", "Permission denied", HTTPStatus.FORBIDDEN)


def integrity_error_handler(_: Request, exc: sqlite3.IntegrityError) -> Response:
    del exc
    return _json_response(
        "CONFLICT",
        "Resource conflict: a record with this identifier already exists",
        HTTPStatus.CONFLICT,
    )


def operational_error_handler(_: Request, exc: sqlite3.OperationalError) -> Response:
    logger.error("Database operational error: %s", exc, exc_info=True)
    try:
        from app.services.error_capture import capture_error

        capture_error(category="db_error", message=str(exc))
    except Exception:
        logger.debug("Error capture failed", exc_info=True)
    return _json_response(
        "SERVICE_UNAVAILABLE",
        "Service temporarily unavailable",
        HTTPStatus.SERVICE_UNAVAILABLE,
    )


def unhandled_handler(_: Request, exc: Exception) -> Response:
    """Last-resort 500 handler — feeds error_capture and returns a generic body."""
    try:
        from app.services.error_capture import capture_error

        tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        capture_error(category="runtime_error", message=str(exc), stack_trace=tb_str)
    except Exception:
        logger.debug("Error capture failed", exc_info=True)
    return _json_response(
        "INTERNAL_SERVER_ERROR",
        "Internal server error",
        HTTPStatus.INTERNAL_SERVER_ERROR,
    )


EXCEPTION_HANDLERS = {
    NotAuthorizedException: not_authorized_handler,
    PermissionDeniedException: permission_denied_handler,
    NotFoundException: not_found_handler,
    ValidationException: validation_handler,
    HTTPException: http_exception_handler,
    ValueError: value_error_handler,
    PermissionError: permission_error_handler,
    sqlite3.IntegrityError: integrity_error_handler,
    sqlite3.OperationalError: operational_error_handler,
    Exception: unhandled_handler,
}
