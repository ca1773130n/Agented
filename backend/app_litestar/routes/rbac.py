"""RBAC routes ported from Flask (track A — wave 23 migration target).

Both apps source the permission matrix from the same module
(``app.services.rbac_service.ROLE_PERMISSIONS``) so responses are
byte-identical regardless of which port the frontend hits during the
transition.
"""

from __future__ import annotations

from typing import Any

from litestar import Router, get

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


rbac_router = Router(path="/admin/rbac", route_handlers=[get_permissions])
