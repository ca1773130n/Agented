"""Litestar exception handlers (wave 80).

Mirror the Flask error handlers in app/__init__.py so JSON shape stays
consistent and 500s feed into the same error_capture sink.
"""

from __future__ import annotations

import logging
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
    return Response(
        content=_error_body(code, message), status_code=status, media_type="application/json"
    )


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
    code = (
        code_map.get(HTTPStatus(status), "HTTP_ERROR")
        if status in {s.value for s in HTTPStatus}
        else "HTTP_ERROR"
    )
    return _json_response(code, exc.detail or HTTPStatus(status).phrase, status)


def not_authorized_handler(_: Request, exc: NotAuthorizedException) -> Response:
    return _json_response("UNAUTHORIZED", exc.detail or "Unauthorized", HTTPStatus.UNAUTHORIZED)


def permission_denied_handler(_: Request, exc: PermissionDeniedException) -> Response:
    return _json_response("FORBIDDEN", exc.detail or "Permission denied", HTTPStatus.FORBIDDEN)


_SPA_INDEX_BYTES: bytes | None = None


def _spa_index_bytes() -> bytes | None:
    """Read + cache the SPA index once instead of re-reading the file on every
    non-API 404 (03-core L4). Logs (not swallows) a genuine read error."""
    global _SPA_INDEX_BYTES
    if _SPA_INDEX_BYTES is None:
        try:
            _SPA_INDEX_BYTES = _SPA_INDEX.read_bytes()
        except OSError as exc:
            logger.warning("SPA index unreadable (%s): %s", _SPA_INDEX, exc)
            return None
    return _SPA_INDEX_BYTES


def not_found_handler(request: Request, exc: NotFoundException) -> Response:
    """Serve SPA index.html for non-API 404s; JSON for API 404s."""
    path = request.url.path
    is_api = any(path == p.rstrip("/") or path.startswith(p) for p in _API_PREFIXES)
    if not is_api:
        body = _spa_index_bytes()
        if body is not None:
            return Response(content=body, status_code=HTTPStatus.OK, media_type="text/html")
    return _json_response("NOT_FOUND", exc.detail or "Not found", HTTPStatus.NOT_FOUND)


def validation_handler(_: Request, exc: ValidationException) -> Response:
    return _json_response(
        "VALIDATION_ERROR",
        exc.detail or "Validation failed",
        HTTPStatus.UNPROCESSABLE_ENTITY,
    )


def value_error_handler(_: Request, exc: ValueError) -> Response:
    # Don't echo the raw ValueError text to the client — an unhandled ValueError
    # may carry internal detail (column names, IDs, paths). Intentional,
    # user-facing validation in this codebase uses structured error_response /
    # ClientException, not raw ValueError reaching this catch-all. Log the
    # detail server-side for operators; return a generic message.
    logger.warning("Unhandled ValueError surfaced to client: %s", exc, exc_info=True)
    return _json_response(
        "VALIDATION_ERROR",
        "Invalid request",
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


def session_persist_error_handler(_: Request, exc: Exception) -> Response:
    """v0.7.97 — global 409 handler for the
    ``ProjectSessionManager.SessionPersistError`` race fix.

    Imported lazily so this module doesn't pull in the PSM (which
    has its own subprocess + threading state) at import time.
    Every caller of ``PSM.create_session`` (currently the SA
    Ouroboros bridge + several ``grd_routes`` + ``grd_planning_service``
    surfaces) now gets a clean ``409 SESSION_PERSIST_RACE`` body
    when a parent FK target was deleted mid-spawn, instead of a
    generic ``500 INTERNAL_SERVER_ERROR``.
    """
    # Don't echo the raw exception text to the client (it may carry internal
    # FK/SQL detail) — log it server-side, return a controlled message (03 M1).
    logger.warning("Session persist race: %s", exc, exc_info=True)
    return _json_response(
        "SESSION_PERSIST_RACE",
        "The parent resource was modified during session creation; please retry.",
        HTTPStatus.CONFLICT,
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


def build_exception_handlers() -> dict:
    """Factory — called by ``create_app`` at construction time so the
    PSM import (subprocess + threading state) doesn't run at module
    import. Tests that build a Litestar TestClient via ``create_app``
    pick up the full handler registry; route-only test clients
    (``create_test_client(route_handlers=...)``) can opt in by
    passing the result as ``exception_handlers=...``.
    """
    from app.services.project_session_manager import SessionPersistError

    return {
        NotAuthorizedException: not_authorized_handler,
        PermissionDeniedException: permission_denied_handler,
        NotFoundException: not_found_handler,
        ValidationException: validation_handler,
        HTTPException: http_exception_handler,
        ValueError: value_error_handler,
        PermissionError: permission_error_handler,
        sqlite3.IntegrityError: integrity_error_handler,
        sqlite3.OperationalError: operational_error_handler,
        SessionPersistError: session_persist_error_handler,
        Exception: unhandled_handler,
    }
