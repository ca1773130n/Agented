"""Team edge (directed graph) API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    add_team_edge,
    delete_team_edge,
    delete_team_edges_by_team,
    get_team_edges,
)
from ..models.common import error_response
from ..models.team import VALID_EDGE_TYPES
from ..services.rbac_service import require_role
from .teams import TeamPath

tag = Tag(name="team-edges", description="Team directed graph edge management")
team_edges_bp = APIBlueprint("team_edges", __name__, url_prefix="/admin/teams", abp_tags=[tag])


class EdgePath(BaseModel):
    team_id: str = Field(..., description="Team ID")
    edge_id: int = Field(..., description="Edge ID")


@team_edges_bp.get("/<team_id>/edges")
@require_role("viewer", "operator", "editor", "admin")
def list_edges(path: TeamPath):
    """List all edges for a team."""
    edges = get_team_edges(path.team_id)
    return {"edges": edges}, HTTPStatus.OK


@team_edges_bp.post("/<team_id>/edges")
@require_role("editor", "admin")
def create_edge(path: TeamPath):
    """Create a directed edge between two team members."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    source_member_id = data.get("source_member_id")
    target_member_id = data.get("target_member_id")
    edge_type = data.get("edge_type", "delegation")

    if source_member_id is None or target_member_id is None:
        return error_response(
            "BAD_REQUEST",
            "source_member_id and target_member_id are required",
            HTTPStatus.BAD_REQUEST,
        )

    if edge_type not in VALID_EDGE_TYPES:
        return error_response(
            "BAD_REQUEST",
            f"Invalid edge_type. Must be one of: {', '.join(VALID_EDGE_TYPES)}",
            HTTPStatus.BAD_REQUEST,
        )

    edge_id = add_team_edge(
        team_id=path.team_id,
        source_member_id=source_member_id,
        target_member_id=target_member_id,
        edge_type=edge_type,
        label=data.get("label"),
        weight=data.get("weight", 1),
    )
    if edge_id is None:
        return error_response(
            "BAD_REQUEST", "Failed to create edge (self-loop or duplicate)", HTTPStatus.BAD_REQUEST
        )

    # Fetch the created edge
    edges = get_team_edges(path.team_id)
    edge = next((e for e in edges if e["id"] == edge_id), None)
    return {"message": "Edge created", "edge": edge}, HTTPStatus.CREATED


@team_edges_bp.delete("/<team_id>/edges/<int:edge_id>")
@require_role("editor", "admin")
def delete_edge(path: EdgePath):
    """Delete a single edge."""
    if not delete_team_edge(path.edge_id):
        return error_response("NOT_FOUND", "Edge not found", HTTPStatus.NOT_FOUND)
    return {"message": "Edge deleted"}, HTTPStatus.OK


@team_edges_bp.delete("/<team_id>/edges")
@require_role("editor", "admin")
def bulk_delete_edges(path: TeamPath):
    """Bulk delete all edges for a team."""
    deleted_count = delete_team_edges_by_team(path.team_id)
    return {
        "message": f"Deleted {deleted_count} edge(s)",
        "deleted_count": deleted_count,
    }, HTTPStatus.OK
