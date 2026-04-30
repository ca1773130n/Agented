"""Auth routes — POST /api/auth/login (track B, wave 32).

Login takes email + password, validates against the bcrypt hash on
users (wave 31), and issues a session token. The session token is the
authoritative identity for subsequent calls; wave 33 adds the verifying
dependency.
"""

from __future__ import annotations

from typing import Any

from litestar import Router, post
from litestar.exceptions import NotAuthorizedException
from msgspec import Struct

from app.db.sessions import create_session
from app.db.users import authenticate


class LoginBody(Struct):
    email: str
    password: str


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


auth_router = Router(path="/api/auth", route_handlers=[login])
