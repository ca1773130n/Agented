"""RBAC routes ported from Flask (track A — wave 23 migration target).

Both apps source the permission matrix from the same module
(``app.services.rbac_service.ROLE_PERMISSIONS``) so responses are
byte-identical regardless of which port the frontend hits during the
transition.
"""

from __future__ import annotations

from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import ClientException, NotFoundException
from msgspec import Struct

from app.db.rbac import (
    create_user_role,
    delete_user_role,
    get_user_role,
    list_user_roles,
    rotate_user_role,
    update_user_role,
)
from app.models.rbac import ALLOWED_ROLES
from app.services.rbac_service import ROLE_PERMISSIONS

from ..auth import Caller, require_role


class CreateRoleBody(Struct):
    api_key: str
    label: str
    role: str = "viewer"


class UpdateRoleBody(Struct):
    label: Optional[str] = None
    role: Optional[str] = None


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


@get(
    "/roles",
    dependencies={"authorized": require_role("admin")},
    sync_to_thread=False,
)
def list_roles(authorized: Caller) -> dict[str, Any]:
    """List all user role records — admin-only."""
    del authorized
    return {"roles": list_user_roles()}


@get(
    "/roles/{role_id:str}",
    dependencies={"authorized": require_role("admin")},
    sync_to_thread=False,
)
def get_role_detail(role_id: str, authorized: Caller) -> dict[str, Any]:
    """Fetch a single user_role record by id — admin-only."""
    del authorized
    role = get_user_role(role_id)
    if role is None:
        raise NotFoundException(detail="Role not found")
    return role


@post(
    "/roles",
    dependencies={"authorized": require_role("admin")},
    sync_to_thread=False,
)
def create_role(data: CreateRoleBody, authorized: Caller) -> dict[str, Any]:
    """Create a new user_role mapping — admin-only."""
    del authorized
    if data.role not in ALLOWED_ROLES:
        raise ClientException(detail=f"role must be one of {ALLOWED_ROLES}")
    role_id = create_user_role(api_key=data.api_key, label=data.label, role=data.role)
    if not role_id:
        raise ClientException(detail="Failed to create role (duplicate API key?)")
    role = get_user_role(role_id)
    return {"message": "Role created", "role": role}


@put(
    "/roles/{role_id:str}",
    dependencies={"authorized": require_role("admin")},
    sync_to_thread=False,
)
def update_role(role_id: str, data: UpdateRoleBody, authorized: Caller) -> dict[str, Any]:
    """Update a role's label and/or role grant — admin-only."""
    del authorized
    if data.role is not None and data.role not in ALLOWED_ROLES:
        raise ClientException(detail=f"role must be one of {ALLOWED_ROLES}")
    if not update_user_role(role_id, label=data.label, role=data.role):
        raise NotFoundException(detail="Role not found or no changes")
    role = get_user_role(role_id)
    return role  # type: ignore[return-value]


@delete(
    "/roles/{role_id:str}",
    dependencies={"authorized": require_role("admin")},
    status_code=200,
    sync_to_thread=False,
)
def remove_role(role_id: str, authorized: Caller) -> dict[str, Any]:
    """Delete a user_role mapping — admin-only."""
    del authorized
    if not delete_user_role(role_id):
        raise NotFoundException(detail="Role not found")
    return {"message": "Role deleted"}


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


rbac_router = Router(
    path="/admin/rbac",
    route_handlers=[
        get_permissions,
        list_roles,
        get_role_detail,
        create_role,
        update_role,
        remove_role,
        rotate_role,
    ],
)
