"""Litestar middleware that mirrors Flask's request_id + auth + security (wave 80, 81)."""

from __future__ import annotations

import hmac
import logging
import os
import re
import uuid
from contextvars import ContextVar
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
from app_litestar.cookie_auth import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    csrf_valid,
    generate_csrf_token,
    parse_cookies,
    set_cookie_headers,
)

# v0.6.2 round-1 M5: import the metrics registry at module load
# instead of per-request inside PerformanceMiddleware.handle's
# finally block.
from app_litestar.metrics import registry as _metrics_registry

logger = logging.getLogger("app.request")

# Phase 23 (23-04): the policy/governance scope summary resolved for the current
# request, observable by routes/logging. ``None`` when the request carries no
# session id. Mirrors the request_id/current_user contextvar pattern.
policy_scope_var: ContextVar[Optional[dict]] = ContextVar("policy_scope", default=None)

# Matches a session id embedded in a session/execution route path, e.g.
# ``/admin/projects/{pid}/sessions/{sid}/...`` → captures ``{sid}``.
_SESSION_PATH_RE = re.compile(r"/sessions/([^/]+)")


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


# Surfaces that legitimately have sub-paths — matched by prefix. /schema,/docs
# host Swagger; /api/oauth-callback is a `{rest:path}` route the provider
# redirects into (state-gated by the proxy), so it must match its subpaths.
_AUTH_BYPASS_PREFIXES = (
    "/health",
    "/docs",
    "/openapi",
    "/schema",
    "/api/oauth-callback",
    # Phase 25: a tokenless teammate attaches/co-drives a shared session by URL
    # token (the token IS the credential, verified in-handler); and the OIDC
    # start/callback routes establish a session for a credential-less caller
    # (same rationale as the /api/auth/login bypass). Both are path-param routes,
    # so they are prefix-matched here rather than listed in _AUTH_BYPASS_EXACT.
    "/api/shared-sessions",
    "/api/auth/oidc",
)
# API endpoints that must skip auth, matched EXACTLY so a future handler mounted
# under one of these prefixes isn't silently made public (02-auth M2). The
# github webhook receiver is HMAC-gated; the auth routes establish a session for
# a caller that has no credentials yet. (oauth-callback is prefix-matched above
# because it is a path-param route the provider redirects into.)
_AUTH_BYPASS_EXACT = frozenset(
    {
        "/api/webhooks/github",
        "/api/auth/login",
        "/api/auth/signup",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
    }
)


def _path_requires_auth(path: str) -> bool:
    if not (path.startswith("/admin") or path.startswith("/api")):
        return False
    if path in _AUTH_BYPASS_EXACT:
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


def _resolve_cookie_user(cookie_header: str | None) -> str | None:
    """Resolve the session user from the HttpOnly session COOKIE.

    SECURITY (Phase 25 BLOCKER — ITEM 2, defense-in-depth): the normal SPA path
    authenticates via the session cookie, not an ``X-API-Key`` header or an
    ``Authorization: Bearer`` token. Without resolving the cookie here,
    ``current_user_var`` stayed ``None`` for every cookie-authenticated request,
    so any code that reads it (e.g. a session-owner backfill) saw no principal.
    The authoritative owner stamp is taken from the resolved ``Caller`` in the
    route, but keeping ``current_user_var`` correct for cookie auth closes the
    gap for all other readers too.
    """
    if not cookie_header:
        return None
    token = parse_cookies(cookie_header).get(SESSION_COOKIE)
    if not token:
        return None
    sess = get_session_by_token(token)
    return sess["user_id"] if sess else None


