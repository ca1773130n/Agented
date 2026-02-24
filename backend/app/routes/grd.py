"""GRD project management sync and data endpoints."""

import logging
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Optional

from flask import Response
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    get_milestones_by_project,
    get_phases_by_milestone,
    get_plans_by_phase,
    get_project,
    get_project_plan,
    get_project_sync_states,
    get_sessions_by_project,
    update_project,
    update_project_plan,
)
from ..services.execution_type_handler import get_handler
from ..services.grd_cli_service import GrdCliService
from ..services.grd_sync_service import GrdSyncService
from ..services.project_session_manager import ProjectSessionManager

tag = Tag(name="grd", description="GRD project management sync and data endpoints")
grd_bp = APIBlueprint("grd", __name__, url_prefix="/api/projects", abp_tags=[tag])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path / Query / Body models
# ---------------------------------------------------------------------------


class ProjectIdPath(BaseModel):
    project_id: str = Field(..., description="Project ID")


class PlanStatusPath(BaseModel):
    project_id: str = Field(..., description="Project ID")
    plan_id: str = Field(..., description="Plan ID")


class UpdatePlanStatusBody(BaseModel):
    status: str = Field(
        ..., description="New plan status: pending|in_progress|completed|failed|in_review"
    )


class MilestoneIdQuery(BaseModel):
    milestone_id: Optional[str] = Field(None, description="Filter by milestone ID")


class PhaseIdQuery(BaseModel):
    phase_id: Optional[str] = Field(None, description="Filter by phase ID")


class SessionPath(BaseModel):
    project_id: str = Field(..., description="Project ID")
    session_id: str = Field(..., description="Session ID")


class CreateSessionBody(BaseModel):
    cmd: list = Field(..., description="Command to execute as list of strings")
    cwd: Optional[str] = Field(
        None, description="Working directory (defaults to project local_path)"
    )
    phase_id: Optional[str] = None
    plan_id: Optional[str] = None
    agent_id: Optional[str] = None
    worktree_path: Optional[str] = None
    execution_type: str = Field(
        "direct", description="Execution type: direct, ralph_loop, team_spawn"
    )
    execution_mode: str = Field("autonomous", description="Execution mode: autonomous, interactive")


class SessionInputBody(BaseModel):
    text: str = Field(..., description="Text to send to PTY stdin")


class SessionOutputQuery(BaseModel):
    last_n: int = Field(100, description="Number of output lines to return", ge=1, le=10000)


class CreateRalphSessionBody(BaseModel):
    cwd: Optional[str] = None
    phase_id: Optional[str] = None
    plan_id: Optional[str] = None
    agent_id: Optional[str] = None
    ralph_config: dict = Field(
        default_factory=dict,
        description="Ralph loop configuration: max_iterations, completion_promise, task_description, no_progress_threshold",
    )


