"""RBAC management API endpoints."""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag

from app.models.common import error_response

from ..db.rbac import (
    create_user_role,
    delete_user_role,
    get_user_role,
    list_user_roles,
    update_user_role,
)
from ..models.rbac import RolePath, UserRoleCreate, UserRoleUpdate
from ..services.rbac_service import ROLE_PERMISSIONS, require_role

tag = Tag(name="rbac", description="Role-Based Access Control management")
rbac_bp = APIBlueprint("rbac", __name__, url_prefix="/admin/rbac", abp_tags=[tag])


@rbac_bp.get("/roles")
@require_role("admin")
def list_roles():
    """List all user roles."""
    roles = list_user_roles()
    return {"roles": roles}, HTTPStatus.OK


@rbac_bp.post("/roles")
@require_role("admin")
def create_role(body: UserRoleCreate):
    """Create a new user role mapping."""
    role_id = create_user_role(
        api_key=body.api_key,
        label=body.label,
        role=body.role,
    )
    if not role_id:
        return error_response(
            "CONFLICT", "Failed to create role (duplicate API key?)", HTTPStatus.CONFLICT
        )
    role = get_user_role(role_id)
    return {"message": "Role created", "role": role}, HTTPStatus.CREATED


@rbac_bp.get("/roles/<role_id>")
@require_role("admin")
def get_role_detail(path: RolePath):
    """Get a single user role by ID."""
    role = get_user_role(path.role_id)
    if not role:
        return error_response("NOT_FOUND", "Role not found", HTTPStatus.NOT_FOUND)
    return role, HTTPStatus.OK


@rbac_bp.put("/roles/<role_id>")
@require_role("admin")
def update_role(path: RolePath, body: UserRoleUpdate):
    """Update a user role."""
    if not update_user_role(path.role_id, label=body.label, role=body.role):
        return error_response("NOT_FOUND", "Role not found or no changes", HTTPStatus.NOT_FOUND)
    role = get_user_role(path.role_id)
    return role, HTTPStatus.OK


@rbac_bp.delete("/roles/<role_id>")
@require_role("admin")
def delete_role(path: RolePath):
    """Delete a user role."""
    if not delete_user_role(path.role_id):
        return error_response("NOT_FOUND", "Role not found", HTTPStatus.NOT_FOUND)
    return {"message": "Role deleted"}, HTTPStatus.OK


@rbac_bp.get("/permissions")
@require_role("viewer", "operator", "editor", "admin")
def get_permissions():
    """Return the RBAC permission matrix."""
    # Convert sets to lists for JSON serialization
    matrix = {role: sorted(perms) for role, perms in ROLE_PERMISSIONS.items()}
    return {"permissions": matrix}, HTTPStatus.OK
