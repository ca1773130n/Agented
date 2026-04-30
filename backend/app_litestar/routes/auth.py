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

from app.db.sessions import create_session, revoke_session
from app.db.users import (
    authenticate,
    create_user,
    get_user,
    get_user_by_email,
    set_password,
)

from ..auth import Caller, _resolve_session_token


class LoginBody(Struct):
    email: str
    password: str


class SignupBody(Struct):
    email: str
    password: str
    display_name: str = ""


_MIN_PASSWORD_LEN = 8


@post("/signup", sync_to_thread=False)
def signup(data: SignupBody) -> dict:
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

    return {
        "token": session["token"],
        "expires_at": session["expires_at"],
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name"),
        },
    }


@post("/login", sync_to_thread=False)
def login(data: LoginBody) -> dict[str, Any]:
    """Verify credentials and issue a session token.

    401 on bad credentials (same response shape regardless of the cause —
    user not found, wrong password, inactive, no hash set).
    """
    user = authenticate(data.email, data.password)
    if user is None:
        raise NotAuthorizedException(detail="Invalid email or password")

    session = create_session(user["id"])
    if session is None:
        raise NotAuthorizedException(detail="Session creation failed")

    return {
        "token": session["token"],
        "expires_at": session["expires_at"],
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name"),
        },
    }


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
    """Revoke the current session token if present. Always 204."""
    token = _resolve_session_token(request)
    if token:
        revoke_session(token)
    return None


auth_router = Router(path="/api/auth", route_handlers=[login, signup, me, logout])
