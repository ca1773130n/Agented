"""Team management API endpoints."""

# stdlib
import json
import logging
import subprocess
import threading
import uuid
from http import HTTPStatus
from typing import Optional

logger = logging.getLogger(__name__)

# third-party
from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

# database
from ..database import (
    VALID_ENTITY_TYPES,
    VALID_TRIGGER_SOURCES,
    add_team,
    add_team_agent_assignment,
    # Edge CRUD
    add_team_edge,
    add_team_member,
    count_teams,
    delete_team,
    delete_team_agent_assignment,
    delete_team_agent_assignments_bulk,
    delete_team_edge,
    delete_team_edges_by_team,
    get_all_teams,
    get_team,
    get_team_agent_assignments,
    get_team_by_name,
    get_team_detail,
    get_team_edges,
    get_team_members,
    remove_team_member,
    update_team,
    update_team_member,
)

# models
from ..models.common import PaginationQuery
from ..models.team import VALID_EDGE_TYPES, VALID_TOPOLOGIES
from ..services.team_generation_service import TeamGenerationService

# services
from ..services.team_service import TeamService

tag = Tag(name="teams", description="Team management operations")
teams_bp = APIBlueprint("teams", __name__, url_prefix="/admin/teams", abp_tags=[tag])

# In-memory job store for async team generation (job_id -> result dict).
# Limited to 200 entries; oldest are evicted when full.
_generation_jobs: dict = {}
_jobs_lock = threading.Lock()
_MAX_JOBS = 200


class TeamPath(BaseModel):
    team_id: str = Field(..., description="Team ID")


class MemberPath(BaseModel):
    team_id: str = Field(..., description="Team ID")
    member_id: int = Field(..., description="Member ID")


class TeamAgentPath(BaseModel):
    team_id: str = Field(..., description="Team ID")
    agent_id: str = Field(..., description="Agent ID")


class AssignmentPath(BaseModel):
    team_id: str = Field(..., description="Team ID")
    assignment_id: int = Field(..., description="Assignment ID")


class EdgePath(BaseModel):
    team_id: str = Field(..., description="Team ID")
    edge_id: int = Field(..., description="Edge ID")


class ConnectionPath(BaseModel):
    team_id: str = Field(..., description="Team ID")
    connection_id: int = Field(..., description="Connection ID")


class GenerateJobPath(BaseModel):
    job_id: str = Field(..., description="Job ID returned by POST /generate")


class TeamConnectionBody(BaseModel):
    target_team_id: str = Field(..., description="ID of the target team")
    connection_type: str = Field("dependency", description="Type of connection")
    description: str = Field(None, description="Optional description")


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
def list_teams(query: PaginationQuery):
    """List all teams with member counts and optional pagination."""
    total_count = count_teams()
    teams = get_all_teams(limit=query.limit, offset=query.offset or 0)
    return {"teams": teams, "total_count": total_count}, HTTPStatus.OK


