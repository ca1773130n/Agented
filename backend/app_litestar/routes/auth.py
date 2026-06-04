"""Auth routes — POST /api/auth/login (track B, wave 32).

Login takes email + password, validates against the bcrypt hash on
users (wave 31), and issues a session token. The session token is the
authoritative identity for subsequent calls; wave 33 adds the verifying
dependency.
"""

from __future__ import annotations

from typing import Any

from litestar import Request, Router, get, post
from litestar.exceptions import ClientException, NotAuthorizedException
from litestar.status_codes import HTTP_204_NO_CONTENT
from msgspec import Struct

import logging

from app.db.password_resets import consume_token, request_reset
from app.db.sessions import create_session, revoke_session, revoke_user_sessions
from app_litestar.rate_limit_guard import requires_rate_limit
from app.db.users import (
    authenticate,
    create_user,
    get_user,
    get_user_by_email,
    set_password,
)

_auth_logger = logging.getLogger("app.auth")

from ..auth import Caller, _resolve_session_token


class LoginBody(Struct):
    email: str
    password: str


class SignupBody(Struct):
    email: str
    password: str
    display_name: str = ""


_MIN_PASSWORD_LEN = 8

# Per-email fixed-window throttle (02 H1), complementing the per-IP limiter:
# the IP key alone is defeatable behind NAT/proxies, so also cap attempts per
# target email for login + password-reset (credential stuffing / reset spam).
import threading as _threading  # noqa: E402
import time as _time  # noqa: E402

_email_attempts: dict[str, list[float]] = {}
_email_attempts_lock = _threading.Lock()
_EMAIL_WINDOW_SECONDS = 300.0
_EMAIL_MAX_ATTEMPTS = 10


def _email_throttled(email: str) -> bool:
    """Record an attempt for *email*; return True if over the window limit."""
    key = (email or "").strip().lower()
    if not key:
        return False
    now = _time.time()
    with _email_attempts_lock:
        # Opportunistic eviction so the dict stays bounded.
        if len(_email_attempts) > 10000:
            _email_attempts.clear()
        hits = [t for t in _email_attempts.get(key, []) if now - t < _EMAIL_WINDOW_SECONDS]
        hits.append(now)
        _email_attempts[key] = hits
        return len(hits) > _EMAIL_MAX_ATTEMPTS


def _session_response(payload: dict, session_token: str, request: Request):
    """Wrap a login/signup payload in a Response that sets the HttpOnly session
    cookie + readable CSRF cookie. The CSRF token is also echoed in the body so
    the SPA can use it immediately. The bearer ``token`` stays in the body for
    backward compatibility with header-auth clients during rollout."""
    from litestar import Response

    from app_litestar.cookie_auth import cookie_secure, generate_csrf_token, litestar_cookies

    csrf = generate_csrf_token()
    secure = cookie_secure(request.url.scheme)
    body = {**payload, "csrf_token": csrf}
    return Response(content=body, cookies=litestar_cookies(session_token, csrf, secure=secure))


@post("/signup", sync_to_thread=False, guards=[requires_rate_limit(5, 60.0)])
def signup(data: SignupBody, request: Request) -> Any:
    """Open registration: create user + immediately issue a session token.

    Validation:
      - email must contain '@' and be unique (case-insensitive).
      - password must be at least 8 characters.

    Returns the same shape as /login so the frontend can use one
    success handler.
    """
    email = data.email.strip()
    if not email or "@" not in email:
        raise ClientException(detail="Invalid email")
    if len(data.password) < _MIN_PASSWORD_LEN:
        raise ClientException(
            detail=f"Password must be at least {_MIN_PASSWORD_LEN} characters",
        )
    if get_user_by_email(email) is not None:
        raise ClientException(detail="Email already registered")

    display_name = data.display_name.strip() or None
    user_id = create_user(email, display_name)
    if user_id is None:
        raise ClientException(detail="Could not create account")
    if not set_password(user_id, data.password):
        raise ClientException(detail="Could not set password")

    user = get_user(user_id)
    session = create_session(user_id)
    if session is None or user is None:
        raise ClientException(detail="Session creation failed")

    payload = {
        "token": session["token"],
        "expires_at": session["expires_at"],
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name"),
        },
    }
    return _session_response(payload, session["token"], request)


@post("/login", sync_to_thread=False, guards=[requires_rate_limit(5, 60.0)])
def login(data: LoginBody, request: Request) -> Any:
    """Verify credentials and issue a session token.

    401 on bad credentials (same response shape regardless of the cause —
    user not found, wrong password, inactive, no hash set).
    """
    if _email_throttled(data.email):
        raise ClientException(detail="Too many attempts for this account; try again later")
    user = authenticate(data.email, data.password)
    if user is None:
        raise NotAuthorizedException(detail="Invalid email or password")

    session = create_session(user["id"])
    if session is None:
        raise NotAuthorizedException(detail="Session creation failed")

    payload = {
        "token": session["token"],
        "expires_at": session["expires_at"],
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name"),
        },
    }
    return _session_response(payload, session["token"], request)