class RequestContextMiddleware(ASGIMiddleware):
    """Set request_id + current_user contextvars; emit X-Request-ID header."""

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        if scope["type"] != "http":
            await next_app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", ())
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
        if user_id is None:
            # Cookie-auth (SPA) path — the session token lives in the HttpOnly
            # cookie, not a header. See _resolve_cookie_user (25 BLOCKER ITEM 2).
            user_id = _resolve_cookie_user(headers.get("cookie"))
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

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
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
            # Bootstrap mode (no roles, no env key). This is fail-OPEN, so it
            # must be an explicit opt-in — never the silent default in
            # production (M1). Mirrors AI_ACCOUNTS_ALLOW_NOAUTH for the sidecar.
            # A prod DB that loses its user_roles rows must fail closed, loudly,
            # not silently become unauthenticated-admin.
            if os.environ.get("AGENTED_ALLOW_BOOTSTRAP") == "1":
                logger.warning(
                    "AUTH BOOTSTRAP MODE ACTIVE: no API keys or roles configured "
                    "and AGENTED_ALLOW_BOOTSTRAP=1 — all requests are unauthenticated. "
                    "Never enable this in production."
                )
                await next_app(scope, receive, send)
                return
            await self._unauthorized(send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", ())
        }
        api_key_provided = headers.get("x-api-key", "")
        bearer = ""
        if headers.get("authorization", "").lower().startswith("bearer "):
            bearer = headers["authorization"][7:].strip()

        principal_role: Optional[str] = None
        principal_user_id: Optional[str] = None
        rotated_token: Optional[str] = None
        rotated_cookie_token: Optional[str] = None
        csrf_token_to_set: Optional[str] = None

        # 1) Bearer session path.
        if bearer:
            session = get_session_by_token(bearer)
            if session:
                principal_user_id = session["user_id"]
                principal_role = get_highest_role_for_user(principal_user_id)
                if not hmac.compare_digest(session["token"], bearer):
                    # Grace-window hit: the client still holds the PREVIOUS
                    # token (it missed the rotation response). Resync it to
                    # the current token — re-rotating here would strand it
                    # for good once the grace window closes.
                    rotated_token = session["token"]
                else:
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
            if (
                principal_role is None
                and env_key
                and hmac.compare_digest(api_key_provided, env_key)
            ):
                # Break-glass shared credential: acts as admin by design, but
                # attribute it to a named service identity so audit events are
                # traceable rather than actor=None (H3).
                principal_role = "admin"
                principal_user_id = "service:env-api-key"
            if principal_role is None:
                await self._unauthorized(send)
                return
        # 3) Cookie session path (browser SPA). Subject to CSRF double-submit on
        #    mutating methods, since the cookie is auto-sent by the browser.
        else:
            cookies = parse_cookies(headers.get("cookie", ""))
            cookie_token = cookies.get(SESSION_COOKIE, "")
            if not cookie_token:
                await self._unauthorized(send)
                return
            session = get_session_by_token(cookie_token)
            if not session:
                await self._unauthorized(send)
                return
            if not csrf_valid(method, cookies, headers.get(CSRF_HEADER)):
                await self._forbidden(send, detail="CSRF token missing or invalid")
                return
            principal_user_id = session["user_id"]
            principal_role = get_highest_role_for_user(principal_user_id)
            if not hmac.compare_digest(session["token"], cookie_token):
                # Grace-window hit: the browser still holds the PREVIOUS
                # token (a page-load burst applied Set-Cookie responses out
                # of order, or the rotation response was lost). Resync the
                # cookie to the current token — re-rotating would strand
                # the browser on a dead token when the grace window closes,
                # silently logging the user out.
                rotated_cookie_token = session["token"]
                csrf_token_to_set = cookies.get(CSRF_COOKIE) or generate_csrf_token()
            else:
                rotated = _rotate_session(cookie_token)
                if rotated:
                    rotated_cookie_token = rotated["token"]
                    # Keep the same CSRF token across rotation (it's an independent
                    # secret); refresh its Max-Age. Mint one if somehow absent.
                    csrf_token_to_set = cookies.get(CSRF_COOKIE) or generate_csrf_token()

        # 4) Coarse role check.
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

        # 5) Wrap `send` to inject rotation artifacts on the response start:
        #    the X-New-Session-Token header (header-auth clients) and/or a
        #    Set-Cookie rotation (cookie-auth browser clients).
        scheme = scope.get("scheme", "http")

        async def send_with_rotation(message: Any) -> None:
            if message["type"] == "http.response.start":
                hdrs = list(message.get("headers", []))
                if rotated_token:
                    hdrs.append((b"x-new-session-token", rotated_token.encode("latin-1")))
                if rotated_cookie_token and csrf_token_to_set:
                    hdrs.extend(
                        set_cookie_headers(rotated_cookie_token, csrf_token_to_set, scheme=scheme)
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
    async def _forbidden(send: Send, detail: str = "Forbidden") -> None:
        body = _json_error_body("FORBIDDEN", detail)
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

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
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
# Strict default for the app: NO inline scripts (the Vite-built SPA loads
# module scripts from files). style-src keeps 'unsafe-inline' because Vue's
# `:style` bindings emit inline style attributes. (03-core L1)
_CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "connect-src 'self'",
    ]
)
# Relaxed CSP scoped to Swagger UI under /schema/* (and the /docs alias). Swagger's
# assets are served SAME-ORIGIN (vendored swagger-ui-dist under /schema-assets/, see
# main._openapi_config) — no CDN origin is whitelisted. The only relaxation vs the
# app default `_CSP` is 'unsafe-inline' for script/style, which the Swagger page's
# inline init script (`SwaggerUIBundle({...})`) and inline styles require. img-src
# keeps `data:` for the data-URI favicon.
_CSP_SCHEMA = "; ".join(
    [
        "default-src 'self'",
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

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        if scope["type"] != "http":
            await next_app(scope, receive, send)
            return

        path = scope.get("path", "")
        csp = _CSP_SCHEMA if path.startswith("/schema") or path.startswith("/docs") else _CSP

        async def add_headers(message: Any) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-frame-options", b"DENY"))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"referrer-policy", b"strict-origin-when-cross-origin"))
                headers.append((b"content-security-policy", csp.encode("latin-1")))
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


def _int_env(name: str, default: int) -> int:
    """Read an integer env var; fall back to default + log on parse error."""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r is not an integer; using default %d", name, raw, default)
        return default


# v0.5.14: env-tunable defaults. Read once at module load.
_GET_LIMIT = _int_env("RATE_LIMIT_API_GET_PER_MIN", 60)
_WRITE_LIMIT = _int_env("RATE_LIMIT_API_WRITE_PER_MIN", 30)
_ADMIN_LIMIT = _int_env("RATE_LIMIT_ADMIN_PER_MIN", 30)


# (method, prefix, limit, window_seconds). First method+prefix match wins.
# Method "*" is a wildcard. Existing webhook rules (preserved from wave 77)
# sort first so they take precedence over the broader /api/* defaults.
_RATE_LIMITS: list[tuple[str, str, int, float]] = [
    # Webhook receivers (existing behavior).
    ("POST", "/api/webhooks/github", 30, 60.0),
    ("POST", "/", 20, 10.0),
    # v0.5.14 broad defaults — first specific-method match wins, then *.
    ("GET", "/api/", _GET_LIMIT, 60.0),
    ("POST", "/api/", _WRITE_LIMIT, 60.0),
    ("PUT", "/api/", _WRITE_LIMIT, 60.0),
    ("PATCH", "/api/", _WRITE_LIMIT, 60.0),
    ("DELETE", "/api/", max(1, _WRITE_LIMIT // 2), 60.0),
    ("*", "/admin/", _ADMIN_LIMIT, 60.0),
]


def _client_ip(scope: Scope) -> str:
    # Only trust forwarding headers when explicitly behind a known proxy
    # (AGENTED_TRUST_PROXY=1). Otherwise an attacker rotates X-Forwarded-For per
    # request to mint unlimited fresh rate-limit buckets and defeat the
    # login/reset throttle. Default: use the un-spoofable socket peer.
    client = scope.get("client")
    peer = client[0] if client else "unknown"
    if os.environ.get("AGENTED_TRUST_PROXY") != "1":
        return peer
    headers = {
        k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", ())
    }
    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        # Right-most hop is the one our trusted proxy appended; left-most is
        # client-supplied and spoofable.
        return forwarded.split(",")[-1].strip()
    real = headers.get("x-real-ip")
    if real:
        return real.strip()
    return peer


def _resolve_rate_key(scope: Scope) -> tuple[str, str]:
    """Returns (kind, value).

    Authenticated requests get keyed by user_id (set in scope["state"]
    by ApiKeyMiddleware in v0.5.12). Unauthed routes (login, signup,
    bootstrap mode) fall back to per-IP."""
    state = scope.get("state") or {}
    principal = state.get("principal") if isinstance(state, dict) else None
    if principal and principal.get("user_id"):
        return ("user", principal["user_id"])
    return ("ip", _client_ip(scope))


def _match_rate_limit(method: str, path: str) -> Optional[tuple[int, float]]:
    """Resolve (limit, window) for (method, path). Returns None if no
    rule matches.

    Per-route overrides (registered by `requires_rate_limit` guard)
    win over the coarse defaults table.
    """
    from .rate_limit_guard import get_override

    override = get_override(method, path)
    if override is not None:
        return override
    for rule_method, prefix, limit, window in _RATE_LIMITS:
        method_match = rule_method == method or rule_method == "*"
        if not method_match:
            continue
        if prefix == "/":
            if path == "/":
                return (limit, window)
            continue
        if path.startswith(prefix):
            return (limit, window)
    return None


class RateLimitMiddleware(ASGIMiddleware):
    """v0.5.14: per-key rate limits on /api/* + /admin/* + per-route
    overrides + preserved webhook rules."""

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        if scope["type"] != "http":
            await next_app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")

        rule = _match_rate_limit(method, path)
        if rule is None:
            await next_app(scope, receive, send)
            return
        limit, window = rule

        key_kind, key_val = _resolve_rate_key(scope)
        limiter_key = (f"{key_kind}:{key_val}", path)

        if not _limiter.hit(limiter_key, limit, window):
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


# ---------------------------------------------------------------------------
# Performance / Server-Timing — v0.6.0
# ---------------------------------------------------------------------------


class PerformanceMiddleware(ASGIMiddleware):
    """v0.6.0: emit Server-Timing response header with handler duration.

    Clients (browsers, profile.py) read this to measure per-request
    server-side cost without parsing logs. Adds <1ms overhead.

    v0.6.2: also records each request into the in-process metrics
    registry so /admin/metrics can emit Prometheus-format counters
    + duration histograms.
    """

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        if scope["type"] != "http":
            await next_app(scope, receive, send)
            return

        from time import perf_counter

        started = perf_counter()
        method = scope.get("method", "GET")
        path = scope.get("path", "")
        sent_start = False
        captured_status: int = 0

        async def send_with_timing(message: Any) -> None:
            nonlocal sent_start, captured_status
            if message["type"] == "http.response.start" and not sent_start:
                elapsed_ms = (perf_counter() - started) * 1000.0
                hdrs = list(message.get("headers", []))
                hdrs.append((b"server-timing", f"app;dur={elapsed_ms:.1f}".encode("latin-1")))
                message = {**message, "headers": hdrs}
                captured_status = int(message.get("status", 0))
                sent_start = True
            await send(message)

        try:
            await next_app(scope, receive, send_with_timing)
        finally:
            # v0.6.2: feed the metrics registry post-response. Done in
            # finally so error paths still record. Import is at module
            # load (v0.6.2 round-1 M5) — no per-request import dance.
            try:
                _metrics_registry.record_request(
                    method,
                    path,
                    captured_status or 500,
                    (perf_counter() - started) * 1000.0,
                )
            except Exception:  # noqa: BLE001 — never fail the request on a metric failure
                pass


class SlowRequestMiddleware(ASGIMiddleware):
    """v0.6.2: log WARN on requests slower than SLOW_REQUEST_THRESHOLD_MS.

    Threshold is read once at module load via _int_env. Operator
    bumps it via env to silence false positives during dev.
    """

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        if scope["type"] != "http":
            await next_app(scope, receive, send)
            return

        from time import perf_counter

        threshold_ms = _int_env("SLOW_REQUEST_THRESHOLD_MS", 500)
        started = perf_counter()
        try:
            await next_app(scope, receive, send)
        finally:
            elapsed_ms = (perf_counter() - started) * 1000.0
            if elapsed_ms >= threshold_ms:
                method = scope.get("method", "GET")
                path = scope.get("path", "")
                logger.warning(
                    "slow request: %s %s took %.1fms (threshold %dms)",
                    method,
                    path,
                    elapsed_ms,
                    threshold_ms,
                )


class PolicyMiddleware(ASGIMiddleware):
    """Annotate the request with the active policy/governance scope (23-04).

    LIGHT + NON-BLOCKING: enforcement happens at the action boundaries
    (ExecutionService Popen / goal_loop, 23-03), never here. This middleware
    only makes the policy *scope* observable on the request: when the path
    carries a session id (the session/execution routes) it resolves a small
    scope summary onto ``scope["state"]["policy"]`` + the ``policy_scope_var``
    contextvar, and echoes it as an ``X-Policy-Scope`` response header so
    routes/logging/clients can read which session a request was governed under.

    For any request WITHOUT a session id it is a complete pass-through — no
    state mutation, no extra header, response untouched. It never performs a
    blocking await (a blocking ASK would hold the live output pipe — the rule
    from 23-RESEARCH.md Pitfall 1). Registered AFTER RequestContextMiddleware so
    the request_id/current_user contextvars are already populated.
    """

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        if scope["type"] != "http":
            await next_app(scope, receive, send)
            return

        path = scope.get("path", "")
        match = _SESSION_PATH_RE.search(path)
        if match is None:
            # No session in the path → clean pass-through.
            await next_app(scope, receive, send)
            return

        session_id = match.group(1)
        annotation = {"session_id": session_id, "scope": "session"}
        scope.setdefault("state", {})
        if isinstance(scope["state"], dict):
            scope["state"]["policy"] = annotation
        token = policy_scope_var.set(annotation)

        async def _send_with_policy_header(message: Any) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-policy-scope", f"session:{session_id}".encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await next_app(scope, receive, _send_with_policy_header)
        finally:
            policy_scope_var.reset(token)