@teams_bp.post("/")
def create_team():
    """Create a new team."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    name = data.get("name")
    if not name:
        return {"error": "name is required"}, HTTPStatus.BAD_REQUEST
    name = name.strip()
    if len(name) < 1:
        return {"error": "name must not be empty"}, HTTPStatus.BAD_REQUEST
    if len(name) > 255:
        return {"error": "name must not exceed 255 characters"}, HTTPStatus.BAD_REQUEST
    if get_team_by_name(name):
        return {"error": "A team with this name already exists"}, HTTPStatus.CONFLICT

    team_id = add_team(
        name=name,
        description=data.get("description"),
        color=data.get("color", "#00d4ff"),
        leader_id=data.get("leader_id"),
        topology=data.get("topology"),
        topology_config=data.get("topology_config"),
        trigger_source=data.get("trigger_source"),
        trigger_config=data.get("trigger_config"),
    )
    if not team_id:
        return {"error": "Failed to create team"}, HTTPStatus.INTERNAL_SERVER_ERROR

    # Auto-add leader as team member if leader_id was provided
    leader_id = data.get("leader_id")
    if leader_id:
        add_team_member(team_id=team_id, agent_id=leader_id, role="leader")

    team = get_team_detail(team_id)
    return {"message": "Team created", "team": team}, HTTPStatus.CREATED


@teams_bp.post("/generate")
def generate_team_config():
    """Generate a team configuration from a natural language description using AI.

    Returns a job_id immediately (202 Accepted). Poll GET /generate/<job_id> for the result.
    This avoids blocking a Flask worker thread for the full Claude CLI duration (up to 2 min).
    """
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    description = data.get("description", "")
    if not description or len(description) < 10:
        return {
            "error": "description is required and must be at least 10 characters"
        }, HTTPStatus.BAD_REQUEST

    job_id = f"gen-{uuid.uuid4().hex[:8]}"

    with _jobs_lock:
        # Evict oldest entries when the store is full
        if len(_generation_jobs) >= _MAX_JOBS:
            oldest_key = next(iter(_generation_jobs))
            del _generation_jobs[oldest_key]
        _generation_jobs[job_id] = {"status": "pending"}

    def _run():
        try:
            result = TeamGenerationService.generate(description)
            with _jobs_lock:
                _generation_jobs[job_id] = {"status": "complete", **result}
        except subprocess.TimeoutExpired:
            with _jobs_lock:
                _generation_jobs[job_id] = {
                    "status": "error",
                    "error": "Team generation timed out. The AI service took too long to respond. Please try again.",
                }
        except RuntimeError as e:
            with _jobs_lock:
                _generation_jobs[job_id] = {"status": "error", "error": str(e)}
        except Exception as e:
            with _jobs_lock:
                _generation_jobs[job_id] = {
                    "status": "error",
                    "error": f"Team generation failed: {str(e)}",
                }

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id}, HTTPStatus.ACCEPTED


@teams_bp.get("/generate/<job_id>")
def get_generation_job(path: GenerateJobPath):
    """Poll the result of a team generation job started by POST /generate."""
    with _jobs_lock:
        job = dict(_generation_jobs.get(path.job_id, {}))
    if not job:
        return {"error": "Job not found"}, HTTPStatus.NOT_FOUND
    if job["status"] == "error":
        error_msg = job.get("error", "Unknown error")
        status_code = (
            HTTPStatus.SERVICE_UNAVAILABLE
            if "timed out" in error_msg or "not found" in error_msg.lower()
            else HTTPStatus.INTERNAL_SERVER_ERROR
        )
        return {"error": error_msg}, status_code
    return job, HTTPStatus.OK


@teams_bp.post("/generate/stream")
def generate_team_config_stream():
    """Stream team configuration generation with real-time AI output via SSE."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    description = data.get("description", "")
    if not description or len(description) < 10:
        return {
            "error": "description is required and must be at least 10 characters"
        }, HTTPStatus.BAD_REQUEST

    def generate():
        yield from TeamGenerationService.generate_streaming(description)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@teams_bp.get("/<team_id>")
def get_team_detail_endpoint(path: TeamPath):
    """Get team details with members."""
    team = get_team_detail(path.team_id)
    if not team:
        return {"error": "Team not found"}, HTTPStatus.NOT_FOUND
    return team, HTTPStatus.OK


@teams_bp.put("/<team_id>")
def update_team_endpoint(path: TeamPath):
    """Update a team."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    new_name = data.get("name")
    if new_name is not None:
        new_name = new_name.strip()
        if len(new_name) < 1:
            return {"error": "name must not be empty"}, HTTPStatus.BAD_REQUEST
        if len(new_name) > 255:
            return {"error": "name must not exceed 255 characters"}, HTTPStatus.BAD_REQUEST
        existing = get_team_by_name(new_name)
        if existing and existing["id"] != path.team_id:
            return {"error": "A team with this name already exists"}, HTTPStatus.CONFLICT

    if not update_team(
        path.team_id,
        name=new_name,
        description=data.get("description"),
        color=data.get("color"),
        leader_id=data.get("leader_id"),
    ):
        return {"error": "Team not found or no changes made"}, HTTPStatus.NOT_FOUND

    team = get_team_detail(path.team_id)
    return team, HTTPStatus.OK


@teams_bp.delete("/<team_id>")
def delete_team_endpoint(path: TeamPath):
    """Delete a team."""
    if not delete_team(path.team_id):
        return {"error": "Team not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Team deleted"}, HTTPStatus.OK


# Member routes
@teams_bp.get("/<team_id>/members")
def list_members(path: TeamPath):
    """List team members."""
    members = get_team_members(path.team_id)
    return {"members": members}, HTTPStatus.OK


@teams_bp.post("/<team_id>/members")
def add_member(path: TeamPath):
    """Add a member to the team."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    name = data.get("name")
    agent_id = data.get("agent_id")
    super_agent_id = data.get("super_agent_id")

    # At least one identifier is required
    if not name and not agent_id and not super_agent_id:
        return {"error": "name, agent_id, or super_agent_id is required"}, HTTPStatus.BAD_REQUEST

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
        return {"error": "Failed to add member"}, HTTPStatus.INTERNAL_SERVER_ERROR

    # Return the member data
    members = get_team_members(path.team_id)
    member = next((m for m in members if m["id"] == member_id), None)
    return {"message": "Member added", "member": member}, HTTPStatus.CREATED