@get("/me", sync_to_thread=False)
def me(caller: Caller) -> dict[str, Any]:
    """Return the authenticated user's profile.

    Works with either auth method (session token or API key). For api-key
    callers without an associated user_id (legacy single-user setups),
    returns a sentinel id so the frontend can still render something.
    """
    if caller.user_id is None:
        return {
            "id": None,
            "email": None,
            "display_name": None,
            "auth_method": caller.auth_method,
        }
    user = get_user(caller.user_id)
    if user is None:
        raise NotAuthorizedException(detail="User no longer exists")
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user.get("display_name"),
        "auth_method": caller.auth_method,
    }


@post("/logout", status_code=HTTP_204_NO_CONTENT, sync_to_thread=False)
def logout(request: Request) -> None:
    """Revoke the caller's sessions. Always 204.

    v0.5.12: revoke by user_id from middleware-stashed principal because
    the bearer in the Authorization header has already been rotated by
    the middleware (the original token now lives in `rotated_from_token`,
    not `token`). When there's no principal (bootstrap mode), resolve
    the token to a user and still revoke ALL their sessions — same
    contract as the authenticated path.
    """
    from litestar import Response

    from app.db.sessions import get_session_by_token
    from app_litestar.cookie_auth import cookie_secure, litestar_clear_cookies, parse_cookies

    # Clear the auth cookies on the way out regardless of which path revokes.
    cleared = Response(
        content=None,
        status_code=HTTP_204_NO_CONTENT,
        cookies=litestar_clear_cookies(secure=cookie_secure(request.url.scheme)),
    )

    principal = request.scope.get("state", {}).get("principal")
    user_id = principal.get("user_id") if principal else None
    if not user_id:
        # Header bearer first, then the session cookie (browser SPA).
        token = _resolve_session_token(request)
        if not token:
            token = parse_cookies(request.headers.get("cookie", "")).get("agented_session")
        if token:
            session = get_session_by_token(token)
            if session:
                user_id = session["user_id"]
            else:
                revoke_session(token, reason="logout")
                return cleared
    if user_id:
        revoke_user_sessions(user_id, reason="logout")
    return cleared


class ForgotPasswordBody(Struct):
    email: str


class ResetPasswordBody(Struct):
    token: str
    password: str


@post(
    "/forgot-password",
    status_code=HTTP_204_NO_CONTENT,
    sync_to_thread=False,
    guards=[requires_rate_limit(3, 60.0)],
)
def forgot_password(data: ForgotPasswordBody) -> None:
    """Issue a password-reset token for *email* if it exists.

    Always returns 204, regardless of whether the email is in the DB.
    Defends against email enumeration. The reset link is logged to
    stderr (no SMTP in this codebase yet — operators read the log).
    """
    # Per-email throttle (02 H1) — still return 204 to preserve enumeration
    # resistance, but silently skip issuing when the email is over the limit.
    if _email_throttled(data.email):
        return None
    user = get_user_by_email(data.email)
    if user is not None and user.get("is_active"):
        token = request_reset(user["id"])
        if token:
            # Never log the token to the general app log: it grants account
            # takeover and persists in log aggregation/SIEM far beyond its TTL
            # (H4). With no SMTP yet, write the link to a restricted 0600 file
            # that only operators with filesystem access can read. Log only
            # the user id, no token.
            _deliver_reset_token(user["id"], token)
            _auth_logger.info("Password reset requested for user %s", user["id"])
    return None


def _deliver_reset_token(user_id: str, token: str) -> None:
    """Out-of-band delivery of a reset token until SMTP exists.

    Writes the reset link to a per-user, owner-only (0600) file under a
    restricted directory rather than the shared application log.
    """
    import os
    import tempfile

    out_dir = os.environ.get(
        "AGENTED_RESET_TOKEN_DIR", os.path.join(tempfile.gettempdir(), "agented-reset-tokens")
    )
    try:
        os.makedirs(out_dir, mode=0o700, exist_ok=True)
        path = os.path.join(out_dir, f"{user_id}.link")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, f"/reset-password?token={token}\n".encode())
        finally:
            os.close(fd)
    except OSError as exc:
        # Don't leak the token into the failure log either.
        _auth_logger.error("Failed to write reset token for user %s: %s", user_id, exc)


@post(
    "/reset-password",
    status_code=HTTP_204_NO_CONTENT,
    sync_to_thread=False,
    guards=[requires_rate_limit(5, 60.0)],
)
def reset_password(data: ResetPasswordBody) -> None:
    """Consume a reset token and set the new password."""
    if len(data.password) < 8:
        raise ClientException(detail="Password must be at least 8 characters")
    user_id = consume_token(data.token)
    if user_id is None:
        raise NotAuthorizedException(detail="Invalid or expired token")
    if not set_password(user_id, data.password):
        raise ClientException(detail="Could not update password")
    return None


auth_router = Router(
    path="/api/auth",
    route_handlers=[login, signup, me, logout, forgot_password, reset_password],
)
