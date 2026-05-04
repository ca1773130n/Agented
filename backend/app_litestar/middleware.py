"""Litestar middleware that mirrors Flask's request_id + auth + security (wave 80, 81)."""

from __future__ import annotations

import hmac
import logging
import os
import uuid
from typing import Any, Optional

from litestar.middleware import ASGIMiddleware
from litestar.types import ASGIApp, Receive, Scope, Send

from app.db.rbac import (
    get_highest_role_for_user,
    get_role_and_user_for_api_key,
    has_any_keys,
)
from app.db.sessions import get_session_by_token
from app.db.sessions import rotate_session as _rotate_session
from app.logging_config import current_user_var, request_id_var
from app_litestar.auth_guards import has_sufficient_role, required_role

logger = logging.getLogger("app.request")


def _json_error_body(code: str, message: str) -> bytes:
    """Build a short-circuit JSON error body that includes the request_id when set.

    The deleted Flask `test_request_id::test_rate_limit_response_has_request_id`
    asserted both `X-Request-ID` header and `request_id` field on the body for
    429s. Mirror that here so 401/429 short-circuits stay traceable.
    """
    import json as _json

    rid = request_id_var.get()
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if rid:
        payload["request_id"] = rid
    return _json.dumps(payload, separators=(",", ":")).encode("utf-8")


_AUTH_BYPASS_PREFIXES = (
    "/health",
    "/docs",
    "/openapi",
    "/schema",
    "/api/webhooks/github",
    "/api/oauth-callback",
    # Auth-establishing routes — caller has no credentials yet. v0.5.12:
    # these must skip authentication entirely so unauthenticated users
    # can sign up, log in, and recover passwords.
    "/api/auth/login",
    "/api/auth/signup",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
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


class RequestContextMiddleware(ASGIMiddleware):
    """Set request_id + current_user contextvars; emit X-Request-ID header."""

    async def handle(
        self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp
    ) -> None:
        if scope["type"] != "http":
            await next_app(scope, receive, send)
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
            await next_app(scope, receive, send_with_request_id)
        finally:
            request_id_var.set(None)
            current_user_var.set(None)


class ApiKeyMiddleware(ASGIMiddleware):
    """Reject /admin/* and /api/* requests without a valid API key.

    Bypass paths (`/health`, `/docs`, `/schema`, webhook callbacks) are
    public.  Bootstrap mode (no DB-stored keys, no env var) lets every
    request through so first-run UX works.
    """

    async def handle(
        self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp
    ) -> None:
        if scope["type"] != "http":
            await next_app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        if method == "OPTIONS":
            await next_app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not _path_requires_auth(path):
            await next_app(scope, receive, send)
            return

        db_has_keys = has_any_keys()
        env_key = os.environ.get("AGENTED_API_KEY", "")

        if not db_has_keys and not env_key:
            # Bootstrap mode — every request through.
            await next_app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", ())
        }
        api_key_provided = headers.get("x-api-key", "")
        bearer = ""
        if headers.get("authorization", "").lower().startswith("bearer "):
            bearer = headers["authorization"][7:].strip()

        principal_role: Optional[str] = None
        principal_user_id: Optional[str] = None
        rotated_token: Optional[str] = None

        # 1) Bearer session path.
        if bearer:
            session = get_session_by_token(bearer)
            if session:
                principal_user_id = session["user_id"]
                principal_role = get_highest_role_for_user(principal_user_id)
                # Rotate — issue a new token; emit X-New-Session-Token.
                rotated = _rotate_session(bearer)
                if rotated:
                    rotated_token = rotated["token"]
            else:
                await self._unauthorized(send)
                return
        # 2) X-API-Key path (no rotation; explicit credentials).
        elif api_key_provided:
            if db_has_keys:
                role_and_user = get_role_and_user_for_api_key(api_key_provided)
                if role_and_user:
                    principal_role, principal_user_id = role_and_user
            if principal_role is None and env_key and hmac.compare_digest(
                api_key_provided, env_key
            ):
                principal_role = "admin"  # env-key principal acts as admin
            if principal_role is None:
                await self._unauthorized(send)
                return
        else:
            await self._unauthorized(send)
            return

        # 3) Coarse role check.
        needed = required_role(method, path)
        if needed is not None and not has_sufficient_role(principal_role, needed):
            await self._forbidden(send)
            return

        # 4) Stash principal for per-route guards + handlers.
        scope.setdefault("state", {})
        scope["state"]["principal"] = {
            "user_id": principal_user_id,
            "role": principal_role,
        }

        # 5) Wrap `send` to inject X-New-Session-Token on the response start.
        async def send_with_rotation(message: Any) -> None:
            if message["type"] == "http.response.start" and rotated_token:
                hdrs = list(message.get("headers", []))
                hdrs.append(
                    (b"x-new-session-token", rotated_token.encode("latin-1"))
                )
                message = dict(message, headers=hdrs)
            await send(message)

        await next_app(scope, receive, send_with_rotation)

    @staticmethod
    async def _unauthorized(send: Send) -> None:
        body = _json_error_body("UNAUTHORIZED", "Unauthorized")
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

    @staticmethod
    async def _forbidden(send: Send) -> None:
        body = _json_error_body("FORBIDDEN", "Forbidden")
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})


