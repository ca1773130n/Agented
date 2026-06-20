"""Wave 74 — GRD project management (~23 routes).

Sync, milestones, phases, plans, project chat POST, planning, sessions,
ralph/team session creators, and per-session control endpoints. Two SSE
streams stay on Flask until the streaming wave:
  - /api/projects/{id}/chat/stream
  - /api/projects/{id}/sessions/{session_id}/stream
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from http import HTTPStatus
from pathlib import Path
from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)
from litestar.response import Stream

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
from app.db.projects import (
    get_harness_setup_status,
    get_harness_setup_steps,
    set_harness_setup_status,
)
from app.services.execution_type_handler import get_handler
from app.services.grd_cli_service import GrdCliService
from app.services.grd_planning_service import GrdPlanningService
from app.services.grd_sync_service import GrdSyncService
from app.services.project_session_manager import ProjectSessionManager
from app.services.project_workspace_service import ProjectWorkspaceService
from app.services.team_harness_setup_service import TeamHarnessSetupService
from app.utils.timezone import utcnow as _utcnow

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
    # v0.7.84 — surface both binary detections so the frontend can
    # gate Ouroboros-only features (think / health / dead-end /
    # genome) on ``gd_available`` separately from the legacy
    # ``grd-tools`` write surface.
    avail = GrdCliService.available()
    return {
        "last_synced_at": project.get("grd_sync_at"),
        "file_count": len(states),
        "grd_available": avail["grd_tools_available"],
        "gd_available": avail["gd_available"],
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
# v0.7.84 — Ouroboros surface (GRD v0.3.24)
#
# Thin pass-through to the gd / grd-tools CLIs. Storage / parsing of
# the resulting artifacts (DEAD-ENDS.md, GENOME.md, REFLECTION.md) is
# handled by the sync layer in a follow-up PR; these routes are the
# write/read primitives the frontend needs to drive the loop.
# ---------------------------------------------------------------------------


def _project_cwd(project_id: str) -> str:
    """Resolve the on-disk working directory for a project, raising the
    standard 400 client exception on misconfiguration.
    """
    try:
        return ProjectWorkspaceService.resolve_working_directory(project_id)
    except ValueError as e:
        raise ClientException(detail=str(e)) from e


@get("/{project_id:str}/grd/health", sync_to_thread=False)
def grd_health(project_id: str) -> dict[str, Any]:
    """v0.7.84 — ``gd health`` weighted drift score + blockers.

    Returns the GRD JSON payload verbatim under ``raw`` for forward
    compatibility, plus a small set of normalized top-level fields the
    frontend reads directly.
    """
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    result = GrdCliService.get_health(cwd)
    if not result["success"]:
        # GRD missing or non-JSON output — surface as 503 so the
        # frontend can show "GRD unavailable" instead of a generic 5xx.
        from litestar.exceptions import HTTPException

        raise HTTPException(
            status_code=503,
            detail=result.get("error") or "gd health unavailable",
        )
    data = result.get("data") or {}
    return {
        "drift_weighted": data.get("drift_weighted"),
        "drift_exceeded": data.get("drift_exceeded"),
        "blocker_count": data.get("blocker_count"),
        "blockers": data.get("blockers", []),
        "deferred_validations": data.get("deferred_validations", []),
        "raw": data,
    }


@post("/{project_id:str}/grd/think", sync_to_thread=False)
def grd_think(project_id: str) -> dict[str, Any]:
    """v0.7.84 — ``gd think`` one-shot project briefing.

    Writes a markdown briefing under ``.planning/thoughts/<ts>-thinking.md``
    and returns the JSON snapshot. Useful as a context primer before
    spawning a Claude Code session (planned wire-up in PR C).
    """
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    result = GrdCliService.think(cwd)
    if not result["success"]:
        from litestar.exceptions import HTTPException

        raise HTTPException(
            status_code=503,
            detail=result.get("error") or "gd think unavailable",
        )
    return result["data"] or {}


@post("/{project_id:str}/grd/dead-ends", status_code=201, sync_to_thread=False)
def grd_add_dead_end(project_id: str, data: dict) -> dict[str, Any]:
    """v0.7.84 — append an entry to ``.planning/DEAD-ENDS.md``.

    Body shape:
        {"approach": str, "reason": str, "phase": str|null}

    Returns the raw CLI output plus the inputs echoed back so the
    frontend can render the new entry without a separate read.
    """
    _ensure_project(project_id)
    body = data or {}
    approach = (body.get("approach") or "").strip()
    reason = (body.get("reason") or "").strip()
    phase = body.get("phase")
    if not approach or not reason:
        raise ClientException(detail="approach and reason are required")
    cwd = _project_cwd(project_id)
    result = GrdCliService.add_dead_end(
        cwd, approach=approach, reason=reason, phase=str(phase) if phase else None
    )
    if not result["success"]:
        from litestar.exceptions import HTTPException

        raise HTTPException(
            status_code=503,
            detail=result.get("error") or "dead-end add failed",
        )
    return {
        "approach": approach,
        "reason": reason,
        "phase": phase,
        "output": result.get("output"),
    }


@post(
    "/{project_id:str}/grd/dead-ends/promote-from-phase/{phase:str}",
    sync_to_thread=False,
)
def grd_promote_dead_ends(project_id: str, phase: str) -> dict[str, Any]:
    """v0.7.84 — promote ``verdict: falsified`` reflections from a
    phase into ``.planning/DEAD-ENDS.md``.
    """
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    result = GrdCliService.promote_dead_ends_from_phase(cwd, phase)
    if not result["success"]:
        from litestar.exceptions import HTTPException

        raise HTTPException(
            status_code=503,
            detail=result.get("error") or "dead-end promotion failed",
        )
    return {"phase": phase, "output": result.get("output")}


@get("/{project_id:str}/grd/genome", sync_to_thread=False)
def grd_genome(project_id: str) -> dict[str, Any]:
    """v0.7.84 — read ``.planning/GENOME.md`` via ``gd-tools genome show``.

    Returns ``{exists: bool, content: str|null}``. Missing GENOME.md
    is a 200 with ``exists=false`` rather than a 404 because the file
    is genuinely optional.
    """
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    result = GrdCliService.genome_show(cwd)
    if not result["success"]:
        from litestar.exceptions import HTTPException

        raise HTTPException(
            status_code=503,
            detail=result.get("error") or "genome show unavailable",
        )
    data = result.get("data") or {}
    return {
        "exists": bool(data.get("exists")),
        "content": data.get("content"),
        "raw": data,
    }


@post("/{project_id:str}/grd/genome/snapshot", sync_to_thread=False)
def grd_genome_snapshot(project_id: str) -> dict[str, Any]:
    """v0.7.84 — append a snapshot to ``.planning/GENOME.md`` via
    ``gd-tools genome snapshot``.
    """
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    result = GrdCliService.genome_snapshot(cwd)
    if not result["success"]:
        from litestar.exceptions import HTTPException

        raise HTTPException(
            status_code=503,
            detail=result.get("error") or "genome snapshot failed",
        )
    return {"output": result.get("output")}


@post("/{project_id:str}/grd/genome/patterns", sync_to_thread=False)
def grd_mine_patterns(project_id: str, data: dict | None) -> dict[str, Any]:
    """GRD 0.4.1 ``gd patterns`` — deterministic statistical pattern miner over
    REFLECTION.md history. ``apply`` writes ``.planning/GENOME-SUGGESTIONS.md``.
    Body: ``{apply?, min_occurrences?, effect_size?, fdr_q?}``. The latest run
    is mirrored into ``grd_genome_suggestions``."""
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    body = data or {}
    from app.services.grd_genome_patterns_runner import mine_patterns

    result = mine_patterns(
        project_id,
        cwd,
        apply=bool(body.get("apply")),
        min_occurrences=body.get("min_occurrences"),
        effect_size=body.get("effect_size"),
        fdr_q=body.get("fdr_q"),
    )
    if not result["success"]:
        raise ClientException(detail=result.get("error") or "gd patterns failed")
    return result


@get("/{project_id:str}/grd/genome/suggestions", sync_to_thread=False)
def grd_get_genome_suggestions(project_id: str) -> dict[str, Any]:
    """The latest mirrored ``gd patterns`` run for this project."""
    _ensure_project(project_id)
    from app.db import get_genome_suggestions

    row = get_genome_suggestions(project_id)
    if not row:
        raise NotFoundException(detail="No pattern-mining run recorded for this project")
    return row


@post("/{project_id:str}/grd/genome/promote-suggestion", sync_to_thread=False)
def grd_promote_suggestion(project_id: str, data: dict) -> dict[str, Any]:
    """Promote one mined suggestion into ``GENOME.md`` via
    ``gd genome promote-suggestion <slug>``. Body: ``{slug}`` (e.g.
    ``"<token>-rate"``)."""
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    slug = (data or {}).get("slug")
    if not slug:
        raise ClientException(detail="slug is required")
    from app.services.grd_genome_patterns_runner import promote_suggestion

    result = promote_suggestion(cwd, str(slug))
    if not result["success"]:
        raise ClientException(detail=result.get("error") or "promote-suggestion failed")
    return result


@post("/{project_id:str}/grd/verify/mechanical/{phase:str}", sync_to_thread=False)
def grd_verify_mechanical(project_id: str, phase: str) -> dict[str, Any]:
    """v0.7.84 — bundle the four PLAN.md mechanical checks via
    ``gd-tools verify mechanical --phase <N>``. Faster than the full
    ``/grd:verify-phase`` agent flow; intended as a pre-gate.
    """
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    result = GrdCliService.verify_mechanical(cwd, phase)
    return {
        "success": result["success"],
        "output": result.get("output"),
        "error": result.get("error"),
        "phase": phase,
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
                (s for s in states if s["entity_id"] == plan_id and s["entity_type"] == "plan"),
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
    kwargs = {
        k: v
        for k, v in (data or {}).items()
        if v is not None and k in {"title", "description", "status", "tasks_json"}
    }
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
        description=(f"AI manager for project '{project_name}'. Manages kanban plans via chat."),
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
        resolve_execution_driver,
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
            raise HTTPException(status_code=500, detail=error or "Failed to create session")

    ChatStateService.init_session(session_id)
    project_context = build_project_context(project_id, milestone_id)

    # Derive the backend from the SuperAgent instead of hardcoding a backend
    # name (REQ-12 anti-regression). Fall back to the SA's backend_type; a
    # None backend is passed through to the stream/runner, which applies its
    # own default — we never reintroduce a hardcoded backend literal here.
    _sa = get_super_agent(sa_id)
    backend = (_sa.get("backend_type") if _sa else None) or None

    # Resolve the project workspace so the turn runs in the project clone
    # instead of cwd=None. Degrade to None on unresolvable workspace.
    workspace_cwd: Optional[str] = None
    try:
        workspace_cwd = ProjectWorkspaceService.resolve_working_directory(project_id)
    except ValueError as exc:
        logger.warning(
            "project_chat: could not resolve project %s workspace, running without cwd: %s",
            project_id,
            exc,
        )

    success, msg_error = SuperAgentSessionService.send_message(session_id, content)
    if not success:
        raise ClientException(detail=msg_error)

    ChatStateService.push_delta(session_id, "message", {"role": "user", "content": content})

    _session_id = session_id
    _sa_id = sa_id
    _project_id = project_id
    _content = content
    _project_context = project_context
    _backend = backend
    _workspace_cwd = workspace_cwd

    def _stream_and_execute() -> None:
        try:
            ChatStateService.push_status(_session_id, "streaming")
            system_prompt = SuperAgentSessionService.assemble_system_prompt(_sa_id, _session_id)
            system_prompt = (system_prompt or "") + "\n\n" + _project_context
            state = SuperAgentSessionService.get_session_state(_session_id)
            llm_messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
            if state and state.get("conversation_log"):
                from app.services.conversation_filters import (
                    drop_empty_content_messages,
                )

                llm_messages.extend(drop_empty_content_messages(state["conversation_log"]))
            accumulated: list[str] = []
            # Single source of routing (REQ-10): resolve the driver instead
            # of the legacy 2-way boolean. Returns "cliproxy" | "cli_agent" |
            # "grd"; the resolver degrades grd→cli_agent when GRD/workspace
            # is unavailable, so this never crashes the turn.
            driver = resolve_execution_driver(
                backend=_backend,
                use_cli_agent=use_cli_agent,
                super_agent_id=_sa_id,
                project_id=_project_id,
            )

            # GRD task turns dispatch the grd_chat handler and bridge its PSM
            # output onto chat SSE — consistent with the streaming_helper
            # funnel. Conversational grd turns fall through to cliproxy below.
            if driver == "grd":
                try:
                    from app.services.execution_type_handler import get_handler
                    from app.services.grd_chat_bridge import bridge_psm_to_chat
                    from app.services.project_session_manager import ProjectSessionManager
                    from app.services.turn_classifier_service import classify_turn

                    classification = classify_turn(_content, backend_kind=_backend)
                    if classification.get("shape") == "task":
                        handler = get_handler("grd_chat")
                        result = (
                            handler.start(
                                {
                                    "project_id": _project_id,
                                    "task": _content,
                                    "intent": classification.get("intent"),
                                    "grd_command": classification.get("grd_command"),
                                    "super_agent_id": _sa_id,
                                    "cwd": _workspace_cwd,
                                }
                            )
                            if handler
                            else None
                        )
                        grd_session_id = (result or {}).get("session_id")
                        if grd_session_id:
                            raw_q = ProjectSessionManager.subscribe_raw(grd_session_id)

                            def _psm_events():
                                while True:
                                    event_type, payload = raw_q.get()
                                    if event_type == "__end__":
                                        return
                                    ev = dict(payload or {})
                                    ev.setdefault("type", event_type)
                                    yield ev

                            try:
                                bridge_psm_to_chat(_session_id, _psm_events(), ChatStateService)
                            finally:
                                ProjectSessionManager.unsubscribe_raw(grd_session_id, raw_q)
                            return
                        logger.warning(
                            "project_chat grd dispatch returned no session; "
                            "falling through to cliproxy"
                        )
                except Exception:
                    logger.warning(
                        "project_chat grd dispatch failed; falling through", exc_info=True
                    )
                # Conversational grd (or degrade) → cliproxy below.
                driver = "cliproxy"

            if driver == "cli_agent":
                # Only reachable for a concrete CLI-runnable backend.
                cli_backend = _backend or ""
                stream_iter = stream_via_cli_agent(
                    llm_messages,
                    backend=cli_backend,
                    cwd=_workspace_cwd,
                    yolo=is_yolo_mode_enabled(),
                    config_dir=resolve_account_config_dir(None, cli_backend),
                )
            else:
                stream_iter = stream_llm_response(
                    llm_messages,
                    backend=_backend,
                    cwd=_workspace_cwd,
                    chat_mode="work" if _workspace_cwd else None,
                )
            for chunk in stream_iter:
                if chunk:
                    accumulated.append(chunk)
                    ChatStateService.push_delta(_session_id, "content_delta", {"content": chunk})
            full_response = "".join(accumulated)
            if full_response:
                SuperAgentSessionService.add_assistant_message(_session_id, full_response)
            ChatStateService.push_delta(
                _session_id, "finish", {"content": full_response, "backend": _backend}
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
# Team harness setup (one-click) — REQ-19 / SC1
# ---------------------------------------------------------------------------


@post("/{project_id:str}/harness-setup", status_code=202, sync_to_thread=False)
def trigger_harness_setup(project_id: str) -> dict[str, Any]:
    """Flip status to 'running' and run the six-step setup off-thread.

    Mirrors the grd-chat thread-spawn shape (grd_routes.py:709). The status
    flip here makes a follow-up GET .../status report 'running' immediately,
    even before the background thread sets it itself.

    Idempotent under concurrent triggers: if a setup is already 'running' we
    return without spawning a second thread. ``_step_team_topology`` does an
    existence-check-then-create on the non-deduped SA-instance table, so two
    overlapping runs could TOCTOU-create duplicate instances — the guard
    prevents that.
    """
    _ensure_project(project_id)
    if get_harness_setup_status(project_id) == "running":
        return {"harness_setup_status": "running"}
    set_harness_setup_status(project_id, "running")
    threading.Thread(
        target=TeamHarnessSetupService.setup,
        args=(project_id,),
        daemon=True,
    ).start()
    return {"harness_setup_status": "running"}


@get("/{project_id:str}/harness-setup/status", sync_to_thread=False)
def harness_setup_status(project_id: str) -> dict[str, Any]:
    _ensure_project(project_id)
    return {
        "harness_setup_status": get_harness_setup_status(project_id),
        "steps": get_harness_setup_steps(project_id),
    }


@get(
    "/{project_id:str}/harness-setup/stream",
    media_type="text/event-stream",
    sync_to_thread=False,
)
async def harness_setup_stream(project_id: str) -> Stream:
    """SSE stream of harness-setup step progress.

    Polls the DB every 1s, emits an ``event: step`` frame per changed step row
    (keyed by step_key, diffed on status+detail), and a terminal
    ``event: done`` frame once the overall status reaches ready/failed.
    Mirrors the trace SSE Stream pattern (agents_and_tracing.py:228).
    """
    _ensure_project(project_id)

    async def event_generator():
        seen: dict[str, str] = {}
        deadline = asyncio.get_event_loop().time() + 600.0  # 10 min
        while True:
            steps = get_harness_setup_steps(project_id)
            for s in steps:
                key = s["step_key"]
                sig = f"{s.get('status')}|{s.get('detail')}"
                if seen.get(key) != sig:
                    seen[key] = sig
                    payload = {
                        "step": key,
                        "status": s.get("status"),
                        "detail": s.get("detail"),
                    }
                    yield f"event: step\ndata: {json.dumps(payload, default=str)}\n\n"
            status = get_harness_setup_status(project_id)
            if status in ("ready", "failed"):
                yield (
                    f"event: done\ndata: {json.dumps({'step': '__done__', 'status': status})}\n\n"
                )
                return
            if asyncio.get_event_loop().time() > deadline:
                yield f"event: timeout\ndata: {json.dumps({'reason': 'max_duration'})}\n\n"
                return
            await asyncio.sleep(1.0)

    return Stream(event_generator(), media_type="text/event-stream")


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

    # v0.7.57 — session-start dialog fields.
    name = body.get("name")
    auto_title = bool(body.get("auto_title", True))
    yolo_mode = bool(body.get("yolo_mode", False))
    account_id = body.get("account_id")

    # v0.7.58 — per-project allowed-accounts enforcement.
    # When yolo_mode is False, the dialog must surface an account
    # picker drawn from the project's whitelist. We re-verify here
    # because the dialog is just a UX hint — the canonical gate has
    # to live server-side (a curl bypass on the same endpoint must
    # not bypass the whitelist).
    if not yolo_mode:
        from litestar.exceptions import HTTPException

        from app.db.grd import is_account_allowed_for_project, list_allowed_accounts

        if not account_id:
            allowed = list_allowed_accounts(project_id)
            if not allowed:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Project has no allowed AI accounts configured. "
                        "Add one in project settings, or start the session "
                        "with yolo_mode=true."
                    ),
                )
            raise ClientException(
                detail=(
                    "account_id is required when yolo_mode is false. "
                    "Pick an account from the project's whitelist."
                ),
            )
        if not is_account_allowed_for_project(project_id, account_id):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"account_id={account_id!r} is not whitelisted for this "
                    "project. Add it on the project settings page, or start "
                    "the session with yolo_mode=true."
                ),
            )

    # When yolo is on, inject ``--dangerously-skip-permissions`` into the
    # claude cmd if it isn't already there. (Ralph / team-spawn handlers
    # build their own commands; if they want yolo, they consult
    # ``yolo_mode`` in their start logic.)
    if yolo_mode and cmd and cmd[0] == "claude" and "--dangerously-skip-permissions" not in cmd:
        cmd = [*cmd, "--dangerously-skip-permissions"]

    # v0.7.70 — compile the project's Forge context bundle and apply
    # it to the cmd before the handler spawns the subprocess. Empty
    # bundle (no bindings, no overrides, no attachments) is a no-op
    # so existing sessions stay byte-identical.
    forge_context = body.get("forge_context") or {}
    forge_bundle_dict: dict | None = None
    try:
        from app.services.context_compiler_service import ContextCompilerService
        from app.services.context_renderers import renderer_for

        bundle = ContextCompilerService.compile(
            project_id,
            session_overrides=forge_context.get("session_overrides"),
            attachments=forge_context.get("attachments"),
            project_root=cwd,
        )
        renderer = renderer_for(cmd[0]) if cmd else None
        if renderer is not None and not bundle.is_empty():
            # Renderer mutates argv (e.g. appends --append-system-prompt).
            # The overlay-side of the bundle (hooks/commands/mcp_servers)
            # is materialized later by PSM via
            # ``claude_config_overlay.apply_forge_bundle`` so it can
            # layer on top of the permission-hook overlay PSM creates
            # for non-yolo stream-json sessions.
            cmd, _renderer_env = renderer.apply(
                cmd, dict(body.get("env") or {}), bundle, session_id="pending"
            )
            # Carry the bundle through to PSM for overlay
            # materialization. Skip if the bundle has nothing
            # overlay-relevant to add (keeps the session_config
            # payload tight in the common empty case).
            if bundle.overlay_files or bundle.overlay_symlinks or bundle.mcp_servers:
                forge_bundle_dict = bundle.to_dict()
    except Exception:
        logger.warning(
            "create_session: forge context compile failed; spawning with raw cmd",
            exc_info=True,
        )

    result = handler.start(
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
            # Forwarded so chat-style views can opt into claude's
            # ``--output-format stream-json`` rendering (parsed in
            # ``ProjectSessionManager._reader_thread``). Without this,
            # ``DirectExecutionHandler.start`` saw ``stream_json=False``
            # regardless of the caller's intent and ``claude`` dropped
            # into TUI mode — leaking ANSI/box-drawing into chat
            # bubbles. See v0.7.43.
            "stream_json": bool(body.get("stream_json", False)),
            # ``use_pty`` defaults to True for back-compat with ralph
            # loops and team-spawn (they need a real tty). Chat-style
            # ``claude --print --input-format stream-json`` sessions
            # must pass ``use_pty: false`` because ``--print`` refuses
            # to read from a tty.
            "use_pty": bool(body.get("use_pty", True)),
            "yolo_mode": yolo_mode,
            # v0.7.71 — overlay portion of the compiled Forge bundle
            # (None when there's nothing for PSM to materialize).
            "forge_bundle": forge_bundle_dict,
            # v0.7.74 — goal-loop config; only consumed by the
            # ``goal_loop`` execution-type handler. Other handlers
            # ignore the field.
            "goal_loop_config": body.get("goal_loop_config"),
        }
    )

    # Stamp name / auto_title / yolo_mode onto the row that the handler
    # just inserted. Stored after-the-fact so handlers don't have to
    # know about dialog fields.
    session_id = result.get("session_id")
    if session_id:
        try:
            from app.db.connection import get_connection

            with get_connection() as conn:
                conn.execute(
                    "UPDATE project_sessions "
                    "SET name = ?, auto_title = ?, yolo_mode = ? WHERE id = ?",
                    (
                        name if name and name.strip() else None,
                        1 if auto_title else 0,
                        1 if yolo_mode else 0,
                        session_id,
                    ),
                )
                conn.commit()
        except Exception:
            logger.warning(
                "create_session: failed to persist dialog fields on %s",
                session_id,
                exc_info=True,
            )
    return result


@get("/{project_id:str}/sessions", sync_to_thread=False)
def list_sessions(project_id: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    _ensure_project(project_id)
    from app.db.grd import count_sessions_by_project

    sessions = get_sessions_by_project(project_id, limit=limit, offset=offset)
    return {"sessions": sessions, "total_count": count_sessions_by_project(project_id)}


@get("/{project_id:str}/sessions/{session_id:str}/output", sync_to_thread=False)
def session_output(project_id: str, session_id: str, last_n: int = 100) -> dict[str, Any]:
    del project_id
    last_n = max(1, min(last_n, 10000))
    lines = ProjectSessionManager.get_output(session_id, last_n=last_n)
    return {"lines": lines, "count": len(lines)}


@get("/{project_id:str}/allowed-accounts", sync_to_thread=False)
def list_allowed_accounts_endpoint(project_id: str) -> dict[str, Any]:
    """v0.7.58 — list the AI backend accounts whitelisted for this
    project. Sessions started with ``yolo_mode=false`` must pick an
    account from this list."""
    _ensure_project(project_id)
    from app.db.grd import list_allowed_accounts

    return {"allowed_accounts": list_allowed_accounts(project_id)}


@post("/{project_id:str}/allowed-accounts", status_code=201, sync_to_thread=False)
def add_allowed_account_endpoint(project_id: str, data: dict) -> dict[str, Any]:
    _ensure_project(project_id)
    body = data or {}
    account_id = body.get("account_id")
    if not account_id or not isinstance(account_id, str):
        raise ClientException(detail="account_id (string) is required")
    from app.db.grd import add_allowed_account

    inserted = add_allowed_account(project_id, account_id)
    return {
        "project_id": project_id,
        "account_id": account_id,
        "inserted": inserted,
    }


@delete(
    "/{project_id:str}/allowed-accounts/{account_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def remove_allowed_account_endpoint(project_id: str, account_id: str) -> dict[str, Any]:
    _ensure_project(project_id)
    from app.db.grd import remove_allowed_account

    if not remove_allowed_account(project_id, account_id):
        raise NotFoundException(detail="Account not in whitelist")
    return {"project_id": project_id, "account_id": account_id, "removed": True}


@post(
    "/{project_id:str}/sessions/{session_id:str}/answer-question",
    sync_to_thread=False,
)
def session_answer_question(project_id: str, session_id: str, data: dict) -> dict[str, Any]:
    """v0.7.63 — receive a user's selection for an ``AskUserQuestion``
    tool_use, wrap as a ``tool_result`` envelope, write to claude's
    stdin. Claude continues the conversation with the answer.

    Body shape:
        {
          "tool_use_id": "toolu_xxx",
          "answers": { "<question text>": "<selected label>" | ["..."] }
        }
    """
    del project_id
    body = data or {}
    # ``tool_use_id`` is optional now (v0.7.72) — when PSM
    # synthesizes an ``ask_user_question`` event from a text-block
    # AskUserQuestion (claude rendered the call inline instead of
    # emitting a real ``tool_use``), there's no id to reference.
    # We still accept the answer and forward it as a plain user
    # message so claude's conversation can continue.
    tool_use_id = body.get("tool_use_id") or ""
    answers = body.get("answers")
    if answers is None:
        raise ClientException(detail="answers is required")

    # Persist the user side so the chat panel re-renders the chosen
    # option as a user bubble on next hydration. Render it as a
    # short summary line — the full structured payload goes into
    # claude's stdin separately.
    try:
        from app.db.grd import append_session_message

        summary_lines: list[str] = []
        for q, a in answers.items() if isinstance(answers, dict) else []:
            shown = a if isinstance(a, str) else ", ".join(a or [])
            summary_lines.append(f"**{q}** → {shown}")
        if summary_lines:
            append_session_message(session_id, "user", "\n".join(summary_lines))
    except Exception:
        logger.warning(
            "answer-question: failed to persist user answer for %s",
            session_id,
            exc_info=True,
        )

    if not ProjectSessionManager.is_stream_json(session_id):
        raise ClientException(detail="Session is not in stream-json mode; cannot answer.")

    import json as _json

    if tool_use_id:
        # Real tool_use path — wrap as the tool_result claude is
        # blocked waiting for.
        content_block: dict = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": _json.dumps({"answers": answers}, ensure_ascii=False),
        }
    else:
        # Synthetic path — claude rendered the AskUserQuestion as
        # text and isn't waiting on a tool_result; ship the answer
        # as a normal user text message so the next turn picks it up.
        if isinstance(answers, dict) and answers:
            lines = []
            for q, a in answers.items():
                shown = a if isinstance(a, str) else ", ".join(a or [])
                lines.append(f"{q} -> {shown}")
            text = "\n".join(lines)
        else:
            text = _json.dumps({"answers": answers}, ensure_ascii=False)
        content_block = {"type": "text", "text": text}

    envelope = {
        "type": "user",
        "session_id": "",
        "message": {
            "role": "user",
            "content": [content_block],
        },
        "parent_tool_use_id": None,
    }
    payload = _json.dumps(envelope, ensure_ascii=False)
    if not ProjectSessionManager.send_input(session_id, payload):
        raise NotFoundException(detail="Session not found or not active")
    return {"message": "Answer sent", "session_id": session_id}


@post(
    "/{project_id:str}/sessions/{session_id:str}/answer-plan",
    sync_to_thread=False,
)
def session_answer_plan(project_id: str, session_id: str, data: dict) -> dict[str, Any]:
    """v0.7.65 — accept or decline claude's ``ExitPlanMode`` proposal.

    Body shape::

        {"tool_use_id": "toolu_xxx", "approved": true | false}

    Claude's ``ExitPlanMode`` tool semantics: tool_result with
    ``"User approved the plan. Proceed with execution."`` signals
    accept; ``"User wants to keep planning."`` signals decline. We
    keep that contract so claude's downstream logic stays unchanged.
    """
    del project_id
    body = data or {}
    tool_use_id = body.get("tool_use_id")
    approved = body.get("approved")
    if not tool_use_id or approved is None:
        raise ClientException(detail="tool_use_id and approved are required")

    decision_text = (
        "User approved the plan. Proceed with execution."
        if approved
        else "User wants to keep planning. Do not execute yet."
    )

    # Persist the user's decision so the chat panel rehydrates it
    # as a user bubble on next session click.
    try:
        from app.db.grd import append_session_message

        append_session_message(
            session_id,
            "user",
            f"**Plan decision** → {'Approved' if approved else 'Keep planning'}",
        )
    except Exception:
        logger.warning(
            "answer-plan: failed to persist user decision for %s",
            session_id,
            exc_info=True,
        )

    if not ProjectSessionManager.is_stream_json(session_id):
        raise ClientException(detail="Session is not in stream-json mode; cannot answer.")

    import json as _json

    envelope = {
        "type": "user",
        "session_id": "",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": decision_text,
                }
            ],
        },
        "parent_tool_use_id": None,
    }
    payload = _json.dumps(envelope, ensure_ascii=False)
    if not ProjectSessionManager.send_input(session_id, payload):
        raise NotFoundException(detail="Session not found or not active")
    return {"message": "Plan decision sent", "session_id": session_id}


@post(
    "/{project_id:str}/sessions/{session_id:str}/permission-request",
    sync_to_thread=True,
)
def session_permission_request(project_id: str, session_id: str, data: dict) -> dict[str, Any]:
    """v0.7.69 — Agented permission hook → backend → web panel.

    The hook script POSTs here when claude is about to use a tool.
    We register a pending request, push a ``permission_request`` SSE
    event to whatever frontend is subscribed to this session, then
    block until the user clicks Approve / Deny in the web chat panel
    (or 5 min default timeout, after which we return no-decision and
    the hook falls back to claude's default permission flow).

    Body shape:

        {
          "tool_name": "Bash",
          "tool_input": {"command": "ls /tmp"},
          "cwd": "/path/to/project",
          "claude_session_id": "uuid-from-claude"
        }

    Response:

        {"decision": "allow" | "deny"}  (200)

    or for missing/invalid body:

        400 with ClientException
    """
    del project_id
    body = data or {}
    tool_name = body.get("tool_name") or ""
    tool_input = body.get("tool_input") or {}
    if not tool_name or not isinstance(tool_input, dict):
        raise ClientException(detail="tool_name and tool_input are required")

    from app.services.permission_prompt_service import PermissionPromptRegistry

    req = PermissionPromptRegistry.register(session_id, tool_name, tool_input)

    # Broadcast to the panel so the user sees the prompt. Side-channel
    # event type matches the contract the frontend's
    # ``onPermissionRequest`` callback subscribes to.
    ProjectSessionManager._broadcast(
        session_id,
        "permission_request",
        {
            "request_id": req.request_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "cwd": body.get("cwd"),
        },
    )

    decision = PermissionPromptRegistry.wait_for_decision(req.request_id)
    if decision in ("allow", "deny"):
        return {"decision": decision}
    # Timeout or cancellation → return 408 so the hook falls back to
    # claude's normal permission flow (the script emits ``ask``).
    raise HTTPException(
        status_code=408,
        detail="No user decision within timeout",
    )


@post(
    "/{project_id:str}/sessions/{session_id:str}/permission-decision",
    sync_to_thread=False,
)
def session_permission_decision(project_id: str, session_id: str, data: dict) -> dict[str, Any]:
    """v0.7.69 — frontend POSTs the user's Approve / Deny click here.

    Body: ``{"request_id": "perm-…", "decision": "allow"|"deny"}``
    """
    del project_id, session_id
    body = data or {}
    rid = body.get("request_id")
    decision = body.get("decision")
    if not rid or decision not in ("allow", "deny"):
        raise ClientException(detail="request_id and decision (allow|deny) are required")

    from app.services.permission_prompt_service import PermissionPromptRegistry

    if not PermissionPromptRegistry.resolve(rid, decision):
        raise NotFoundException(detail="Request not found (timed out?)")
    return {"request_id": rid, "decision": decision, "resolved": True}


@get("/{project_id:str}/sessions/{session_id:str}/messages", sync_to_thread=False)
def session_messages(project_id: str, session_id: str) -> dict[str, Any]:
    """Return persisted chat messages for a session.

    Sourced from ``project_sessions.log_json``, which the input route
    and reader thread both append to as the chat progresses. Survives
    subprocess exit and gunicorn restart, unlike the in-memory ring
    buffer that ``/output`` reads from.
    """
    del project_id
    from app.db.grd import get_session_messages

    messages = get_session_messages(session_id)
    return {"messages": messages, "count": len(messages)}


@post("/{project_id:str}/sessions/{session_id:str}/stop", sync_to_thread=False)
def stop_session(project_id: str, session_id: str) -> dict[str, Any]:
    del project_id
    # Signal any goal-loop/ralph runner FIRST so its loop thread exits and stops
    # the live child it owns. Under context_policy=reset the runner re-points to a
    # fresh child whose id this route never learns — without stop_runner (keyed by
    # the stable registry id) the live child would keep iterating + spending after
    # the route only kills the original (already-dead) process. No-op for
    # non-runner sessions.
    from app.services.goal_loop_runner import stop_runner

    stop_runner(session_id)
    if not ProjectSessionManager.stop_session(session_id):
        raise NotFoundException(detail="Session not found or already stopped")
    return {"message": "Session stopped", "session_id": session_id}


@post("/{project_id:str}/sessions/{session_id:str}/pause", sync_to_thread=False)
def pause_session(project_id: str, session_id: str) -> dict[str, Any]:
    del project_id
    if not ProjectSessionManager.pause_session(session_id):
        raise NotFoundException(detail="Session not found")
    from app.services.goal_loop_runner import pause_runner

    pause_runner(session_id)
    return {"message": "Session paused", "session_id": session_id}


@post("/{project_id:str}/sessions/{session_id:str}/resume", sync_to_thread=False)
def resume_session(project_id: str, session_id: str) -> dict[str, Any]:
    del project_id
    if not ProjectSessionManager.resume_session(session_id):
        raise NotFoundException(detail="Session not found")
    from app.services.goal_loop_runner import resume_runner

    resume_runner(session_id)
    return {"message": "Session resumed", "session_id": session_id}


@post("/{project_id:str}/sessions/{session_id:str}/loop/intervene", sync_to_thread=False)
def loop_intervene(project_id: str, session_id: str, data: dict) -> dict[str, Any]:
    _ensure_project(project_id)
    message = (data or {}).get("message")
    if not message:
        raise ClientException(detail="message is required")
    from app.services.goal_loop_runner import intervene_runner

    return {"ok": intervene_runner(session_id, str(message))}


@post("/{project_id:str}/sessions/{session_id:str}/loop/gate-decision", sync_to_thread=False)
def loop_gate_decision(project_id: str, session_id: str, data: dict) -> dict[str, Any]:
    _ensure_project(project_id)
    body = data or {}
    decision = body.get("decision")
    if decision not in ("continue", "modify", "abort"):
        raise ClientException(detail="decision must be continue|modify|abort")
    from app.services.goal_loop_runner import submit_gate_decision

    return {"ok": submit_gate_decision(session_id, decision, body.get("message"))}


@post("/{project_id:str}/sessions/{session_id:str}/input", sync_to_thread=False)
def session_input(project_id: str, session_id: str, data: dict) -> dict[str, Any]:
    body = data or {}
    text = body.get("text")
    if text is None:
        raise ClientException(detail="text is required")

    # v0.7.70 — per-prompt attachments: if the operator attached
    # files/snippets/URLs/entity refs in the SessionContextTray, the
    # frontend forwards them as ``attachments``. Re-compile a
    # bundle (cheap — empty bindings + only this prompt's
    # attachments) and prepend the rendered text. The result is a
    # single user message containing the Operator Context block
    # above the operator's question.
    attachments = body.get("attachments") or []
    if attachments:
        try:
            from app.services.context_compiler_service import ContextCompilerService
            from app.services.project_workspace_service import ProjectWorkspaceService

            project_root = None
            try:
                project_root = ProjectWorkspaceService.resolve_working_directory(project_id)
            except Exception:
                project_root = None
            bundle = ContextCompilerService.compile(
                project_id,
                attachments=attachments,
                project_root=project_root,
            )
            if bundle.prompt_prepend:
                text = f"{bundle.prompt_prepend}\n\n{text}"
        except Exception:
            logger.warning(
                "session_input: failed to render attachments for %s",
                session_id,
                exc_info=True,
            )
    del project_id

    # Persist the user's message into ``project_sessions.log_json``
    # before forwarding to claude — so even if the subprocess crashes
    # or gunicorn restarts, clicking this session in the sidebar later
    # still surfaces what the user said.
    try:
        from app.db.grd import append_session_message

        append_session_message(session_id, "user", text)
    except Exception:
        logger.warning(
            "session_input: failed to persist user message for %s", session_id, exc_info=True
        )

    if ProjectSessionManager.is_stream_json(session_id):
        # claude was started with ``--input-format stream-json`` — it
        # expects one JSON event per line on stdin, not raw text. The
        # envelope shape is documented in the Claude Agent SDK V1 docs
        # (https://code.claude.com/docs/en/agent-sdk/typescript-v2-preview):
        #
        #   yield {
        #     type: "user",
        #     session_id: "",
        #     message: { role: "user", content: [{type:"text", text:"..."}]},
        #     parent_tool_use_id: null,
        #   };
        #
        # The ``session_id`` and ``parent_tool_use_id`` fields are
        # required — without them claude silently fails to parse the
        # user event and the chat appears to hang (no assistant
        # response). v0.7.46 added them after the v0.7.45 chat view
        # sat at "AI is thinking..." with no claude output.
        # Unicode user content (Korean, emoji, …) is preserved by
        # ``ensure_ascii=False``.
        import json as _json

        envelope = {
            "type": "user",
            "session_id": "",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": text}],
            },
            "parent_tool_use_id": None,
        }
        payload = _json.dumps(envelope, ensure_ascii=False)
        if not ProjectSessionManager.send_input(session_id, payload):
            raise NotFoundException(detail="Session not found or not active")
        return {"message": "Input sent", "session_id": session_id}

    # Default (interactive PTY REPL): strip non-printable bytes so a
    # rogue control char can't reprogram the user's terminal.
    sanitized = "".join(ch for ch in text if ch in {"\t", "\n", "\r"} or (32 <= ord(ch) < 127))
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


@get(
    "/{project_id:str}/sessions/{session_id:str}/goal-iterations",
    sync_to_thread=False,
)
def list_session_goal_iterations(project_id: str, session_id: str) -> dict[str, Any]:
    """v0.7.74 — iteration audit trail for a goal_loop session.

    Returns every iteration row with its verdict + reason + judging
    cost. The operator inspects this when figuring out "why did it
    stop on turn 7?" The list is empty (not 404) for non-goal_loop
    sessions so the frontend can render the same component
    unconditionally; the panel just shows nothing when there are
    no rows.
    """
    del project_id
    from app.db import get_goal_loop_config, list_goal_loop_iterations

    iterations = list_goal_loop_iterations(session_id)
    config = get_goal_loop_config(session_id)
    return {
        "session_id": session_id,
        "config": config,
        "iterations": iterations,
    }


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
        raise NotFoundException(detail=f"No handler for execution_type: {execution_type}")
    result = handler.monitor(session_id)
    result["session_id"] = session_id
    result["execution_type"] = execution_type
    return result


# ---------------------------------------------------------------------------
# v0.7.85 — Ouroboros DB-mirror read endpoints (Layer B)
# ---------------------------------------------------------------------------


@get("/{project_id:str}/grd/phases/{phase_id:str}/reflections", sync_to_thread=False)
def list_phase_reflections(project_id: str, phase_id: str) -> dict[str, Any]:
    """v0.7.85 — Reflections (hypothesis → verdict) for a phase, newest
    first. Backed by the ``phase_reflections`` table which the sync
    layer populates from per-phase VERIFICATION.md ``## Reflection``
    sections. Pure DB read — no GRD CLI hop.
    """
    _ensure_project(project_id)
    from app.database import get_phase_reflections

    return {"reflections": get_phase_reflections(phase_id)}


@get("/{project_id:str}/grd/verdict-counts", sync_to_thread=False)
def grd_verdict_counts(project_id: str) -> dict[str, Any]:
    """v0.7.85 — Aggregate ``{verdict: count}`` across the project's
    phases. Backs the project overview card without round-tripping
    through ``gd think``.
    """
    _ensure_project(project_id)
    from app.database import count_reflections_by_verdict

    return {"verdicts": count_reflections_by_verdict(project_id)}


@get("/{project_id:str}/grd/dead-ends", sync_to_thread=False)
def list_grd_dead_ends(project_id: str, limit: int = 200) -> dict[str, Any]:
    """v0.7.85 — read DEAD-ENDS.md mirror from the DB. Faster than the
    CLI shell-out and unaffected by missing ``gd.js``.
    """
    _ensure_project(project_id)
    from app.database import list_dead_ends

    return {"dead_ends": list_dead_ends(project_id, limit=limit)}


@get("/{project_id:str}/grd/genome/snapshots", sync_to_thread=False)
def list_grd_genome_snapshots(project_id: str, limit: int = 50) -> dict[str, Any]:
    """v0.7.85 — historical GENOME.md snapshots for the project,
    newest first. The latest snapshot's ``content`` is the full
    markdown body so the frontend can render a diff against
    ``content`` of the previous entry.
    """
    _ensure_project(project_id)
    from app.database import list_genome_snapshots

    return {"snapshots": list_genome_snapshots(project_id, limit=limit)}


@get("/{project_id:str}/grd/genome/latest", sync_to_thread=False)
def latest_grd_genome_snapshot(project_id: str) -> dict[str, Any]:
    """v0.7.85 — most-recent GENOME.md snapshot only. Convenience
    endpoint so the planning header doesn't have to fetch + slice a
    full history list on every page load.
    """
    _ensure_project(project_id)
    from app.database import get_latest_genome_snapshot

    return get_latest_genome_snapshot(project_id) or {"exists": False}


# ---------------------------------------------------------------------------
# v0.7.88 — gd evolve session runs
# ---------------------------------------------------------------------------


@post("/{project_id:str}/grd/evolve/start", sync_to_thread=False)
def start_grd_evolve(project_id: str, data: dict | None) -> dict[str, Any]:
    """DEPRECATED (GRD 0.4.3): ``gd evolve`` no longer runs — it was superseded
    by the life-harness (``gd harness round``). Starting an evolve session would
    no-op, so this endpoint returns a pointer to the harness-round surface
    instead. The read-only ``/grd/evolve/runs`` endpoints stay for history.
    """
    del data
    _ensure_project(project_id)
    return {
        "deprecated": True,
        "reason": "gd evolve was deprecated in GRD 0.4.3 (superseded by the life-harness).",
        "use": f"/api/projects/{project_id}/grd/harness/round",
    }


# ---------------------------------------------------------------------------
# GRD 0.4.x life-harness rounds (gd harness round) — supersedes gd evolve
# ---------------------------------------------------------------------------


@post("/{project_id:str}/grd/harness/round", sync_to_thread=False)
def grd_harness_round(project_id: str, data: dict | None) -> dict[str, Any]:
    """Trigger a ``gd harness round`` in the background. The result is mirrored
    into ``grd_harness_rounds`` on completion — poll the rounds list."""
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    body = data or {}
    from app.services.grd_harness_round_runner import run_round

    started = run_round(
        project_id,
        cwd,
        auto=bool(body.get("auto")),
        dry_run=bool(body.get("dry_run")),
        full_eval=bool(body.get("full_eval")),
    )
    if not started:
        raise ClientException(
            detail="GRD gd binary not detected — install @jokerized/getresearchdone"
        )
    return {"status": "running"}


@get("/{project_id:str}/grd/harness/rounds", sync_to_thread=False)
def grd_list_harness_rounds(project_id: str, limit: int = 50) -> dict[str, Any]:
    _ensure_project(project_id)
    from app.db import list_harness_rounds

    return {"rounds": list_harness_rounds(project_id, limit=limit)}


@get("/{project_id:str}/grd/harness/rounds/{round_id:str}", sync_to_thread=False)
def grd_get_harness_round(project_id: str, round_id: str) -> dict[str, Any]:
    _ensure_project(project_id)
    from app.db import get_harness_round

    row = get_harness_round(project_id, round_id)
    if not row:
        raise NotFoundException(detail="Harness round not found")
    return row


@post("/{project_id:str}/grd/harness/rounds/{round_id:str}/revert", sync_to_thread=False)
def grd_revert_harness_round(project_id: str, round_id: str) -> dict[str, Any]:
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    from app.services.grd_harness_round_runner import revert_round

    result = revert_round(cwd, round_id)
    if not result["success"]:
        raise ClientException(detail=result.get("error") or "revert failed")
    return result


@get("/{project_id:str}/grd/harness/status", sync_to_thread=False)
def grd_harness_round_status(project_id: str) -> dict[str, Any]:
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    from app.services.grd_harness_round_runner import harness_status

    return harness_status(cwd)


@post("/{project_id:str}/grd/plan/{phase:str}/select", sync_to_thread=False)
def grd_select_plan_candidate(project_id: str, phase: str, data: dict | None) -> dict[str, Any]:
    """Run ``gd select-candidate <phase>`` (deterministic scorer). ``dry_run``
    previews the ranking without promoting; a real run promotes the winner to
    ``PLAN.md`` and mirrors the selection. Body:
    ``{dry_run?, force?, run_verification_commands?}``."""
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    body = data or {}
    from app.services.grd_plan_selection_runner import select_candidate

    result = select_candidate(
        project_id,
        cwd,
        phase,
        dry_run=bool(body.get("dry_run")),
        force=bool(body.get("force")),
        run_verification_commands=bool(body.get("run_verification_commands")),
    )
    if not result["success"]:
        raise ClientException(detail=result.get("error") or "select-candidate failed")
    return result


@get("/{project_id:str}/grd/plan/{phase:str}/selection", sync_to_thread=False)
def grd_get_plan_selection(project_id: str, phase: str) -> dict[str, Any]:
    """The latest mirrored ``gd select-candidate`` result for this phase."""
    _ensure_project(project_id)
    from app.db import get_plan_selection

    row = get_plan_selection(project_id, phase)
    if not row:
        raise NotFoundException(detail="No plan selection recorded for this phase")
    return row


@post("/{project_id:str}/grd/plan/tournament", sync_to_thread=False)
def grd_plan_tournament(project_id: str, data: dict) -> dict[str, Any]:
    """Run ``gd plan-tournament --phase <N> --candidates <paths…>`` — ad-hoc
    ranked scoring over explicit candidate paths (no promotion). Body:
    ``{phase, candidates: [paths]}``."""
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    body = data or {}
    phase = body.get("phase")
    candidates = body.get("candidates")
    if not phase or not isinstance(candidates, list) or not candidates:
        raise ClientException(detail="phase and a non-empty candidates list are required")
    from app.services.grd_plan_selection_runner import plan_tournament

    result = plan_tournament(cwd, str(phase), [str(c) for c in candidates])
    if not result["success"]:
        raise ClientException(detail=result.get("error") or "plan-tournament failed")
    return result


@get("/{project_id:str}/grd/evolve/runs", sync_to_thread=False)
def list_grd_evolve_runs(
    project_id: str, status: Optional[str] = None, limit: int = 20
) -> dict[str, Any]:
    """v0.7.88 — recent evolve runs for the project, newest first.
    ``status`` filter (``active`` / ``completed`` / ``failed`` /
    ``stopped``) is optional.
    """
    _ensure_project(project_id)
    from app.database import list_evolve_runs_for_project

    runs = list_evolve_runs_for_project(project_id, status=status, limit=limit)
    return {"runs": runs}


@get("/{project_id:str}/grd/evolve/runs/{run_id:str}", sync_to_thread=False)
def get_grd_evolve_run(project_id: str, run_id: str) -> dict[str, Any]:
    """v0.7.88 — single evolve-run detail including the parsed
    ``last_state`` (EVOLVE-STATE.json snapshot) for UI rendering.
    """
    _ensure_project(project_id)
    from app.database import get_evolve_run

    run = get_evolve_run(run_id)
    if not run or run["project_id"] != project_id:
        raise NotFoundException(detail="Evolve run not found")
    return run


@post("/{project_id:str}/grd/evolve/runs/{run_id:str}/stop", sync_to_thread=False)
def stop_grd_evolve_run(project_id: str, run_id: str) -> dict[str, Any]:
    """v0.7.88 — terminate an active evolve run. Idempotent; safe
    to call on already-terminal runs (returns the current status
    without re-stopping).
    """
    _ensure_project(project_id)
    from app.database import finalize_evolve_run, get_evolve_run
    from app.services.execution_type_handler import get_handler

    run = get_evolve_run(run_id)
    if not run or run["project_id"] != project_id:
        raise NotFoundException(detail="Evolve run not found")
    if run["status"] != "active":
        return {"status": run["status"], "already_terminal": True}
    handler = get_handler("grd_evolve")
    if handler:
        handler.stop(run["session_id"])
    # Mark terminal regardless of session-stop outcome so the UI
    # doesn't get stuck on "stopping…" if PSM raced ahead.
    finalize_evolve_run(session_id=run["session_id"], status="stopped")
    return {"status": "stopped"}


@post("/{project_id:str}/sessions/{session_id:str}/resume-loop", sync_to_thread=True)
def resume_goal_loop_route(project_id: str, session_id: str) -> dict[str, Any]:
    """Phase 4, Unit C — resume a failed goal-loop session by spawning a fresh
    session seeded with persisted iteration knowledge.

    404 when session not found; 409 when not eligible / already resumed.
    """
    del project_id
    from app.services.goal_loop_runner import resume_goal_loop

    result = resume_goal_loop(session_id)
    if result.get("error") == "not_found":
        raise NotFoundException(detail=f"Session {session_id} not found")
    if "error" in result:
        raise HTTPException(status_code=409, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Research (v0.8.0 — REQ-14, autoresearch loop)
#
# The long ``gd research`` loop runs as a streamed ``grd_research`` PSM
# session via ``GrdResearchSessionHandler``; the operator watches it through
# the generic ``/sessions/{session_id}/output`` SSE route (no research-
# specific bridge). The thread browser/status endpoints read the loop's
# on-disk ``THREAD.md`` / ``HYPOTHESES.md`` / ``FINDING.md`` outputs.
# ---------------------------------------------------------------------------


@post("/{project_id:str}/research/start", status_code=201, sync_to_thread=False)
def research_start(project_id: str, data: dict) -> dict[str, Any]:
    """Start a fresh ``gd research`` loop as a streamed ``grd_research``
    session. Returns ``{"session_id": ...}``; stream it via the generic
    ``/sessions/{session_id}/output`` SSE route.
    """
    _ensure_project(project_id)
    body = data or {}
    question = (body.get("question") or "").strip()
    if not question:
        raise ClientException(detail="question is required")

    handler = get_handler("grd_research")
    config: dict[str, Any] = {"project_id": project_id, "question": question}
    if body.get("max_iterations") is not None:
        config["max_iterations"] = body["max_iterations"]
    if body.get("no_gates"):
        config["no_gates"] = True

    result = handler.start(config)
    if "error" in result:
        raise ClientException(detail=result["error"])
    return {"session_id": result["session_id"]}


@post(
    "/{project_id:str}/research/{thread_id:str}/resume",
    status_code=201,
    sync_to_thread=False,
)
def research_resume(project_id: str, thread_id: str, data: dict) -> dict[str, Any]:
    """Resume an existing research thread by spawning a fresh
    ``grd_research`` session pinned to ``/grd:research resume <thread_id>``.
    Returns ``{"session_id": ...}``.
    """
    _ensure_project(project_id)
    body = data or {}

    handler = get_handler("grd_research")
    config: dict[str, Any] = {"project_id": project_id, "thread_id": thread_id}
    if body.get("max_iterations") is not None:
        config["max_iterations"] = body["max_iterations"]
    if body.get("no_gates"):
        config["no_gates"] = True

    result = handler.start(config)
    if "error" in result:
        raise ClientException(detail=result["error"])
    return {"session_id": result["session_id"]}


@get("/{project_id:str}/research/threads", sync_to_thread=False)
def research_list_threads(project_id: str) -> dict[str, Any]:
    """Portfolio/browser — the project's research threads parsed from
    on-disk ``THREAD.md`` frontmatter. Returns ``{"threads": []}`` when no
    research has run yet (the threads dir does not exist until then).
    """
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    return {"threads": GrdCliService.list_threads(cwd)}


@get("/{project_id:str}/research/threads/{thread_id:str}", sync_to_thread=False)
def research_read_thread(project_id: str, thread_id: str) -> dict[str, Any]:
    """None-safe bundle of one thread's ``THREAD.md`` + ``HYPOTHESES.md`` +
    ``FINDING.md`` (each ``None`` when its file is absent).
    """
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    return GrdCliService.read_thread(cwd, thread_id)


@get("/{project_id:str}/research/status", sync_to_thread=False)
def research_status_route(project_id: str, thread_id: Optional[str] = None) -> dict[str, Any]:
    """Passthrough to ``gd research status [thread_id]`` (JSON snapshot of
    the active/most-recent loop).
    """
    _ensure_project(project_id)
    cwd = _project_cwd(project_id)
    return GrdCliService.research_status(cwd, thread_id)


grd_router = Router(
    path="/api/projects",
    route_handlers=[
        sync_status,
        trigger_sync,
        # v0.7.84 — Ouroboros surface (GRD v0.3.24)
        grd_health,
        grd_think,
        grd_add_dead_end,
        grd_promote_dead_ends,
        grd_genome,
        grd_genome_snapshot,
        # GRD 0.4.1 pattern mining → GENOME-SUGGESTIONS → promote
        grd_mine_patterns,
        grd_get_genome_suggestions,
        grd_promote_suggestion,
        grd_verify_mechanical,
        # v0.7.85 — Ouroboros DB-mirror read endpoints
        list_phase_reflections,
        grd_verdict_counts,
        list_grd_dead_ends,
        list_grd_genome_snapshots,
        latest_grd_genome_snapshot,
        # v0.7.88 — gd evolve session runs (start deprecated; runs read-only)
        start_grd_evolve,
        list_grd_evolve_runs,
        get_grd_evolve_run,
        stop_grd_evolve_run,
        # GRD 0.4.x life-harness rounds (supersedes gd evolve)
        grd_harness_round,
        grd_list_harness_rounds,
        grd_get_harness_round,
        grd_revert_harness_round,
        grd_harness_round_status,
        # GRD 0.4.5 multi-candidate plan selection (gd select-candidate)
        grd_select_plan_candidate,
        grd_get_plan_selection,
        grd_plan_tournament,
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
        # v0.8.0 — one-click team harness setup (REQ-19 / SC1)
        trigger_harness_setup,
        harness_setup_status,
        harness_setup_stream,
        create_session,
        list_sessions,
        session_output,
        session_messages,
        session_answer_question,
        session_answer_plan,
        resume_goal_loop_route,
        session_permission_request,
        session_permission_decision,
        list_allowed_accounts_endpoint,
        add_allowed_account_endpoint,
        remove_allowed_account_endpoint,
        stop_session,
        pause_session,
        resume_session,
        loop_intervene,
        loop_gate_decision,
        session_input,
        create_ralph_session,
        create_team_session,
        monitor_session,
        list_session_goal_iterations,
        # v0.8.0 — REQ-14 autoresearch loop
        research_start,
        research_resume,
        research_list_threads,
        research_read_thread,
        research_status_route,
    ],
)
