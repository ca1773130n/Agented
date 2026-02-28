"""GRD project management sync and data endpoints."""

import logging
import threading
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Optional

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    add_project_phase,
    add_project_plan,
    add_super_agent,
    add_super_agent_document,
    delete_project_plan,
    get_milestones_by_project,
    get_phases_by_milestone,
    get_plans_by_phase,
    get_project,
    get_project_plan,
    get_project_sync_states,
    get_sessions_by_project,
    get_super_agent,
    update_project,
    update_project_plan,
)
from ..services.execution_type_handler import get_handler
from ..services.grd_cli_service import GrdCliService
from ..services.grd_planning_service import GrdPlanningService
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


class CreatePlanBody(BaseModel):
    phase_id: str = Field(..., description="Phase ID to add plan to")
    title: str = Field(..., description="Plan title")
    description: Optional[str] = Field(None, description="Plan description")
    status: str = Field("pending", description="Initial status")
    tasks_json: Optional[str] = Field(None, description="Tasks JSON")


class UpdatePlanBody(BaseModel):
    title: Optional[str] = Field(None, description="New title")
    description: Optional[str] = Field(None, description="New description")
    status: Optional[str] = Field(None, description="New status")
    tasks_json: Optional[str] = Field(None, description="Tasks JSON")


class ProjectChatBody(BaseModel):
    content: str = Field(..., description="Chat message content")
    milestone_id: Optional[str] = Field(None, description="Milestone context filter")


class CreatePhaseBody(BaseModel):
    milestone_id: str = Field(..., description="Milestone ID to add phase to")
    name: str = Field(..., description="Phase name")
    goal: Optional[str] = Field(None, description="Phase goal")
    status: str = Field("pending", description="Initial status")


class MilestoneIdQuery(BaseModel):
    milestone_id: Optional[str] = Field(None, description="Filter by milestone ID")


class PhaseIdQuery(BaseModel):
    phase_id: Optional[str] = Field(None, description="Filter by phase ID")


class InvokePlanningBody(BaseModel):
    command: str = Field(..., description="GRD command name (e.g., plan-phase, discuss-phase)")
    args: Optional[dict] = Field(None, description="Command arguments as key-value pairs")


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


@grd_bp.post("/<project_id>/phases")
def create_phase(path: ProjectIdPath, body: CreatePhaseBody):
    """Create a new phase within a milestone."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    # Verify milestone belongs to this project
    milestones = get_milestones_by_project(path.project_id)
    ms_ids = {m["id"] for m in milestones}
    if body.milestone_id not in ms_ids:
        return {"error": "Milestone not found in this project"}, HTTPStatus.NOT_FOUND

    # Auto-compute phase_number as max + 1
    existing_phases = get_phases_by_milestone(body.milestone_id)
    next_number = max((p["phase_number"] for p in existing_phases), default=0) + 1

    phase_id = add_project_phase(
        milestone_id=body.milestone_id,
        phase_number=next_number,
        name=body.name,
        goal=body.goal,
    )
    if not phase_id:
        return {"error": "Failed to create phase"}, HTTPStatus.INTERNAL_SERVER_ERROR

    return {
        "message": "Phase created",
        "phase": {
            "id": phase_id,
            "milestone_id": body.milestone_id,
            "phase_number": next_number,
            "name": body.name,
            "status": body.status,
            "goal": body.goal,
            "verification_level": "sanity",
            "wave": None,
            "plan_count": 0,
        },
    }, HTTPStatus.CREATED


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


@grd_bp.post("/<project_id>/plans")
def create_plan(path: ProjectIdPath, body: CreatePlanBody):
    """Create a new plan in a phase."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    # Auto-compute plan_number as max(existing) + 1
    existing = get_plans_by_phase(body.phase_id)
    plan_number = max((p["plan_number"] for p in existing), default=0) + 1

    plan_id = add_project_plan(
        phase_id=body.phase_id,
        plan_number=plan_number,
        title=body.title,
        description=body.description,
        tasks_json=body.tasks_json,
    )
    if not plan_id:
        return {"error": "Failed to create plan"}, HTTPStatus.INTERNAL_SERVER_ERROR

    # Set initial status if not default
    if body.status and body.status != "pending":
        update_project_plan(plan_id, status=body.status)

    plan = get_project_plan(plan_id)
    return {"message": "Plan created", "plan": plan}, HTTPStatus.CREATED


