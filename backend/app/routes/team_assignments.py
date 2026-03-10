"""Team agent assignment API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    VALID_ENTITY_TYPES,
    add_team_agent_assignment,
    delete_team_agent_assignment,
    delete_team_agent_assignments_bulk,
    get_team,
    get_team_agent_assignments,
)
from ..models.common import error_response
from ..services.rbac_service import require_role
from ..services.team_service import TeamService
from .teams import TeamPath

tag = Tag(name="team-assignments", description="Team agent assignment management")
team_assignments_bp = APIBlueprint(
    "team_assignments", __name__, url_prefix="/admin/teams", abp_tags=[tag]
)


class TeamAgentPath(BaseModel):
    team_id: str = Field(..., description="Team ID")
    agent_id: str = Field(..., description="Agent ID")


class AssignmentPath(BaseModel):
    team_id: str = Field(..., description="Team ID")
    assignment_id: int = Field(..., description="Assignment ID")


@team_assignments_bp.post("/<team_id>/agents/<agent_id>/assignments")
@require_role("admin")
def add_agent_assignment(path: TeamAgentPath):
    """Add an entity assignment (skill/command/hook/rule) for an agent within a team."""
    team = get_team(path.team_id)
    if not team:
        return error_response("NOT_FOUND", "Team not found", HTTPStatus.NOT_FOUND)

    if not TeamService.is_agent_team_member(path.team_id, path.agent_id):
        return error_response(
            "BAD_REQUEST", "Agent is not a member of this team", HTTPStatus.BAD_REQUEST
        )

    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")

    if not entity_type or not entity_id:
        return error_response(
            "BAD_REQUEST", "entity_type and entity_id are required", HTTPStatus.BAD_REQUEST
        )

    if entity_type not in VALID_ENTITY_TYPES:
        return error_response(
            "BAD_REQUEST",
            f"Invalid entity_type. Must be one of: {', '.join(VALID_ENTITY_TYPES)}",
            HTTPStatus.BAD_REQUEST,
        )

    assignment_id = add_team_agent_assignment(
        team_id=path.team_id,
        agent_id=path.agent_id,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=data.get("entity_name"),
    )

    if assignment_id is None:
        return error_response(
            "CONFLICT", "Assignment already exists or failed to create", HTTPStatus.CONFLICT
        )

    # Fetch the created assignment
    assignments = get_team_agent_assignments(path.team_id, path.agent_id)
    assignment = next((a for a in assignments if a["id"] == assignment_id), None)

    return {
        "message": "Assignment added",
        "assignment": assignment,
    }, HTTPStatus.CREATED


@team_assignments_bp.get("/<team_id>/agents/<agent_id>/assignments")
@require_role("viewer", "operator", "editor", "admin")
def list_agent_assignments(path: TeamAgentPath):
    """List assignments for an agent within a team."""
    assignments = get_team_agent_assignments(path.team_id, path.agent_id)
    return {"assignments": assignments}, HTTPStatus.OK


@team_assignments_bp.get("/<team_id>/assignments")
@require_role("viewer", "operator", "editor", "admin")
def list_team_assignments(path: TeamPath):
    """List all assignments for a team across all agents."""
    assignments = get_team_agent_assignments(path.team_id)
    return {"assignments": assignments}, HTTPStatus.OK


@team_assignments_bp.delete("/<team_id>/assignments/<int:assignment_id>")
@require_role("admin")
def delete_assignment(path: AssignmentPath):
    """Delete a single assignment."""
    if not delete_team_agent_assignment(path.assignment_id):
        return error_response("NOT_FOUND", "Assignment not found", HTTPStatus.NOT_FOUND)
    return {"message": "Assignment deleted"}, HTTPStatus.OK


@team_assignments_bp.delete("/<team_id>/agents/<agent_id>/assignments")
@require_role("admin")
def bulk_delete_agent_assignments(path: TeamAgentPath):
    """Bulk delete assignments for an agent in a team. Optional query param entity_type."""
    entity_type = request.args.get("entity_type")
    deleted_count = delete_team_agent_assignments_bulk(
        team_id=path.team_id,
        agent_id=path.agent_id,
        entity_type=entity_type,
    )
    return {
        "message": f"Deleted {deleted_count} assignment(s)",
        "deleted_count": deleted_count,
    }, HTTPStatus.OK
