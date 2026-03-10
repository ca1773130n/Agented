"""Team management API endpoints."""

# stdlib
import json
import logging
import sqlite3
from http import HTTPStatus
from typing import Optional

from app.models.common import error_response

logger = logging.getLogger(__name__)

# third-party
from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

# database
from ..database import (
    VALID_TRIGGER_SOURCES,
    add_team_edge,
    add_team_member,
    count_teams,
    delete_team,
    delete_team_edges_by_team,
    get_all_teams,
    get_team,
    get_team_by_name,
    get_team_detail,
    get_team_members,
    update_team,
)
from ..database import (
    create_team as db_create_team,
)

# models
from ..models.common import PaginationQuery
from ..models.team import VALID_TOPOLOGIES

# services
from ..services.rbac_service import require_role
from ..services.team_service import TeamService

tag = Tag(name="teams", description="Team management operations")
teams_bp = APIBlueprint("teams", __name__, url_prefix="/admin/teams", abp_tags=[tag])


class TeamPath(BaseModel):
    team_id: str = Field(..., description="Team ID")


class TeamTriggerBody(BaseModel):
    trigger_source: Optional[str] = Field(None, description="Trigger source type")
    trigger_config: Optional[object] = Field(None, description="Trigger match configuration")
    enabled: Optional[int] = Field(None, description="Enable or disable team trigger")


class TeamTopologyBody(BaseModel):
    topology: Optional[str] = Field(None, description="Topology pattern")
    topology_config: Optional[object] = Field(None, description="Topology configuration")


_MAX_TOPOLOGY_MEMBERS = 50


def _auto_generate_topology_edges(team_id: str, topology: str, topology_config=None):
    """Auto-generate edges based on topology type.

    For coordinator/hierarchical: creates delegation edges from leader to all workers.
    Clears existing edges first to avoid duplicates.
    """
    members = get_team_members(team_id)
    if not members or len(members) < 2:
        return

    if len(members) > _MAX_TOPOLOGY_MEMBERS:
        logger.warning(
            "Team %s has %d members, exceeding the topology edge generation limit of %d; "
            "skipping auto-generate to prevent synchronous overload on the request thread",
            team_id,
            len(members),
            _MAX_TOPOLOGY_MEMBERS,
        )
        return

    # Parse config to find coordinator
    config = {}
    if topology_config:
        try:
            config = (
                json.loads(topology_config) if isinstance(topology_config, str) else topology_config
            )
        except (json.JSONDecodeError, TypeError):
            config = {}

    coordinator_agent_id = config.get("coordinator")

    # Find the leader member
    leader = None
    workers = []
    for m in members:
        if coordinator_agent_id and m.get("agent_id") == coordinator_agent_id:
            leader = m
        elif m.get("role") == "leader":
            leader = m
        else:
            workers.append(m)

    # If coordinator was identified but also in workers, move to leader
    if leader and leader in workers:
        workers.remove(leader)

    if not leader or not workers:
        return

    # Clear existing edges for this team
    delete_team_edges_by_team(team_id)

    # Create delegation edges from leader to each worker
    for worker in workers:
        add_team_edge(
            team_id=team_id,
            source_member_id=leader["id"],
            target_member_id=worker["id"],
            edge_type="delegation",
            label="delegates",
        )


@teams_bp.get("/")
@require_role("viewer", "operator", "editor", "admin")
def list_teams(query: PaginationQuery):
    """List all teams with member counts and optional pagination."""
    total_count = count_teams()
    teams = get_all_teams(limit=query.limit, offset=query.offset or 0)
    return {"teams": teams, "total_count": total_count}, HTTPStatus.OK