@grd_bp.put("/<project_id>/plans/<plan_id>")
def update_plan(path: PlanStatusPath, body: UpdatePlanBody):
    """Update plan fields (title, description, status, tasks_json)."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    plan = get_project_plan(path.plan_id)
    if not plan:
        return {"error": "Plan not found"}, HTTPStatus.NOT_FOUND

    kwargs = {}
    if body.title is not None:
        kwargs["title"] = body.title
    if body.description is not None:
        kwargs["description"] = body.description
    if body.status is not None:
        kwargs["status"] = body.status
    if body.tasks_json is not None:
        kwargs["tasks_json"] = body.tasks_json

    if kwargs:
        update_project_plan(path.plan_id, **kwargs)

    updated = get_project_plan(path.plan_id)
    return {"message": "Plan updated", "plan": updated}, HTTPStatus.OK


@grd_bp.delete("/<project_id>/plans/<plan_id>")
def delete_plan(path: PlanStatusPath):
    """Delete a plan."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    if not delete_project_plan(path.plan_id):
        return {"error": "Plan not found"}, HTTPStatus.NOT_FOUND

    return {"message": "Plan deleted"}, HTTPStatus.OK


# ---------------------------------------------------------------------------
# Project AI Chat endpoints
# ---------------------------------------------------------------------------


def _resolve_manager_agent(project: dict) -> Optional[str]:
    """Resolve or auto-create the manager super agent for a project.

    Returns the super_agent_id or None on failure.
    """
    sa_id = project.get("manager_super_agent_id")
    if sa_id and get_super_agent(sa_id):
        return sa_id

    project_name = project.get("name", "Unnamed Project")
    sa_id = add_super_agent(
        name=f"{project_name} Manager",
        description=f"AI manager for project '{project_name}'. Manages kanban plans via chat.",
        backend_type="claude",
    )
    if not sa_id:
        return None

    role_content = (
        f"You are the project manager for '{project_name}'.\n\n"
        "You help users manage their kanban board by creating, updating, moving, and deleting plan cards.\n\n"
        "## Available Actions\n\n"
        "When the user asks you to modify the kanban board, emit action markers in your response.\n"
        "Each action must be wrapped in markers exactly like this:\n\n"
        "---PLAN_ACTION---\n"
        '{"action": "create", "phase_id": "...", "title": "...", "description": "...", "status": "pending"}\n'
        "---END_PLAN_ACTION---\n\n"
        "Supported actions:\n"
        '- create: {"action": "create", "phase_id": "...", "title": "...", "description": "...", "status": "pending|in_progress|completed|failed|in_review"}\n'
        '- update: {"action": "update", "plan_id": "...", "title": "...", "description": "...", "status": "..."}\n'
        '- move: {"action": "move", "plan_id": "...", "status": "pending|in_progress|completed|failed|in_review"}\n'
        '- delete: {"action": "delete", "plan_id": "..."}\n\n'
        "Always confirm what you did after emitting actions. Be conversational and helpful.\n"
        "When listing plans or giving status updates, use the project context provided to you.\n"
    )
    add_super_agent_document(sa_id, "ROLE", "Project Manager Role", role_content)
    update_project(project["id"], manager_super_agent_id=sa_id)
    return sa_id


