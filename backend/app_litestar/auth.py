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


@dataclass(slots=True, frozen=True)
class Caller:
    """Resolved identity for the current Litestar request."""

    api_key: str
    role: str
    user_id: Optional[str]


def provide_caller(request: Request) -> Caller:
    """Litestar dependency: yields the authenticated Caller.

    Behaviour mirrors Flask's @require_role:
      - If no roles exist in the database, every request is treated as
        admin (graceful bootstrap mode for fresh installs).
      - Missing/unknown X-API-Key → 401.
    """
    if count_user_roles() == 0:
        return Caller(api_key="bootstrap", role="admin", user_id=None)

    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise NotAuthorizedException(detail="API key required")

    resolved = get_role_and_user_for_api_key(api_key)
    if resolved is None:
        raise NotAuthorizedException(detail="Invalid API key")

    role, user_id = resolved
    return Caller(api_key=api_key, role=role, user_id=user_id)


def require_role(*allowed: str):
    """Factory that returns a dependency enforcing one of *allowed* roles."""

    def _dependency(caller: Caller) -> Caller:
        if caller.role not in allowed:
            raise PermissionDeniedException(detail="Insufficient permissions")
        return caller

    return _dependency