@teams_bp.put("/<team_id>/members/<int:member_id>")
def update_member(path: MemberPath):
    """Update a team member."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    if not update_team_member(
        path.member_id,
        name=data.get("name"),
        email=data.get("email"),
        role=data.get("role"),
        layer=data.get("layer"),
        description=data.get("description"),
        tier=data.get("tier"),
    ):
        return {"error": "Member not found or no changes made"}, HTTPStatus.NOT_FOUND

    members = get_team_members(path.team_id)
    member = next((m for m in members if m["id"] == path.member_id), None)
    return {"member": member}, HTTPStatus.OK


@teams_bp.delete("/<team_id>/members/<int:member_id>")
def delete_member(path: MemberPath):
    """Remove a member from the team."""
    if not remove_team_member(path.member_id):
        return {"error": "Member not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Member removed"}, HTTPStatus.OK


# =============================================================================
# Team connection routes (inter-team)
# =============================================================================


@teams_bp.get("/<team_id>/connections")
def list_team_connections(path: TeamPath):
    """List inter-team connections for a team."""
    from ..db.rotations import get_team_connections

    connections = get_team_connections(path.team_id)
    return {"connections": connections}, HTTPStatus.OK


@teams_bp.post("/<team_id>/connections")
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
        return {"error": "Failed to create connection"}, HTTPStatus.BAD_REQUEST
    return {"message": "Connection created", "id": conn_id}, HTTPStatus.CREATED


@teams_bp.delete("/<team_id>/connections/<int:connection_id>")
def remove_team_connection(path: ConnectionPath):
    """Delete an inter-team connection."""
    from ..db.rotations import delete_team_connection

    if not delete_team_connection(path.connection_id):
        return {"error": "Connection not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Connection deleted"}, HTTPStatus.OK


# =============================================================================
# Assignment routes
# =============================================================================


@teams_bp.post("/<team_id>/agents/<agent_id>/assignments")
def add_agent_assignment(path: TeamAgentPath):
    """Add an entity assignment (skill/command/hook/rule) for an agent within a team."""
    team = get_team(path.team_id)
    if not team:
        return {"error": "Team not found"}, HTTPStatus.NOT_FOUND

    if not TeamService.is_agent_team_member(path.team_id, path.agent_id):
        return {"error": "Agent is not a member of this team"}, HTTPStatus.BAD_REQUEST

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")

    if not entity_type or not entity_id:
        return {"error": "entity_type and entity_id are required"}, HTTPStatus.BAD_REQUEST

    if entity_type not in VALID_ENTITY_TYPES:
        return {
            "error": f"Invalid entity_type. Must be one of: {', '.join(VALID_ENTITY_TYPES)}"
        }, HTTPStatus.BAD_REQUEST

    assignment_id = add_team_agent_assignment(
        team_id=path.team_id,
        agent_id=path.agent_id,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=data.get("entity_name"),
    )

    if assignment_id is None:
        return {"error": "Assignment already exists or failed to create"}, HTTPStatus.CONFLICT

    # Fetch the created assignment
    assignments = get_team_agent_assignments(path.team_id, path.agent_id)
    assignment = next((a for a in assignments if a["id"] == assignment_id), None)

    return {
        "message": "Assignment added",
        "assignment": assignment,
    }, HTTPStatus.CREATED


@teams_bp.get("/<team_id>/agents/<agent_id>/assignments")
def list_agent_assignments(path: TeamAgentPath):
    """List assignments for an agent within a team."""
    assignments = get_team_agent_assignments(path.team_id, path.agent_id)
    return {"assignments": assignments}, HTTPStatus.OK


@teams_bp.get("/<team_id>/assignments")
def list_team_assignments(path: TeamPath):
    """List all assignments for a team across all agents."""
    assignments = get_team_agent_assignments(path.team_id)
    return {"assignments": assignments}, HTTPStatus.OK


@teams_bp.delete("/<team_id>/assignments/<int:assignment_id>")
def delete_assignment(path: AssignmentPath):
    """Delete a single assignment."""
    if not delete_team_agent_assignment(path.assignment_id):
        return {"error": "Assignment not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Assignment deleted"}, HTTPStatus.OK


@teams_bp.delete("/<team_id>/agents/<agent_id>/assignments")
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


# =============================================================================
# Edge routes (directed graph relationships)
# =============================================================================


@teams_bp.get("/<team_id>/edges")
def list_edges(path: TeamPath):
    """List all edges for a team."""
    edges = get_team_edges(path.team_id)
    return {"edges": edges}, HTTPStatus.OK


@teams_bp.post("/<team_id>/edges")
def create_edge(path: TeamPath):
    """Create a directed edge between two team members."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    source_member_id = data.get("source_member_id")
    target_member_id = data.get("target_member_id")
    edge_type = data.get("edge_type", "delegation")

    if source_member_id is None or target_member_id is None:
        return {
            "error": "source_member_id and target_member_id are required"
        }, HTTPStatus.BAD_REQUEST

    if edge_type not in VALID_EDGE_TYPES:
        return {
            "error": f"Invalid edge_type. Must be one of: {', '.join(VALID_EDGE_TYPES)}"
        }, HTTPStatus.BAD_REQUEST

    edge_id = add_team_edge(
        team_id=path.team_id,
        source_member_id=source_member_id,
        target_member_id=target_member_id,
        edge_type=edge_type,
        label=data.get("label"),
        weight=data.get("weight", 1),
    )
    if edge_id is None:
        return {"error": "Failed to create edge (self-loop or duplicate)"}, HTTPStatus.BAD_REQUEST

    # Fetch the created edge
    edges = get_team_edges(path.team_id)
    edge = next((e for e in edges if e["id"] == edge_id), None)
    return {"message": "Edge created", "edge": edge}, HTTPStatus.CREATED


