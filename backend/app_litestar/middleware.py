"""Litestar middleware that mirrors Flask's request_id + auth (wave 80)."""

from __future__ import annotations

import hmac
import logging
import os
import uuid
from typing import Any

from litestar.middleware import AbstractMiddleware
from litestar.types import ASGIApp, Receive, Scope, Send

from app.db.rbac import (
    get_role_and_user_for_api_key,
    get_role_for_api_key,
    has_any_keys,
)
from app.db.sessions import get_session_by_token
from app.logging_config import current_user_var, request_id_var

logger = logging.getLogger("app.request")


_AUTH_BYPASS_PREFIXES = (
    "/health",
    "/docs",
    "/openapi",
    "/schema",
    "/api/webhooks/github",
    "/api/oauth-callback",
)


def _path_requires_auth(path: str) -> bool:
    if not (path.startswith("/admin") or path.startswith("/api")):
        return False
    for prefix in _AUTH_BYPASS_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return False
    return True


def _resolve_session_user(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    if not token:
        return None
    sess = get_session_by_token(token)
    return sess["user_id"] if sess else None


class RequestContextMiddleware(AbstractMiddleware):
    """Set request_id + current_user contextvars; emit X-Request-ID header."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", ())
        }
        rid = headers.get("x-request-id") or str(uuid.uuid4())
        request_id_var.set(rid)

        user_id: str | None = None
        api_key = headers.get("x-api-key")
        if api_key:
            try:
                resolved = get_role_and_user_for_api_key(api_key)
                if resolved is not None:
                    _, user_id = resolved
            except Exception as exc:
                logger.debug("user lookup failed: %s", exc)
        if user_id is None:
            user_id = _resolve_session_user(headers.get("authorization"))
        current_user_var.set(user_id)

        async def send_with_request_id(message: Any) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", rid.encode("latin-1")))
                message = {**message, "headers": response_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_var.set(None)
            current_user_var.set(None)


class ApiKeyMiddleware(AbstractMiddleware):
    """Reject /admin/* and /api/* requests without a valid API key.

    Bypass paths (`/health`, `/docs`, `/schema`, webhook callbacks) are
    public.  Bootstrap mode (no DB-stored keys, no env var) lets every
    request through so first-run UX works.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not _path_requires_auth(path):
            await self.app(scope, receive, send)
            return

        db_has_keys = has_any_keys()
        env_key = os.environ.get("AGENTED_API_KEY", "")

        if not db_has_keys and not env_key:
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", ())
        }
        provided = headers.get("x-api-key", "")

        # Sessions: Authorization: Bearer <token> bypasses the X-API-Key check.
        if not provided and headers.get("authorization"):
            session_user = _resolve_session_user(headers["authorization"])
            if session_user:
                await self.app(scope, receive, send)
                return

        if not provided:
            await self._unauthorized(send)
            return

        if db_has_keys and get_role_for_api_key(provided):
            await self.app(scope, receive, send)
            return

        if env_key and hmac.compare_digest(provided, env_key):
            await self.app(scope, receive, send)
            return

        await self._unauthorized(send)

    @staticmethod
    async def _unauthorized(send: Send) -> None:
        body = b'{"error":"Unauthorized"}'
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})


class RequestLoggingMiddleware(AbstractMiddleware):
    """Log method/path/status after each HTTP response."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        status_code = 0
        content_length: str | None = None

        async def capture(message: Any) -> None:
            nonlocal status_code, content_length
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                for k, v in message.get("headers", []):
                    if k.decode("latin-1").lower() == "content-length":
                        content_length = v.decode("latin-1")
                        break
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            logger.info(
                "%s %s %s %s",
                scope.get("method", ""),
                scope.get("path", ""),
                status_code,
                content_length,
            )