@teams_bp.post("/")
@require_role("admin")
def create_team():
    """Create a new team."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    name = data.get("name")
    if not name:
        return error_response("BAD_REQUEST", "name is required", HTTPStatus.BAD_REQUEST)
    name = name.strip()
    if len(name) < 1:
        return error_response("BAD_REQUEST", "name must not be empty", HTTPStatus.BAD_REQUEST)
    if len(name) > 255:
        return error_response(
            "BAD_REQUEST", "name must not exceed 255 characters", HTTPStatus.BAD_REQUEST
        )
    if get_team_by_name(name):
        return error_response(
            "CONFLICT", "A team with this name already exists", HTTPStatus.CONFLICT
        )

    try:
        team_id = db_create_team(
            name=name,
            description=data.get("description"),
            color=data.get("color", "#00d4ff"),
            leader_id=data.get("leader_id"),
            topology=data.get("topology"),
            topology_config=data.get("topology_config"),
            trigger_source=data.get("trigger_source"),
            trigger_config=data.get("trigger_config"),
        )
    except sqlite3.IntegrityError as e:
        logger.error("Integrity error creating team: %s", e)
        return error_response(
            "CONFLICT",
            "A team with this name or configuration already exists",
            HTTPStatus.CONFLICT,
        )
    except sqlite3.OperationalError as e:
        logger.error("DB error creating team: %s", e)
        return error_response(
            "SERVICE_UNAVAILABLE",
            "Database unavailable, please retry",
            HTTPStatus.SERVICE_UNAVAILABLE,
        )
    if not team_id:
        return error_response(
            "INTERNAL_SERVER_ERROR",
            "Failed to create team — the database insert returned no ID",
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    # Auto-add leader as team member if leader_id was provided
    leader_id = data.get("leader_id")
    if leader_id:
        add_team_member(team_id=team_id, agent_id=leader_id, role="leader")

    team = get_team_detail(team_id)
    return {"message": "Team created", "team": team}, HTTPStatus.CREATED


@teams_bp.get("/<team_id>")
@require_role("viewer", "operator", "editor", "admin")
def get_team_detail_endpoint(path: TeamPath):
    """Get team details with members."""
    team = get_team_detail(path.team_id)
    if not team:
        return error_response("NOT_FOUND", "Team not found", HTTPStatus.NOT_FOUND)
    return team, HTTPStatus.OK


@teams_bp.put("/<team_id>")
@require_role("editor", "admin")
def update_team_endpoint(path: TeamPath):
    """Update a team."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    new_name = data.get("name")
    if new_name is not None:
        new_name = new_name.strip()
        if len(new_name) < 1:
            return error_response("BAD_REQUEST", "name must not be empty", HTTPStatus.BAD_REQUEST)
        if len(new_name) > 255:
            return error_response(
                "BAD_REQUEST", "name must not exceed 255 characters", HTTPStatus.BAD_REQUEST
            )
        existing = get_team_by_name(new_name)
        if existing and existing["id"] != path.team_id:
            return error_response(
                "CONFLICT", "A team with this name already exists", HTTPStatus.CONFLICT
            )

    if not update_team(
        path.team_id,
        name=new_name,
        description=data.get("description"),
        color=data.get("color"),
        leader_id=data.get("leader_id"),
    ):
        return error_response(
            "NOT_FOUND", "Team not found or no changes made", HTTPStatus.NOT_FOUND
        )

    team = get_team_detail(path.team_id)
    return team, HTTPStatus.OK


@teams_bp.delete("/<team_id>")
@require_role("admin")
def delete_team_endpoint(path: TeamPath):
    """Delete a team."""
    if not delete_team(path.team_id):
        return error_response("NOT_FOUND", "Team not found", HTTPStatus.NOT_FOUND)
    return {"message": "Team deleted"}, HTTPStatus.OK


# =============================================================================
# Topology routes
# =============================================================================


