"""RBAC routes ported from Flask (track A — wave 23 migration target).

Both apps source the permission matrix from the same module
(``app.services.rbac_service.ROLE_PERMISSIONS``) so responses are
byte-identical regardless of which port the frontend hits during the
transition.
"""

from __future__ import annotations

from typing import Any

from litestar import Router, get, post
from litestar.exceptions import NotFoundException

from app.db.rbac import rotate_user_role
from app.services.rbac_service import ROLE_PERMISSIONS

from ..auth import Caller, require_role


@get(
    "/permissions",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def get_permissions(authorized: Caller) -> dict[str, Any]:
    """Return the RBAC permission matrix — read access for any authenticated role."""
    del authorized  # presence enforces the role check; body doesn't need it
    matrix = {role: sorted(perms) for role, perms in ROLE_PERMISSIONS.items()}
    return {"permissions": matrix}


@post(
    "/roles/{role_id:str}/rotate",
    dependencies={"authorized": require_role("admin")},
    sync_to_thread=False,
)
def rotate_role(role_id: str, authorized: Caller) -> dict[str, Any]:
    """Rotate the API key for a role — admin-only.

    Mirrors the Flask version (wave 8): atomic swap, returns the new
    record. 404 when role_id is unknown; 403 when caller is not admin
    (handled by require_role); 401 when no/invalid key (handled by
    provide_caller).
    """
    del authorized
    new_role = rotate_user_role(role_id)
    if not new_role:
        raise NotFoundException(detail="Role not found")
    return {"message": "Key rotated", "role": new_role}


rbac_router = Router(path="/admin/rbac", route_handlers=[get_permissions, rotate_role])
