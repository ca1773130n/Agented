"""Wave 74 — GRD project management (~23 routes).

Sync, milestones, phases, plans, project chat POST, planning, sessions,
ralph/team session creators, and per-session control endpoints. Two SSE
streams stay on Flask until the streaming wave:
  - /api/projects/{id}/chat/stream
  - /api/projects/{id}/sessions/{session_id}/stream
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)

from app.utils.timezone import utcnow as _utcnow

from app.database import (
    add_project_phase,
    add_project_plan,
    add_super_agent_document,
    create_super_agent,
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
from app.services.execution_type_handler import get_handler
from app.services.grd_cli_service import GrdCliService
from app.services.grd_planning_service import GrdPlanningService
from app.services.grd_sync_service import GrdSyncService
from app.services.project_session_manager import ProjectSessionManager
from app.services.project_workspace_service import ProjectWorkspaceService

logger = logging.getLogger(__name__)


VALID_PLAN_STATUSES = {"pending", "in_progress", "completed", "failed", "in_review"}


def _ensure_project(project_id: str) -> dict:
    project = get_project(project_id)
    if not project:
        raise NotFoundException(detail="Project not found")
    return project


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


@get("/{project_id:str}/sync", sync_to_thread=False)
def sync_status(project_id: str) -> dict[str, Any]:
    project = _ensure_project(project_id)
    states = get_project_sync_states(project_id)
    return {
        "last_synced_at": project.get("grd_sync_at"),
        "file_count": len(states),
        "grd_available": GrdCliService._binary_available,
    }


@post("/{project_id:str}/sync", sync_to_thread=False)
def trigger_sync(project_id: str) -> dict[str, Any]:
    _ensure_project(project_id)
    try:
        local_path = ProjectWorkspaceService.resolve_working_directory(project_id)
    except ValueError as e:
        raise ClientException(detail=str(e)) from e
    planning_dir = str(Path(local_path).expanduser().resolve() / ".planning")
    result = GrdSyncService.sync_project(project_id, planning_dir)
    update_project(project_id, grd_sync_at=_utcnow().isoformat())
    return {
        "synced": result["synced"],
        "skipped": result["skipped"],
        "errors": result["errors"],
    }


# ---------------------------------------------------------------------------
# Milestones / Phases / Plans
# ---------------------------------------------------------------------------


@get("/{project_id:str}/milestones", sync_to_thread=False)
def list_milestones(project_id: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    _ensure_project(project_id)
    from app.db.grd import count_milestones_by_project

    milestones = get_milestones_by_project(project_id, limit=limit, offset=offset)
    return {
        "milestones": milestones,
        "total_count": count_milestones_by_project(project_id),
    }


@get("/{project_id:str}/phases", sync_to_thread=False)
def list_phases(project_id: str, milestone_id: Optional[str] = None) -> dict[str, Any]:
    _ensure_project(project_id)
    if milestone_id:
        phases = get_phases_by_milestone(milestone_id)
    else:
        phases = []
        for ms in get_milestones_by_project(project_id):
            phases.extend(get_phases_by_milestone(ms["id"]))
    return {"phases": phases}


@post("/{project_id:str}/phases", status_code=201, sync_to_thread=False)
def create_phase(project_id: str, data: dict) -> dict[str, Any]:
    _ensure_project(project_id)
    body = data or {}
    milestone_id = body.get("milestone_id")
    name = body.get("name")
    if not milestone_id or not name:
        raise ClientException(detail="milestone_id and name are required")

    ms_ids = {m["id"] for m in get_milestones_by_project(project_id)}
    if milestone_id not in ms_ids:
        raise NotFoundException(detail="Milestone not found in this project")

    existing = get_phases_by_milestone(milestone_id)
    next_number = max((p["phase_number"] for p in existing), default=0) + 1
    phase_id = add_project_phase(
        milestone_id=milestone_id,
        phase_number=next_number,
        name=name,
        goal=body.get("goal"),
    )
    if not phase_id:
        raise HTTPException(status_code=500, detail="Failed to create phase")
    return {
        "message": "Phase created",
        "phase": {
            "id": phase_id,
            "milestone_id": milestone_id,
            "phase_number": next_number,
            "name": name,
            "status": body.get("status", "pending"),
            "goal": body.get("goal"),
            "verification_level": "sanity",
            "wave": None,
            "plan_count": 0,
        },
    }


@get("/{project_id:str}/plans", sync_to_thread=False)
def list_plans(project_id: str, phase_id: Optional[str] = None) -> dict[str, Any]:
    _ensure_project(project_id)
    if phase_id:
        plans = get_plans_by_phase(phase_id)
    else:
        plans = []
        for ms in get_milestones_by_project(project_id):
            for phase in get_phases_by_milestone(ms["id"]):
                plans.extend(get_plans_by_phase(phase["id"]))
    return {"plans": plans}


@put("/{project_id:str}/plans/{plan_id:str}/status", sync_to_thread=False)
def update_plan_status(project_id: str, plan_id: str, data: dict) -> dict[str, Any]:
    _ensure_project(project_id)
    plan = get_project_plan(plan_id)
    if not plan:
        raise NotFoundException(detail="Plan not found")
    body = data or {}
    status = body.get("status")
    if status not in VALID_PLAN_STATUSES:
        raise ClientException(
            detail=(
                f"Invalid status: {status}. "
                f"Must be one of: {', '.join(sorted(VALID_PLAN_STATUSES))}"
            )
        )
    update_project_plan(plan_id, status=status)

    try:
        local_path = ProjectWorkspaceService.resolve_working_directory(project_id)
    except ValueError:
        local_path = None
    if local_path and GrdCliService._binary_available:
        try:
            states = get_project_sync_states(project_id)
            match = next(
                (
                    s
                    for s in states
                    if s["entity_id"] == plan_id and s["entity_type"] == "plan"
                ),
                None,
            )
            if match:
                cli_result = GrdCliService.update_plan_status(
                    local_path, match["file_path"], status
                )
                if not cli_result.get("success"):
                    logger.warning(
                        "GRD CLI plan status write failed for plan %s: %s",
                        plan_id,
                        cli_result.get("error"),
                    )
            else:
                logger.debug("No sync state match for plan %s", plan_id)
        except Exception as e:
            logger.warning("GRD CLI plan status write error for plan %s: %s", plan_id, e)

    return {"message": "Plan status updated", "plan": get_project_plan(plan_id)}


@post("/{project_id:str}/plans", status_code=201, sync_to_thread=False)
def create_plan(project_id: str, data: dict) -> dict[str, Any]:
    _ensure_project(project_id)
    body = data or {}
    phase_id = body.get("phase_id")
    title = body.get("title")
    if not phase_id or not title:
        raise ClientException(detail="phase_id and title are required")

    existing = get_plans_by_phase(phase_id)
    plan_number = max((p["plan_number"] for p in existing), default=0) + 1
    plan_id = add_project_plan(
        phase_id=phase_id,
        plan_number=plan_number,
        title=title,
        description=body.get("description"),
        tasks_json=body.get("tasks_json"),
    )
    if not plan_id:
        raise HTTPException(status_code=500, detail="Failed to create plan")
    status = body.get("status", "pending")
    if status and status != "pending":
        update_project_plan(plan_id, status=status)
    return {"message": "Plan created", "plan": get_project_plan(plan_id)}


@put("/{project_id:str}/plans/{plan_id:str}", sync_to_thread=False)
def update_plan(project_id: str, plan_id: str, data: dict) -> dict[str, Any]:
    _ensure_project(project_id)
    if not get_project_plan(plan_id):
        raise NotFoundException(detail="Plan not found")
    kwargs = {k: v for k, v in (data or {}).items() if v is not None and k in {
        "title", "description", "status", "tasks_json"
    }}
    if kwargs:
        update_project_plan(plan_id, **kwargs)
    return {"message": "Plan updated", "plan": get_project_plan(plan_id)}


@delete("/{project_id:str}/plans/{plan_id:str}", status_code=200, sync_to_thread=False)
def delete_plan(project_id: str, plan_id: str) -> dict[str, Any]:
    _ensure_project(project_id)
    if not delete_project_plan(plan_id):
        raise NotFoundException(detail="Plan not found")
    return {"message": "Plan deleted"}


# ---------------------------------------------------------------------------
# Project chat (POST only — SSE stream stays on Flask)
# ---------------------------------------------------------------------------


def _resolve_manager_agent(project: dict) -> Optional[str]:
    sa_id = project.get("manager_super_agent_id")
    if sa_id and get_super_agent(sa_id):
        return sa_id
    project_name = project.get("name", "Unnamed Project")
    sa_id = create_super_agent(
        name=f"{project_name} Manager",
        description=(
            f"AI manager for project '{project_name}'. Manages kanban plans via chat."
        ),
        backend_type="claude",
    )
    if not sa_id:
        return None
    role_content = (
        f"You are the project manager for '{project_name}'.\n\n"
        "You help users manage their kanban board by creating, updating, moving, "
        "and deleting plan cards.\n\n"
        "## Available Actions\n\n"
        "When the user asks you to modify the kanban board, emit action markers "
        "in your response.\n"
        "Each action must be wrapped in markers exactly like this:\n\n"
        "---PLAN_ACTION---\n"
        '{"action": "create", "phase_id": "...", "title": "...", '
        '"description": "...", "status": "pending"}\n'
        "---END_PLAN_ACTION---\n\n"
        "Supported actions:\n"
        '- create: {"action": "create", "phase_id": "...", "title": "...", '
        '"description": "...", "status": "pending|in_progress|completed|failed|in_review"}\n'
        '- update: {"action": "update", "plan_id": "...", "title": "...", '
        '"description": "...", "status": "..."}\n'
        '- move: {"action": "move", "plan_id": "...", '
        '"status": "pending|in_progress|completed|failed|in_review"}\n'
        '- delete: {"action": "delete", "plan_id": "..."}\n\n'
        "Always confirm what you did after emitting actions. Be conversational and helpful.\n"
        "When listing plans or giving status updates, use the project context provided to you.\n"
    )
    add_super_agent_document(sa_id, "ROLE", "Project Manager Role", role_content)
    update_project(project["id"], manager_super_agent_id=sa_id)
    return sa_id


@post("/{project_id:str}/chat", sync_to_thread=False)
def project_chat(project_id: str, data: dict) -> dict[str, Any]:
    from app.services.chat_state_service import ChatStateService
    from app.services.cli_agent_runner_service import (
        is_yolo_mode_enabled,
        resolve_account_config_dir,
        should_route_via_cli_agent,
        stream_via_cli_agent,
    )
    from app.services.conversation_streaming import stream_llm_response
    from app.services.project_chat_service import (
        build_project_context,
        execute_plan_actions,
    )
    from app.services.super_agent_session_service import SuperAgentSessionService

    body = data or {}
    content = body.get("content")
    if not content:
        raise ClientException(detail="content is required")
    milestone_id = body.get("milestone_id")
    raw_override = body.get("use_cli_agent")
    use_cli_agent = raw_override if isinstance(raw_override, bool) else None

    project = _ensure_project(project_id)
    sa_id = _resolve_manager_agent(project)
    if not sa_id:
        raise HTTPException(status_code=500, detail="Failed to resolve manager agent")

    session_id, error = SuperAgentSessionService.create_session(sa_id)
    if not session_id:
        from app.database import get_super_agent_sessions

        existing = get_super_agent_sessions(sa_id)
        active = [s for s in existing if s.get("status") == "active"]
        if active:
            session_id = active[0]["id"]
        else:
            raise HTTPException(
                status_code=500, detail=error or "Failed to create session"
            )

    ChatStateService.init_session(session_id)
    project_context = build_project_context(project_id, milestone_id)

    success, msg_error = SuperAgentSessionService.send_message(session_id, content)
    if not success:
        raise ClientException(detail=msg_error)

    ChatStateService.push_delta(session_id, "message", {"role": "user", "content": content})

    _session_id = session_id
    _sa_id = sa_id
    _project_id = project_id
    _content = content
    _project_context = project_context

    def _stream_and_execute() -> None:
        try:
            ChatStateService.push_status(_session_id, "streaming")
            system_prompt = SuperAgentSessionService.assemble_system_prompt(_sa_id, _session_id)
            system_prompt = (system_prompt or "") + "\n\n" + _project_context
            state = SuperAgentSessionService.get_session_state(_session_id)
            llm_messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt}
            ]
            if state and state.get("conversation_log"):
                for msg in state["conversation_log"]:
                    llm_messages.append(
                        {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                    )
            accumulated: list[str] = []
            if should_route_via_cli_agent("claude", use_cli_agent):
                stream_iter = stream_via_cli_agent(
                    llm_messages,
                    backend="claude",
                    cwd=None,
                    yolo=is_yolo_mode_enabled(),
                    config_dir=resolve_account_config_dir(None, "claude"),
                )
            else:
                stream_iter = stream_llm_response(llm_messages, backend="claude")
            for chunk in stream_iter:
                if chunk:
                    accumulated.append(chunk)
                    ChatStateService.push_delta(_session_id, "content_delta", {"content": chunk})
            full_response = "".join(accumulated)
            if full_response:
                SuperAgentSessionService.add_assistant_message(_session_id, full_response)
            ChatStateService.push_delta(
                _session_id, "finish", {"content": full_response, "backend": "claude"}
            )
            for result in execute_plan_actions(_project_id, full_response):
                ChatStateService.push_delta(_session_id, "plan_changed", result)
            ChatStateService.push_status(_session_id, "idle")
        except Exception as e:
            logger.error("Project chat streaming error: %s", e, exc_info=True)
            ChatStateService.push_delta(_session_id, "error", {"message": str(e)})
            ChatStateService.push_status(_session_id, "idle")

    threading.Thread(target=_stream_and_execute, daemon=True).start()
    return {"status": "streaming", "session_id": session_id, "super_agent_id": sa_id}


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


@post("/{project_id:str}/planning/invoke", status_code=201, sync_to_thread=False)
def invoke_planning(project_id: str, data: dict) -> dict[str, Any]:
    body = data or {}
    command = body.get("command")
    if not command:
        raise ClientException(detail="command is required")
    result = GrdPlanningService.invoke_command(project_id, command, body.get("args"))
    if "error" in result:
        if "already active" in result["error"]:
            raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=result["error"])
        raise ClientException(detail=result["error"])
    return result


@get("/{project_id:str}/planning/status", sync_to_thread=False)
def planning_status(project_id: str) -> dict[str, Any]:
    _ensure_project(project_id)
    return {
        "grd_init_status": GrdPlanningService.get_init_status(project_id),
        "active_session_id": GrdPlanningService.get_active_planning_session(project_id),
    }


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@post("/{project_id:str}/sessions", status_code=201, sync_to_thread=False)
def create_session(project_id: str, data: dict) -> dict[str, Any]:
    _ensure_project(project_id)
    body = data or {}
    cmd = body.get("cmd")
    if not cmd or not isinstance(cmd, list):
        raise ClientException(detail="cmd (list) is required")
    execution_type = body.get("execution_type", "direct")
    handler = get_handler(execution_type)
    if not handler:
        raise ClientException(detail=f"Unknown execution_type: {execution_type}")
    cwd = body.get("cwd")
    if not cwd:
        try:
            cwd = ProjectWorkspaceService.resolve_working_directory(project_id)
        except ValueError as e:
            raise ClientException(detail=str(e)) from e
    return handler.start(
        {
            "project_id": project_id,
            "cmd": cmd,
            "cwd": cwd,
            "phase_id": body.get("phase_id"),
            "plan_id": body.get("plan_id"),
            "agent_id": body.get("agent_id"),
            "worktree_path": body.get("worktree_path"),
            "execution_type": execution_type,
            "execution_mode": body.get("execution_mode", "autonomous"),
        }
    )


@get("/{project_id:str}/sessions", sync_to_thread=False)
def list_sessions(project_id: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    _ensure_project(project_id)
    from app.db.grd import count_sessions_by_project

    sessions = get_sessions_by_project(project_id, limit=limit, offset=offset)
    return {"sessions": sessions, "total_count": count_sessions_by_project(project_id)}


@get("/{project_id:str}/sessions/{session_id:str}/output", sync_to_thread=False)
def session_output(
    project_id: str, session_id: str, last_n: int = 100
) -> dict[str, Any]:
    del project_id
    last_n = max(1, min(last_n, 10000))
    lines = ProjectSessionManager.get_output(session_id, last_n=last_n)
    return {"lines": lines, "count": len(lines)}


@post("/{project_id:str}/sessions/{session_id:str}/stop", sync_to_thread=False)
def stop_session(project_id: str, session_id: str) -> dict[str, Any]:
    del project_id
    if not ProjectSessionManager.stop_session(session_id):
        raise NotFoundException(detail="Session not found or already stopped")
    return {"message": "Session stopped", "session_id": session_id}


@post("/{project_id:str}/sessions/{session_id:str}/pause", sync_to_thread=False)
def pause_session(project_id: str, session_id: str) -> dict[str, Any]:
    del project_id
    if not ProjectSessionManager.pause_session(session_id):
        raise NotFoundException(detail="Session not found")
    return {"message": "Session paused", "session_id": session_id}


@post("/{project_id:str}/sessions/{session_id:str}/resume", sync_to_thread=False)
def resume_session(project_id: str, session_id: str) -> dict[str, Any]:
    del project_id
    if not ProjectSessionManager.resume_session(session_id):
        raise NotFoundException(detail="Session not found")
    return {"message": "Session resumed", "session_id": session_id}


@post("/{project_id:str}/sessions/{session_id:str}/input", sync_to_thread=False)
def session_input(project_id: str, session_id: str, data: dict) -> dict[str, Any]:
    del project_id
    text = (data or {}).get("text")
    if text is None:
        raise ClientException(detail="text is required")
    sanitized = "".join(
        ch for ch in text if ch in {"\t", "\n", "\r"} or (32 <= ord(ch) < 127)
    )
    if not ProjectSessionManager.send_input(session_id, sanitized):
        raise NotFoundException(detail="Session not found or not active")
    return {"message": "Input sent", "session_id": session_id}


@post("/{project_id:str}/sessions/ralph", status_code=201, sync_to_thread=False)
def create_ralph_session(project_id: str, data: dict) -> dict[str, Any]:
    _ensure_project(project_id)
    body = data or {}
    cwd = body.get("cwd")
    if not cwd:
        try:
            cwd = ProjectWorkspaceService.resolve_working_directory(project_id)
        except ValueError as e:
            raise ClientException(detail=str(e)) from e
    handler = get_handler("ralph_loop")
    if not handler:
        raise HTTPException(status_code=500, detail="Ralph loop handler not registered")
    result = handler.start(
        {
            "project_id": project_id,
            "cwd": cwd,
            "phase_id": body.get("phase_id"),
            "plan_id": body.get("plan_id"),
            "agent_id": body.get("agent_id"),
            "ralph_config": body.get("ralph_config") or {},
        }
    )
    if "error" in result:
        raise ClientException(detail=result["error"])
    return result


@post("/{project_id:str}/sessions/team", status_code=201, sync_to_thread=False)
def create_team_session(project_id: str, data: dict) -> dict[str, Any]:
    _ensure_project(project_id)
    body = data or {}
    cwd = body.get("cwd")
    if not cwd:
        try:
            cwd = ProjectWorkspaceService.resolve_working_directory(project_id)
        except ValueError as e:
            raise ClientException(detail=str(e)) from e
    handler = get_handler("team_spawn")
    if not handler:
        raise HTTPException(status_code=500, detail="Team spawn handler not registered")
    result = handler.start(
        {
            "project_id": project_id,
            "cwd": cwd,
            "phase_id": body.get("phase_id"),
            "plan_id": body.get("plan_id"),
            "agent_id": body.get("agent_id"),
            "team_config": body.get("team_config") or {},
        }
    )
    if "error" in result:
        raise ClientException(detail=result["error"])
    return result


@get("/{project_id:str}/sessions/{session_id:str}/monitor", sync_to_thread=False)
def monitor_session(project_id: str, session_id: str) -> dict[str, Any]:
    del project_id
    info = ProjectSessionManager.get_session_info(session_id)
    if info:
        execution_type = info.get("execution_type", "direct")
    else:
        from app.database import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT execution_type FROM project_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            raise NotFoundException(detail="Session not found")
        execution_type = row["execution_type"] if row["execution_type"] else "direct"
    handler = get_handler(execution_type)
    if not handler:
        raise NotFoundException(
            detail=f"No handler for execution_type: {execution_type}"
        )
    result = handler.monitor(session_id)
    result["session_id"] = session_id
    result["execution_type"] = execution_type
    return result


grd_router = Router(
    path="/api/projects",
    route_handlers=[
        sync_status,
        trigger_sync,
        list_milestones,
        list_phases,
        create_phase,
        list_plans,
        update_plan_status,
        create_plan,
        update_plan,
        delete_plan,
        project_chat,
        invoke_planning,
        planning_status,
        create_session,
        list_sessions,
        session_output,
        stop_session,
        pause_session,
        resume_session,
        session_input,
        create_ralph_session,
        create_team_session,
        monitor_session,
    ],
)
