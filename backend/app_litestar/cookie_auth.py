"""HttpOnly session cookie + double-submit CSRF helpers.

Migrates the session token out of the browser's localStorage (XSS-exfiltratable)
into an HttpOnly cookie, paired with a readable CSRF token the frontend echoes
in the ``X-CSRF-Token`` header on mutating requests. The middleware verifies the
header matches the CSRF cookie (double-submit) for cookie-authenticated writes.

Header-authenticated requests (X-API-Key / Authorization: Bearer) are exempt
from CSRF — those credentials are never auto-sent by the browser cross-site, so
they carry no CSRF risk.
"""

from __future__ import annotations

import hmac
import os
import secrets

SESSION_COOKIE = "agented_session"
CSRF_COOKIE = "agented_csrf"
CSRF_HEADER = "x-csrf-token"

# Mutating methods that require a CSRF token on the cookie auth path.
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Cookie lifetime (seconds). Matches a generous session window; the session row
# itself still governs actual validity server-side.
COOKIE_MAX_AGE = 7 * 24 * 3600


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def parse_cookies(raw_cookie_header: str) -> dict[str, str]:
    """Parse a raw Cookie header into {name: value}. Tolerant of stray spaces."""
    out: dict[str, str] = {}
    if not raw_cookie_header:
        return out
    for part in raw_cookie_header.split(";"):
        if "=" not in part:
            continue
        name, _, value = part.partition("=")
        out[name.strip()] = value.strip()
    return out


def cookie_secure(scheme: str) -> bool:
    """Whether to set the Secure flag.

    AGENTED_COOKIE_SECURE forces it (1/0). Otherwise it follows the request
    scheme — Secure over HTTPS (prod), not over HTTP (local dev), so the same
    code works in both without locking dev out.
    """
    forced = os.environ.get("AGENTED_COOKIE_SECURE")
    if forced is not None:
        return forced == "1"
    return scheme == "https"


def _cookie(name: str, value: str, *, http_only: bool, secure: bool, max_age: int) -> bytes:
    attrs = [f"{name}={value}", "Path=/", "SameSite=Strict", f"Max-Age={max_age}"]
    if http_only:
        attrs.append("HttpOnly")
    if secure:
        attrs.append("Secure")
    return "; ".join(attrs).encode("latin-1")


def set_cookie_headers(
    session_token: str, csrf_token: str, *, scheme: str, max_age: int = COOKIE_MAX_AGE
) -> list[tuple[bytes, bytes]]:
    """Set-Cookie headers for the HttpOnly session + readable CSRF cookies."""
    secure = cookie_secure(scheme)
    return [
        (
            b"set-cookie",
            _cookie(SESSION_COOKIE, session_token, http_only=True, secure=secure, max_age=max_age),
        ),
        # CSRF cookie is intentionally readable by JS (not HttpOnly) so the SPA
        # can echo it in the X-CSRF-Token header.
        (
            b"set-cookie",
            _cookie(CSRF_COOKIE, csrf_token, http_only=False, secure=secure, max_age=max_age),
        ),
    ]


def clear_cookie_headers(scheme: str) -> list[tuple[bytes, bytes]]:
    secure = cookie_secure(scheme)
    return [
        (b"set-cookie", _cookie(SESSION_COOKIE, "", http_only=True, secure=secure, max_age=0)),
        (b"set-cookie", _cookie(CSRF_COOKIE, "", http_only=False, secure=secure, max_age=0)),
    ]


def litestar_cookies(
    session_token: str, csrf_token: str, *, secure: bool, max_age: int = COOKIE_MAX_AGE
):
    """Litestar ``Cookie`` objects for use in route handler responses."""
    from litestar.datastructures import Cookie

    return [
        Cookie(
            key=SESSION_COOKIE,
            value=session_token,
            httponly=True,
            secure=secure,
            samesite="strict",
            path="/",
            max_age=max_age,
        ),
        Cookie(
            key=CSRF_COOKIE,
            value=csrf_token,
            httponly=False,
            secure=secure,
            samesite="strict",
            path="/",
            max_age=max_age,
        ),
    ]


def litestar_clear_cookies(*, secure: bool):
    return litestar_cookies("", "", secure=secure, max_age=0)


def csrf_valid(method: str, cookies: dict[str, str], csrf_header: str | None) -> bool:
    """Double-submit check: for a mutating method, the X-CSRF-Token header must
    match the CSRF cookie (constant-time). Safe methods always pass."""
    if method.upper() not in UNSAFE_METHODS:
        return True
    cookie_token = cookies.get(CSRF_COOKIE)
    if not cookie_token or not csrf_header:
        return False
    return hmac.compare_digest(cookie_token, csrf_header)
