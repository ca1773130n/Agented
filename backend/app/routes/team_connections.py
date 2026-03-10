"""Team inter-connection API endpoints."""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..models.common import error_response
from ..services.rbac_service import require_role
from .teams import TeamPath

tag = Tag(name="team-connections", description="Inter-team connection management")
team_connections_bp = APIBlueprint(
    "team_connections", __name__, url_prefix="/admin/teams", abp_tags=[tag]
)


class ConnectionPath(BaseModel):
    team_id: str = Field(..., description="Team ID")
    connection_id: int = Field(..., description="Connection ID")


class TeamConnectionBody(BaseModel):
    target_team_id: str = Field(..., description="ID of the target team")
    connection_type: str = Field("dependency", description="Type of connection")
    description: str = Field(None, description="Optional description")


@team_connections_bp.get("/<team_id>/connections")
@require_role("viewer", "operator", "editor", "admin")
def list_team_connections(path: TeamPath):
    """List inter-team connections for a team."""
    from ..db.rotations import get_team_connections

    connections = get_team_connections(path.team_id)
    return {"connections": connections}, HTTPStatus.OK


@team_connections_bp.post("/<team_id>/connections")
@require_role("admin")
def create_team_connection(path: TeamPath, body: TeamConnectionBody):
    """Create an inter-team connection."""
    from ..db.rotations import add_team_connection

    conn_id = add_team_connection(
        source_team_id=path.team_id,
        target_team_id=body.target_team_id,
        connection_type=body.connection_type,
        description=body.description,
    )
    if not conn_id:
        return error_response("BAD_REQUEST", "Failed to create connection", HTTPStatus.BAD_REQUEST)
    return {"message": "Connection created", "id": conn_id}, HTTPStatus.CREATED


@team_connections_bp.delete("/<team_id>/connections/<int:connection_id>")
@require_role("admin")
def remove_team_connection(path: ConnectionPath):
    """Delete an inter-team connection."""
    from ..db.rotations import delete_team_connection

    if not delete_team_connection(path.connection_id):
        return error_response("NOT_FOUND", "Connection not found", HTTPStatus.NOT_FOUND)
    return {"message": "Connection deleted"}, HTTPStatus.OK