@grd_bp.post("/<project_id>/chat")
def project_chat(path: ProjectIdPath, body: ProjectChatBody):
    """Send a chat message to the project's AI manager.

    Resolves the manager super agent, creates/reuses a session, injects
    project context, sends the message via the super agent session system,
    and initiates streaming. After the AI responds, plan action markers
    are parsed and executed, with plan_changed deltas pushed to SSE.
    """
    from ..services.chat_state_service import ChatStateService
    from ..services.conversation_streaming import stream_llm_response
    from ..services.project_chat_service import (
        build_project_context,
        execute_plan_actions,
    )
    from ..services.super_agent_session_service import SuperAgentSessionService

    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    sa_id = _resolve_manager_agent(project)
    if not sa_id:
        return {"error": "Failed to resolve manager agent"}, HTTPStatus.INTERNAL_SERVER_ERROR

    # Create or reuse active session
    session_id, error = SuperAgentSessionService.create_session(sa_id)
    if not session_id:
        # Try to find an existing active session
        from ..database import get_super_agent_sessions

        existing = get_super_agent_sessions(sa_id)
        active = [s for s in existing if s.get("status") == "active"]
        if active:
            session_id = active[0]["id"]
        else:
            return {"error": error or "Failed to create session"}, HTTPStatus.INTERNAL_SERVER_ERROR

    # Ensure ChatStateService tracks this session
    ChatStateService.init_session(session_id)

    # Inject project context as system prompt supplement
    project_context = build_project_context(path.project_id, body.milestone_id)

    # Add user message
    success, msg_error = SuperAgentSessionService.send_message(session_id, body.content)
    if not success:
        return {"error": msg_error}, HTTPStatus.BAD_REQUEST

    # Push user message delta
    ChatStateService.push_delta(session_id, "message", {"role": "user", "content": body.content})

    # Capture values for background thread
    _session_id = session_id
    _sa_id = sa_id
    _project_id = path.project_id
    _content = body.content
    _project_context = project_context

    def _stream_and_execute():
        try:
            ChatStateService.push_status(_session_id, "streaming")

            # Assemble system prompt with project context injected
            system_prompt = SuperAgentSessionService.assemble_system_prompt(_sa_id, _session_id)
            system_prompt = (system_prompt or "") + "\n\n" + _project_context

            state = SuperAgentSessionService.get_session_state(_session_id)
            llm_messages = [{"role": "system", "content": system_prompt}]
            if state and state.get("conversation_log"):
                for msg in state["conversation_log"]:
                    llm_messages.append(
                        {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                    )

            accumulated = []
            for chunk in stream_llm_response(llm_messages, backend="claude"):
                if chunk:
                    accumulated.append(chunk)
                    ChatStateService.push_delta(_session_id, "content_delta", {"content": chunk})

            full_response = "".join(accumulated)
            if full_response:
                SuperAgentSessionService.add_assistant_message(_session_id, full_response)

            ChatStateService.push_delta(
                _session_id, "finish", {"content": full_response, "backend": "claude"}
            )

            # Parse and execute plan actions from the response
            results = execute_plan_actions(_project_id, full_response)
            for result in results:
                ChatStateService.push_delta(_session_id, "plan_changed", result)

            ChatStateService.push_status(_session_id, "idle")

        except Exception as e:
            logger.error("Project chat streaming error: %s", e, exc_info=True)
            ChatStateService.push_delta(_session_id, "error", {"message": str(e)})
            ChatStateService.push_status(_session_id, "idle")

    thread = threading.Thread(target=_stream_and_execute, daemon=True)
    thread.start()

    return {
        "status": "streaming",
        "session_id": session_id,
        "super_agent_id": sa_id,
    }, HTTPStatus.OK


@grd_bp.get("/<project_id>/chat/stream")
def project_chat_stream(path: ProjectIdPath):
    """SSE stream for project chat -- proxies to the manager's session stream.

    Resolves the manager super agent and its active session, then delegates
    to ChatStateService.subscribe() for SSE event delivery.
    """
    from ..services.chat_state_service import ChatStateService

    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    sa_id = project.get("manager_super_agent_id")
    if not sa_id:
        return {"error": "No manager agent configured"}, HTTPStatus.NOT_FOUND

    # Find active session for this super agent
    from ..database import get_super_agent_sessions

    sessions = get_super_agent_sessions(sa_id)
    active = [s for s in sessions if s.get("status") == "active"]
    if not active:
        return {"error": "No active chat session"}, HTTPStatus.NOT_FOUND

    session_id = active[0]["id"]

    last_event_id = request.headers.get("Last-Event-ID", "0")
    try:
        last_seq = int(last_event_id)
    except (ValueError, TypeError):
        last_seq = 0

    def generate():
        for event in ChatStateService.subscribe(session_id, last_seq=last_seq):
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


# ---------------------------------------------------------------------------
# Planning endpoints
# ---------------------------------------------------------------------------


@grd_bp.post("/<project_id>/planning/invoke")
def invoke_planning(path: ProjectIdPath, body: InvokePlanningBody):
    """Invoke a GRD planning command in a new PTY session."""
    result = GrdPlanningService.invoke_command(path.project_id, body.command, body.args)
    if "error" in result:
        status = (
            HTTPStatus.CONFLICT if "already active" in result["error"] else HTTPStatus.BAD_REQUEST
        )
        return result, status
    return result, HTTPStatus.CREATED


@grd_bp.get("/<project_id>/planning/status")
def get_planning_status(path: ProjectIdPath):
    """Get GRD initialization status and active planning session for a project."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    active_session_id = GrdPlanningService.get_active_planning_session(path.project_id)
    grd_init_status = GrdPlanningService.get_init_status(path.project_id)
    return {
        "grd_init_status": grd_init_status,
        "active_session_id": active_session_id,
    }, HTTPStatus.OK


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