@teams_bp.delete("/<team_id>/edges/<int:edge_id>")
def delete_edge(path: EdgePath):
    """Delete a single edge."""
    if not delete_team_edge(path.edge_id):
        return {"error": "Edge not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Edge deleted"}, HTTPStatus.OK


@teams_bp.delete("/<team_id>/edges")
def bulk_delete_edges(path: TeamPath):
    """Bulk delete all edges for a team."""
    deleted_count = delete_team_edges_by_team(path.team_id)
    return {
        "message": f"Deleted {deleted_count} edge(s)",
        "deleted_count": deleted_count,
    }, HTTPStatus.OK


# =============================================================================
# Topology routes
# =============================================================================


@teams_bp.put("/<team_id>/topology")
def update_topology(path: TeamPath, body: TeamTopologyBody):
    """Update team topology configuration."""
    team = get_team(path.team_id)
    if not team:
        return {"error": "Team not found"}, HTTPStatus.NOT_FOUND

    _UNSET = object()
    # Use model_fields_set to distinguish "not provided" from "explicitly null"
    topology = body.topology if "topology" in body.model_fields_set else _UNSET
    topology_config = body.topology_config if "topology_config" in body.model_fields_set else _UNSET

    # Validate topology value (allow None to clear)
    if topology is not _UNSET and topology is not None and topology not in VALID_TOPOLOGIES:
        return {
            "error": f"Invalid topology. Must be one of: {', '.join(VALID_TOPOLOGIES)}"
        }, HTTPStatus.BAD_REQUEST

    # Validate topology config if both provided
    if topology_config is not _UNSET and topology is not _UNSET and topology is not None:
        config_err = TeamService.validate_topology_config(path.team_id, topology, topology_config)
        if config_err:
            return {"error": config_err}, HTTPStatus.BAD_REQUEST

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
def update_trigger(path: TeamPath, body: TeamTriggerBody):
    """Update team trigger configuration."""
    team = get_team(path.team_id)
    if not team:
        return {"error": "Team not found"}, HTTPStatus.NOT_FOUND

    trigger_source = body.trigger_source
    trigger_config = body.trigger_config
    enabled = body.enabled

    # Validate trigger_source
    if trigger_source is not None and trigger_source not in VALID_TRIGGER_SOURCES:
        return {
            "error": f"Invalid trigger_source. Must be one of: {', '.join(VALID_TRIGGER_SOURCES)}"
        }, HTTPStatus.BAD_REQUEST

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
def manual_run(path: TeamPath):
    """Manually trigger a team execution."""
    team = get_team(path.team_id)
    if not team:
        return {"error": "Team not found"}, HTTPStatus.NOT_FOUND

    if not team.get("enabled", 1):
        return {"error": "Team is disabled"}, HTTPStatus.BAD_REQUEST

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
        return {"error": str(e)}, HTTPStatus.BAD_REQUEST

    return {
        "message": "Team execution started",
        "team_execution_id": team_exec_id,
    }, HTTPStatus.OK
