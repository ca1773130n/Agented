"""Resolve + open the team-leader super-agent chat session for a project.

Layered on top of the existing super-agent chat surface:

  - This endpoint takes a ``project_id`` and returns the ``{super_agent_id,
    session_id}`` pair the operator should target for chat.
  - The actual chat I/O uses the already-shipped endpoints:
      POST /admin/super-agents/{sa_id}/sessions/{sid}/chat          (send)
      GET  /admin/super-agents/{sa_id}/sessions/{sid}/chat/stream   (SSE)
  - For Tesserae-enabled projects, the team leader's runtime context
    already includes the Tesserae MCP server (auto-bound by
    ``tesserae_integration.set_tesserae_root``) — so ``tesserae_ask``
    + the rest of the surface are available without any extra wiring
    here. This endpoint just surfaces a boolean so the operator UI can
    show "grounded by Tesserae" affordance.
"""

from __future__ import annotations

from typing import Any

from litestar import Router, post
from litestar.exceptions import NotFoundException, ClientException

from app.db.connection import get_connection
from app.db.projects import get_project
from app.db.super_agents import get_super_agent
from app.services.instance_service import InstanceService
from app.services.super_agent_session_service import SuperAgentSessionService


@post(
    "/projects/{project_id:str}/team-leader/chat/session",
    sync_to_thread=True,
)
def open_team_leader_chat(project_id: str) -> dict[str, Any]:
    """Resolve the team-leader super-agent for a project + ensure a
    chat session exists. Returns the IDs the frontend uses to drive
    the existing SA chat endpoints.

    Returns:
        ``{super_agent_id, session_id, leader_template_id, leader_name,
        tesserae_enabled}``

    Errors:
        - 404 if the project doesn't exist
        - 400 if the project has no ``manager_super_agent_id`` set
    """
    project = get_project(project_id)
    if not project:
        raise NotFoundException(detail=f"project not found: {project_id}")

    manager_sa_id = project.get("manager_super_agent_id")
    if not manager_sa_id:
        raise ClientException(
            detail=(
                "No team leader configured for this project. Set "
                "projects.manager_super_agent_id to a super-agent id."
            ),
        )

    # Get or create the per-project SA instance. Returns
    # ``{id, template_sa_id, worktree_path, session_id}``. The
    # instance's id (``psa-XXX``) is what the frontend uses to address
    # chat — _resolve_chat_session handles the psa-* prefix.
    instance = InstanceService.ensure_manager_instance(project_id)
    if not instance:
        raise NotFoundException(
            detail="Failed to materialize manager super-agent instance",
        )
    instance_id = instance["id"]

    # Get-or-create a leader session. ``get_or_create_session`` keys
    # on the TEMPLATE super-agent id (the row that exists in
    # super_agents); the instance_id flows separately when the
    # session is first created so chat handlers can resolve the
    # project-scoped runtime (worktree, MCP bindings, etc.).
    #
    # If no active/paused session exists for this template SA we
    # ``create_session`` directly with the leader session_type so the
    # downstream chat handler picks the right context bundle.
    session_id = _ensure_leader_session(
        template_sa_id=manager_sa_id,
        instance_id=instance_id,
        project_id=project_id,
    )

    # Pull the human-readable leader name from the template SA.
    template = get_super_agent(manager_sa_id) or {}
    leader_name = template.get("name") or manager_sa_id

    # Surface whether the project has Tesserae enabled (operator UI
    # uses this to badge the chat panel as "grounded by Tesserae").
    tesserae_enabled = False
    with get_connection() as conn:
        row = conn.execute(
            "SELECT tesserae_project_root FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    if row and row["tesserae_project_root"]:
        tesserae_enabled = True

    return {
        "project_id": project_id,
        "super_agent_id": instance_id,
        "session_id": session_id,
        "leader_template_id": manager_sa_id,
        "leader_name": leader_name,
        "tesserae_enabled": tesserae_enabled,
    }


def _ensure_leader_session(
    *, template_sa_id: str, instance_id: str, project_id: str,
) -> str:
    """Return an existing leader session for the (template_sa, project)
    pair or create one.

    Reuse rule: an active/paused session whose ``super_agent_id`` is
    the template SA AND whose ``instance_id`` matches the project
    instance counts as the leader session. Otherwise spin up a new
    one with ``session_type='leader'``.
    """
    from app.services.super_agent_session_service import (
        SessionLimitError,
        SuperAgentSessionService,
    )

    # Scan the in-memory active sessions for a matching leader session.
    with SuperAgentSessionService._lock:
        for s in SuperAgentSessionService._active_sessions.values():
            if (
                s.get("super_agent_id") == template_sa_id
                and s.get("instance_id") == instance_id
                and s.get("status") in ("active", "paused")
            ):
                sid = s["session_id"]
                if s["status"] == "paused":
                    # Release lock before resume_session re-acquires it.
                    break
                return sid
        else:
            sid = None

    if sid is not None:
        # Was paused — resume + return.
        SuperAgentSessionService.resume_session(sid)
        return sid

    session_id, error = SuperAgentSessionService.create_session(
        template_sa_id,
        instance_id=instance_id,
        project_id=project_id,
        session_type="leader",
    )
    if session_id is None:
        raise SessionLimitError(error or "Failed to create leader session")
    return session_id


team_leader_chat_router = Router(
    path="/admin",
    route_handlers=[open_team_leader_chat],
)