@teams_bp.put("/<team_id>/topology")
@require_role("editor", "admin")
def update_topology(path: TeamPath, body: TeamTopologyBody):
    """Update team topology configuration."""
    team = get_team(path.team_id)
    if not team:
        return error_response("NOT_FOUND", "Team not found", HTTPStatus.NOT_FOUND)

    _UNSET = object()
    # Use model_fields_set to distinguish "not provided" from "explicitly null"
    topology = body.topology if "topology" in body.model_fields_set else _UNSET
    topology_config = body.topology_config if "topology_config" in body.model_fields_set else _UNSET

    # Validate topology value (allow None to clear)
    if topology is not _UNSET and topology is not None and topology not in VALID_TOPOLOGIES:
        return error_response(
            "BAD_REQUEST",
            f"Invalid topology. Must be one of: {', '.join(VALID_TOPOLOGIES)}",
            HTTPStatus.BAD_REQUEST,
        )

    # Validate topology config if both provided
    if topology_config is not _UNSET and topology is not _UNSET and topology is not None:
        config_err = TeamService.validate_topology_config(path.team_id, topology, topology_config)
        if config_err:
            return error_response("BAD_REQUEST", config_err, HTTPStatus.BAD_REQUEST)

    # Serialize topology_config to JSON string if it's a dict
    config_str = _UNSET
    if topology_config is not _UNSET:
        if topology_config is None:
            config_str = ""
        else:
            config_str = (
                json.dumps(topology_config)
                if isinstance(topology_config, dict)
                else topology_config
            )

    # Build kwargs, using empty string for null topology to allow clearing
    update_kwargs = {}
    if topology is not _UNSET:
        update_kwargs["topology"] = topology if topology is not None else ""
    if config_str is not _UNSET:
        update_kwargs["topology_config"] = config_str

    if update_kwargs:
        update_team(path.team_id, **update_kwargs)

    # Auto-generate edges for coordinator/hierarchical topologies
    resolved_topology = update_kwargs.get("topology", topology)
    if resolved_topology in ("coordinator", "hierarchical"):
        _auto_generate_topology_edges(path.team_id, resolved_topology, config_str)

    updated = get_team_detail(path.team_id)
    return updated, HTTPStatus.OK


# =============================================================================
# Trigger routes
# =============================================================================


@teams_bp.put("/<team_id>/trigger")
@require_role("editor", "admin")
def update_trigger(path: TeamPath, body: TeamTriggerBody):
    """Update team trigger configuration."""
    team = get_team(path.team_id)
    if not team:
        return error_response("NOT_FOUND", "Team not found", HTTPStatus.NOT_FOUND)

    trigger_source = body.trigger_source
    trigger_config = body.trigger_config
    enabled = body.enabled

    # Validate trigger_source
    if trigger_source is not None and trigger_source not in VALID_TRIGGER_SOURCES:
        return error_response(
            "BAD_REQUEST",
            f"Invalid trigger_source. Must be one of: {', '.join(VALID_TRIGGER_SOURCES)}",
            HTTPStatus.BAD_REQUEST,
        )

    # Serialize trigger_config to JSON string if it's a dict
    config_str = None
    if trigger_config is not None:
        config_str = (
            json.dumps(trigger_config) if isinstance(trigger_config, dict) else trigger_config
        )

    update_team(
        path.team_id,
        trigger_source=trigger_source,
        trigger_config=config_str,
        enabled=enabled,
    )

    updated = get_team_detail(path.team_id)
    return updated, HTTPStatus.OK


# =============================================================================
# Manual run route
# =============================================================================


@teams_bp.post("/<team_id>/run")
@require_role("operator", "editor", "admin")
def manual_run(path: TeamPath):
    """Manually trigger a team execution."""
    team = get_team(path.team_id)
    if not team:
        return error_response("NOT_FOUND", "Team not found", HTTPStatus.NOT_FOUND)

    if not team.get("enabled", 1):
        return error_response("BAD_REQUEST", "Team is disabled", HTTPStatus.BAD_REQUEST)

    data = request.get_json(silent=True) or {}
    message = data.get("message", "")

    from ..services.team_execution_service import TeamExecutionService

    try:
        team_exec_id = TeamExecutionService.execute_team(
            team_id=path.team_id,
            message=message,
            event={},
            trigger_type="manual",
        )
    except ValueError as e:
        return error_response("BAD_REQUEST", str(e), HTTPStatus.BAD_REQUEST)

    return {
        "message": "Team execution started",
        "team_execution_id": team_exec_id,
    }, HTTPStatus.OK
