"""Auth dependency reused by the Litestar app.

Both the Flask middleware (wave 21) and these dependencies look up
identity through the same `get_role_and_user_for_api_key` so two
authentication systems can never drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from litestar.connection import Request
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException

from app.db.rbac import count_user_roles, get_role_and_user_for_api_key
from app.db.sessions import get_session_by_token


@dataclass(slots=True, frozen=True)
class Caller:
    """Resolved identity for the current Litestar request.

    `auth_method` describes how the identity was established:
      - "api_key"   — X-API-Key header matched a user_roles row.
      - "session"   — Authorization: Bearer <token> matched a sessions row.
      - "bootstrap" — no roles configured (fresh install).
    """

    api_key: str
    role: str
    user_id: Optional[str]
    auth_method: str = "api_key"


def _resolve_session_token(request: Request) -> Optional[str]:
    """Extract a bearer token from the Authorization header, if present."""
    auth = request.headers.get("Authorization")
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _caller_from_session(token: str) -> Optional[Caller]:
    """Resolve a session token to a Caller. Returns None on miss/expired.

    Default role for session-authenticated users is "viewer" — admin
    operations still need an api-key-with-admin-role mapping. Future
    waves will associate roles directly with users.
    """
    sess = get_session_by_token(token)
    if sess is None:
        return None
    return Caller(
        api_key="session",
        role="viewer",
        user_id=sess["user_id"],
        auth_method="session",
    )


def provide_caller(request: Request) -> Caller:
    """Litestar dependency: yields the authenticated Caller.

    Resolution order:
      1. If no roles are configured at all, bootstrap mode → admin.
      2. Authorization: Bearer <token> against the sessions table.
      3. X-API-Key header against user_roles.
      4. Otherwise 401.
    """
    if count_user_roles() == 0:
        return Caller(
            api_key="bootstrap", role="admin", user_id=None, auth_method="bootstrap"
        )

    token = _resolve_session_token(request)
    if token is not None:
        caller = _caller_from_session(token)
        if caller is not None:
            return caller

    api_key = request.headers.get("X-API-Key")
    if api_key:
        resolved = get_role_and_user_for_api_key(api_key)
        if resolved is not None:
            role, user_id = resolved
            return Caller(
                api_key=api_key,
                role=role,
                user_id=user_id,
                auth_method="api_key",
            )

    raise NotAuthorizedException(detail="Authentication required")


def require_role(*allowed: str):
    """Factory that returns a dependency enforcing one of *allowed* roles."""

    def _dependency(caller: Caller) -> Caller:
        if caller.role not in allowed:
            raise PermissionDeniedException(detail="Insufficient permissions")
        return caller

    return _dependency