class RequestLoggingMiddleware(ASGIMiddleware):
    """Log method/path/status after each HTTP response."""

    async def handle(
        self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp
    ) -> None:
        if scope["type"] != "http":
            await next_app(scope, receive, send)
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
            await next_app(scope, receive, capture)
        finally:
            logger.info(
                "%s %s %s %s",
                scope.get("method", ""),
                scope.get("path", ""),
                status_code,
                content_length,
            )


# OWASP-aligned defaults that match the Flask-Talisman config wave 80 retired.
_FORCE_HTTPS = os.environ.get("FORCE_HTTPS", "false").lower() == "true"
_HSTS_MAX_AGE = "31536000"  # 1 year
_CSP = "; ".join(
    [
        "default-src 'self'",
        # Swagger / Litestar's /schema/swagger needs inline scripts + styles.
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "connect-src 'self'",
    ]
)


class SecurityHeadersMiddleware(ASGIMiddleware):
    """Apply CSP / HSTS / X-Frame-Options / Referrer-Policy on every HTTP response.

    Mirrors the flask_talisman defaults from the wave 79 Flask app:
      - Strict-Transport-Security: max-age=31536000; includeSubDomains
      - X-Frame-Options: DENY
      - X-Content-Type-Options: nosniff
      - Referrer-Policy: strict-origin-when-cross-origin
      - Content-Security-Policy: locked-down with Swagger inline allowance
    """

    async def handle(
        self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp
    ) -> None:
        if scope["type"] != "http":
            await next_app(scope, receive, send)
            return

        async def add_headers(message: Any) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-frame-options", b"DENY"))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append(
                    (b"referrer-policy", b"strict-origin-when-cross-origin")
                )
                headers.append((b"content-security-policy", _CSP.encode("latin-1")))
                if _FORCE_HTTPS:
                    headers.append(
                        (
                            b"strict-transport-security",
                            f"max-age={_HSTS_MAX_AGE}; includeSubDomains".encode(),
                        )
                    )
                message = {**message, "headers": headers}
            await send(message)

        await next_app(scope, receive, add_headers)


# ---------------------------------------------------------------------------
# Rate limiting (port of the Flask-Limiter setup).
# ---------------------------------------------------------------------------


from collections import defaultdict, deque
from time import monotonic


class _FixedWindowLimiter:
    """In-memory fixed-window limiter, keyed by remote_address + path family.

    Workers=1 (gunicorn) means a single process; in-memory is safe. If the
    deployment ever moves to workers>1 this needs to swap in Redis (same
    decision the Flask-Limiter setup deferred).
    """

    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def hit(self, key: tuple[str, str], limit: int, window_seconds: float) -> bool:
        """Return True if this hit is allowed; False if rate-limited."""
        now = monotonic()
        bucket = self._buckets[key]
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


_limiter = _FixedWindowLimiter()

# Per-prefix limits ported from app/routes/__init__.py (Flask-Limiter wiring):
#   `limiter.limit("20/10seconds")(webhook_bp)`  → POST /
#   `limiter.limit("30/minute")(github_webhook_bp)` → POST /api/webhooks/github
_RATE_LIMITS: tuple[tuple[str, int, float], ...] = (
    ("/api/webhooks/github", 30, 60.0),
    # Bare "/" handler is the generic webhook receiver (wave 77).
    # Match it explicitly so the limiter doesn't count unrelated requests.
)


def _client_ip(scope: Scope) -> str:
    headers = {
        k.decode("latin-1").lower(): v.decode("latin-1")
        for k, v in scope.get("headers", ())
    }
    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real = headers.get("x-real-ip")
    if real:
        return real.strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimitMiddleware(ASGIMiddleware):
    """Apply per-IP rate limits on the webhook receivers."""

    async def handle(
        self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp
    ) -> None:
        if scope["type"] != "http":
            await next_app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")

        # Generic webhook receiver lives at root POST /
        if method == "POST" and path == "/":
            limit_match = ("/", 20, 10.0)
        else:
            limit_match = next(
                (entry for entry in _RATE_LIMITS if path.startswith(entry[0])),
                None,
            )

        if limit_match is None:
            await next_app(scope, receive, send)
            return

        prefix, limit, window = limit_match
        if not _limiter.hit((_client_ip(scope), prefix), limit, window):
            body = _json_error_body("RATE_LIMITED", "Rate limit exceeded")
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"retry-after", str(int(window)).encode()),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body, "more_body": False})
            return

        await next_app(scope, receive, send)
