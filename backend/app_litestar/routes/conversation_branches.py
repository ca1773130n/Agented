"""Session fork route (Phase 25, 25-03).

Fork a conversation/session onto a SEPARATE independent run:
``POST /api/projects/{pid}/sessions/{sid}/fork`` → ``{branch_id, session_id}``.
Owner-gated like other ``/api`` routes (X-API-Key path). Composes the existing
``ConversationBranchService.fork_to_run`` primitive (create_branch + a fresh
seeded ``create_session``) — the parent conversation stays immutable and the
parent's running session is untouched.
"""

from __future__ import annotations

from typing import Any

from litestar import Router, post
from litestar.exceptions import ClientException, NotFoundException

from app.database import get_project
from app.services.conversation_branch_service import ConversationBranchService


@post("/{project_id:str}/sessions/{session_id:str}/fork", status_code=201, sync_to_thread=False)
def fork_session(project_id: str, session_id: str, data: dict) -> dict[str, Any]:
    """Fork a conversation onto a new run. Returns the child ``{branch_id, session_id}``.

    Body: ``{conversation_id, fork_message_index, name?}``.
    """
    del session_id
    project = get_project(project_id)
    if not project:
        raise NotFoundException(detail="Project not found")

    body = data or {}
    conversation_id = body.get("conversation_id")
    fork_message_index = body.get("fork_message_index")
    if not conversation_id or fork_message_index is None:
        raise ClientException(detail="conversation_id and fork_message_index are required")
    try:
        fork_message_index = int(fork_message_index)
    except (TypeError, ValueError) as exc:
        raise ClientException(detail="fork_message_index must be an integer") from exc

    cwd = project.get("local_path") or project.get("worktree_base_path") or "."
    try:
        result = ConversationBranchService.fork_to_run(
            conversation_id,
            fork_message_index,
            project_id=project_id,
            cwd=cwd,
            name=body.get("name"),
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise NotFoundException(detail=msg) from exc
        raise ClientException(detail=msg) from exc
    return result


session_fork_router = Router(
    path="/api/projects",
    route_handlers=[fork_session],
)