class CreateTeamSessionBody(BaseModel):
    cwd: Optional[str] = None
    phase_id: Optional[str] = None
    plan_id: Optional[str] = None
    agent_id: Optional[str] = None
    team_config: dict = Field(
        default_factory=dict,
        description="Team config: team_size, task_description, roles",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@grd_bp.get("/<project_id>/sync")
def get_sync_status(path: ProjectIdPath):
    """Return sync metadata for a project."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    states = get_project_sync_states(path.project_id)
    return {
        "last_synced_at": project.get("grd_sync_at"),
        "file_count": len(states),
        "grd_available": GrdCliService._binary_available,
    }, HTTPStatus.OK


@grd_bp.post("/<project_id>/sync")
def trigger_sync(path: ProjectIdPath):
    """Trigger a full GRD sync for a project."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    local_path = project.get("local_path")
    if not local_path:
        return {"error": "Project has no local_path configured"}, HTTPStatus.BAD_REQUEST

    planning_dir = str(Path(local_path).expanduser().resolve() / ".planning")
    result = GrdSyncService.sync_project(path.project_id, planning_dir)

    # Persist sync timestamp
    update_project(path.project_id, grd_sync_at=datetime.utcnow().isoformat())

    return {
        "synced": result["synced"],
        "skipped": result["skipped"],
        "errors": result["errors"],
    }, HTTPStatus.OK


@grd_bp.get("/<project_id>/milestones")
def list_milestones(path: ProjectIdPath):
    """List all milestones for a project."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    milestones = get_milestones_by_project(path.project_id)
    return {"milestones": milestones}, HTTPStatus.OK


@grd_bp.get("/<project_id>/phases")
def list_phases(path: ProjectIdPath, query: MilestoneIdQuery):
    """List phases for a project, optionally filtered by milestone."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    if query.milestone_id:
        phases = get_phases_by_milestone(query.milestone_id)
    else:
        # Aggregate phases from all milestones for this project
        milestones = get_milestones_by_project(path.project_id)
        phases = []
        for ms in milestones:
            phases.extend(get_phases_by_milestone(ms["id"]))

    return {"phases": phases}, HTTPStatus.OK


@grd_bp.get("/<project_id>/plans")
def list_plans(path: ProjectIdPath, query: PhaseIdQuery):
    """List plans for a project, optionally filtered by phase."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    if query.phase_id:
        plans = get_plans_by_phase(query.phase_id)
    else:
        # Aggregate plans from all milestones -> all phases
        milestones = get_milestones_by_project(path.project_id)
        plans = []
        for ms in milestones:
            for phase in get_phases_by_milestone(ms["id"]):
                plans.extend(get_plans_by_phase(phase["id"]))

    return {"plans": plans}, HTTPStatus.OK


@grd_bp.put("/<project_id>/plans/<plan_id>/status")
def update_plan_status(path: PlanStatusPath, body: UpdatePlanStatusBody):
    """Update a plan's status (triggers GRD CLI file write if available)."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    plan = get_project_plan(path.plan_id)
    if not plan:
        return {"error": "Plan not found"}, HTTPStatus.NOT_FOUND

    valid_statuses = {"pending", "in_progress", "completed", "failed", "in_review"}
    if body.status not in valid_statuses:
        return {
            "error": f"Invalid status: {body.status}. Must be one of: {', '.join(sorted(valid_statuses))}"
        }, HTTPStatus.BAD_REQUEST

    # Update DB immediately
    update_project_plan(path.plan_id, status=body.status)

    # Attempt GRD CLI file write (non-blocking -- DB update already done)
    local_path = project.get("local_path")
    if local_path and GrdCliService._binary_available:
        try:
            states = get_project_sync_states(path.project_id)
            match = next(
                (
                    s
                    for s in states
                    if s["entity_id"] == path.plan_id and s["entity_type"] == "plan"
                ),
                None,
            )
            if match:
                cli_result = GrdCliService.update_plan_status(
                    local_path, match["file_path"], body.status
                )
                if not cli_result.get("success"):
                    logger.warning(
                        "GRD CLI plan status write failed for plan %s: %s",
                        path.plan_id,
                        cli_result.get("error"),
                    )
            else:
                logger.debug(
                    "No sync state match for plan %s -- skipping GRD CLI write", path.plan_id
                )
        except Exception as e:
            logger.warning("GRD CLI plan status write error for plan %s: %s", path.plan_id, e)

    updated_plan = get_project_plan(path.plan_id)
    return {"message": "Plan status updated", "plan": updated_plan}, HTTPStatus.OK


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------


@grd_bp.post("/<project_id>/sessions")
def create_session(path: ProjectIdPath, body: CreateSessionBody):
    """Create a new PTY session for a project."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    handler = get_handler(body.execution_type)
    if not handler:
        return {"error": f"Unknown execution_type: {body.execution_type}"}, HTTPStatus.BAD_REQUEST

    cwd = body.cwd or project.get("local_path")
    if not cwd:
        return {
            "error": "No working directory: set cwd in request body or local_path on project"
        }, HTTPStatus.BAD_REQUEST

    session_config = {
        "project_id": path.project_id,
        "cmd": body.cmd,
        "cwd": cwd,
        "phase_id": body.phase_id,
        "plan_id": body.plan_id,
        "agent_id": body.agent_id,
        "worktree_path": body.worktree_path,
        "execution_type": body.execution_type,
        "execution_mode": body.execution_mode,
    }
    result = handler.start(session_config)
    return result, HTTPStatus.CREATED


@grd_bp.get("/<project_id>/sessions")
def list_sessions(path: ProjectIdPath):
    """List all sessions for a project."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    sessions = get_sessions_by_project(path.project_id)
    return {"sessions": sessions}, HTTPStatus.OK


@grd_bp.get("/<project_id>/sessions/<session_id>/stream")
def stream_session(path: SessionPath):
    """SSE endpoint for real-time session output streaming."""

    def generate():
        for event in ProjectSessionManager.subscribe(path.session_id):
            yield event

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@grd_bp.get("/<project_id>/sessions/<session_id>/output")
def get_session_output(path: SessionPath, query: SessionOutputQuery):
    """Get buffered output lines from a session's ring buffer."""
    lines = ProjectSessionManager.get_output(path.session_id, last_n=query.last_n)
    return {"lines": lines, "count": len(lines)}, HTTPStatus.OK


@grd_bp.post("/<project_id>/sessions/<session_id>/stop")
def stop_session(path: SessionPath):
    """Stop a running session."""
    success = ProjectSessionManager.stop_session(path.session_id)
    if not success:
        return {"error": "Session not found or already stopped"}, HTTPStatus.NOT_FOUND
    return {"message": "Session stopped", "session_id": path.session_id}, HTTPStatus.OK


@grd_bp.post("/<project_id>/sessions/<session_id>/pause")
def pause_session(path: SessionPath):
    """Pause SSE broadcasting for a session (process keeps running)."""
    success = ProjectSessionManager.pause_session(path.session_id)
    if not success:
        return {"error": "Session not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Session paused", "session_id": path.session_id}, HTTPStatus.OK


@grd_bp.post("/<project_id>/sessions/<session_id>/resume")
def resume_session(path: SessionPath):
    """Resume SSE broadcasting for a paused session."""
    success = ProjectSessionManager.resume_session(path.session_id)
    if not success:
        return {"error": "Session not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Session resumed", "session_id": path.session_id}, HTTPStatus.OK


@grd_bp.post("/<project_id>/sessions/<session_id>/input")
def send_session_input(path: SessionPath, body: SessionInputBody):
    """Send input text to a session's PTY stdin."""
    # Strip ASCII control characters (0-8, 11-31, 127) to prevent unintended PTY signals.
    # Tab (9), newline (10), and carriage return (13) are preserved as harmless whitespace.
    sanitized = "".join(
        ch for ch in body.text if ch == "\t" or ch == "\n" or ch == "\r" or (32 <= ord(ch) < 127)
    )
    success = ProjectSessionManager.send_input(path.session_id, sanitized)
    if not success:
        return {"error": "Session not found or not active"}, HTTPStatus.NOT_FOUND
    return {"message": "Input sent", "session_id": path.session_id}, HTTPStatus.OK


# ---------------------------------------------------------------------------
# Ralph / Team session endpoints
# ---------------------------------------------------------------------------


@grd_bp.post("/<project_id>/sessions/ralph")
def create_ralph_session(path: ProjectIdPath, body: CreateRalphSessionBody):
    """Create a new Ralph loop session for a project."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    cwd = body.cwd or project.get("local_path")
    if not cwd:
        return {
            "error": "No working directory: set cwd in request body or local_path on project"
        }, HTTPStatus.BAD_REQUEST

    handler = get_handler("ralph_loop")
    if not handler:
        return {"error": "Ralph loop handler not registered"}, HTTPStatus.INTERNAL_SERVER_ERROR

    session_config = {
        "project_id": path.project_id,
        "cwd": cwd,
        "phase_id": body.phase_id,
        "plan_id": body.plan_id,
        "agent_id": body.agent_id,
        "ralph_config": body.ralph_config,
    }
    result = handler.start(session_config)

    # Check if handler returned an error (e.g., plugin not installed)
    if "error" in result:
        return result, HTTPStatus.BAD_REQUEST

    return result, HTTPStatus.CREATED


@grd_bp.post("/<project_id>/sessions/team")
def create_team_session(path: ProjectIdPath, body: CreateTeamSessionBody):
    """Create a new team spawn session for a project."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    cwd = body.cwd or project.get("local_path")
    if not cwd:
        return {
            "error": "No working directory: set cwd in request body or local_path on project"
        }, HTTPStatus.BAD_REQUEST

    handler = get_handler("team_spawn")
    if not handler:
        return {"error": "Team spawn handler not registered"}, HTTPStatus.INTERNAL_SERVER_ERROR

    session_config = {
        "project_id": path.project_id,
        "cwd": cwd,
        "phase_id": body.phase_id,
        "plan_id": body.plan_id,
        "agent_id": body.agent_id,
        "team_config": body.team_config,
    }
    result = handler.start(session_config)

    # Check if handler returned an error (e.g., feature flag unavailable)
    if "error" in result:
        return result, HTTPStatus.BAD_REQUEST

    return result, HTTPStatus.CREATED


@grd_bp.get("/<project_id>/sessions/<session_id>/monitor")
def monitor_session(path: SessionPath):
    """Get execution-type-aware monitoring data for a session.

    Looks up the session's execution_type and delegates to the appropriate
    handler's monitor() method for type-specific data (e.g., Ralph iteration
    count or team member list).
    """
    # First try in-memory session info
    info = ProjectSessionManager.get_session_info(path.session_id)
    if info:
        execution_type = info.get("execution_type", "direct")
    else:
        # Fallback: check database
        from ..database import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT execution_type FROM project_sessions WHERE id = ?",
                (path.session_id,),
            ).fetchone()
        if not row:
            return {"error": "Session not found"}, HTTPStatus.NOT_FOUND
        execution_type = row["execution_type"] if row["execution_type"] else "direct"

    handler = get_handler(execution_type)
    if not handler:
        return {"error": f"No handler for execution_type: {execution_type}"}, HTTPStatus.NOT_FOUND

    result = handler.monitor(path.session_id)
    result["session_id"] = path.session_id
    result["execution_type"] = execution_type
    return result, HTTPStatus.OK
