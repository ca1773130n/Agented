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
from litestar.exceptions import ClientException, NotFoundException, PermissionDeniedException

from app.database import get_project
from app.db.agents import get_agent_conversation
from app.services.conversation_branch_service import ConversationBranchService
from app_litestar.auth import Caller


@post("/{project_id:str}/sessions/{session_id:str}/fork", status_code=201, sync_to_thread=False)
def fork_session(project_id: str, session_id: str, data: dict, caller: Caller) -> dict[str, Any]:
    """Fork a conversation onto a new run. Returns the child ``{branch_id, session_id}``.

    Body: ``{conversation_id, fork_message_index, name?}``.

    SECURITY (25 BLOCKER — ownership gate): forking copies the source
    conversation's transcript into a new run, so the caller must OWN the source
    conversation (and, when it has one, the project) — else 403. Fail CLOSED: an
    unattributed (NULL-owner) conversation is forkable only by an admin, never by
    an arbitrary authenticated caller. This blocks reading another user's
    transcript (and spending resources) via a guessed conversation/project id.
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

    caller_user_id = getattr(caller, "user_id", None) if caller else None
    is_admin = (getattr(caller, "role", None) if caller else None) == "admin"

    conversation = get_agent_conversation(conversation_id)
    if not conversation:
        raise NotFoundException(detail="Conversation not found")

    if not is_admin:
        # Hard gate: own the source conversation (fail closed on an unknown owner).
        conv_owner = conversation.get("user_id")
        if conv_owner is None or caller_user_id is None or conv_owner != caller_user_id:
            raise PermissionDeniedException(detail="You do not own this conversation")
        # If the project is owned, it must be by the same caller.
        proj_owner = project.get("user_id")
        if proj_owner is not None and proj_owner != caller_user_id:
            raise PermissionDeniedException(detail="You do not own this project")

    cwd = project.get("local_path") or project.get("worktree_base_path") or "."
    try:
        result = ConversationBranchService.fork_to_run(
            conversation_id,
            fork_message_index,
            project_id=project_id,
            cwd=cwd,
            name=body.get("name"),
            # The forked run is owned by the caller so they can stream it (the
            # SSE gate now fails closed on an unattributed session).
            created_by=caller_user_id,
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
