"""Team member management API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    add_team_member,
    get_team_members,
    remove_team_member,
    update_team_member,
)
from ..models.common import error_response
from ..services.rbac_service import require_role
from .teams import TeamPath

tag = Tag(name="team-members", description="Team member management")
team_members_bp = APIBlueprint("team_members", __name__, url_prefix="/admin/teams", abp_tags=[tag])


class MemberPath(BaseModel):
    team_id: str = Field(..., description="Team ID")
    member_id: int = Field(..., description="Member ID")


@team_members_bp.get("/<team_id>/members")
@require_role("viewer", "operator", "editor", "admin")
def list_members(path: TeamPath):
    """List team members."""
    members = get_team_members(path.team_id)
    return {"members": members}, HTTPStatus.OK


@team_members_bp.post("/<team_id>/members")
@require_role("admin")
def add_member(path: TeamPath):
    """Add a member to the team."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    name = data.get("name")
    agent_id = data.get("agent_id")
    super_agent_id = data.get("super_agent_id")

    # At least one identifier is required
    if not name and not agent_id and not super_agent_id:
        return error_response(
            "BAD_REQUEST", "name, agent_id, or super_agent_id is required", HTTPStatus.BAD_REQUEST
        )

    member_id = add_team_member(
        team_id=path.team_id,
        name=name,
        email=data.get("email"),
        role=data.get("role", "member"),
        layer=data.get("layer", "backend"),
        description=data.get("description"),
        agent_id=agent_id,
        super_agent_id=super_agent_id,
        tier=data.get("tier"),
    )
    if not member_id:
        return error_response(
            "INTERNAL_SERVER_ERROR", "Failed to add member", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    # Return the member data
    members = get_team_members(path.team_id)
    member = next((m for m in members if m["id"] == member_id), None)
    return {"message": "Member added", "member": member}, HTTPStatus.CREATED


@team_members_bp.put("/<team_id>/members/<int:member_id>")
@require_role("admin")
def update_member(path: MemberPath):
    """Update a team member."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    if not update_team_member(
        path.member_id,
        name=data.get("name"),
        email=data.get("email"),
        role=data.get("role"),
        layer=data.get("layer"),
        description=data.get("description"),
        tier=data.get("tier"),
    ):
        return error_response(
            "NOT_FOUND", "Member not found or no changes made", HTTPStatus.NOT_FOUND
        )

    members = get_team_members(path.team_id)
    member = next((m for m in members if m["id"] == path.member_id), None)
    return {"member": member}, HTTPStatus.OK


@team_members_bp.delete("/<team_id>/members/<int:member_id>")
@require_role("admin")
def delete_member(path: MemberPath):
    """Remove a member from the team."""
    if not remove_team_member(path.member_id):
        return error_response("NOT_FOUND", "Member not found", HTTPStatus.NOT_FOUND)
    return {"message": "Member removed"}, HTTPStatus.OK
