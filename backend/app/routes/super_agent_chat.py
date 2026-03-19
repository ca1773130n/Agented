"""SuperAgent chat API endpoints."""

import logging
from http import HTTPStatus
from typing import Optional

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..database import (
    get_super_agent,
    get_super_agent_session,
)
from ..services.super_agent_session_service import SuperAgentSessionService

logger = logging.getLogger(__name__)

tag = Tag(name="super-agent-chat", description="SuperAgent chat operations")
super_agent_chat_bp = APIBlueprint(
    "super_agent_chat", __name__, url_prefix="/admin/super-agents", abp_tags=[tag]
)


class SessionPath(BaseModel):
    super_agent_id: str = Field(..., description="SuperAgent ID")
    session_id: str = Field(..., description="Session ID")


class ChatSendRequest(BaseModel):
    """Request body for sending a chat message."""

    content: str = Field(..., description="Message content")
    backend: str = Field("auto", description="Backend to use (auto, claude, opencode)")
    account_id: Optional[str] = Field(None, description="Account ID for proxy routing")
    model: Optional[str] = Field(None, description="Model override")
    mode: str = Field("single", description="Chat mode: single, all, compound")
    chat_mode: Optional[str] = Field(None, description="Chat mode: management or work")


def _generate_message_id() -> str:
    """Generate a unique message ID with msg- prefix."""
    from app.db.ids import generate_message_id

    return generate_message_id()


def _resolve_session(data: dict, super_agent_id: str, session_id: str) -> dict:
    """Resolve session and effective backend from request data.

    Returns a dict with resolved values, or a dict with 'error_response' key on failure.
    Handles psa- prefixed IDs for project-scoped instances.
    """
    session = get_super_agent_session(session_id)
    if not session:
        return {
            "error_response": error_response("NOT_FOUND", "Session not found", HTTPStatus.NOT_FOUND)
        }
    if session.get("status") != "active":
        return {
            "error_response": error_response(
                "BAD_REQUEST", "Session is not active", HTTPStatus.BAD_REQUEST
            )
        }

    backend = data.get("backend", "auto")
    effective_backend = backend if backend != "auto" else None

    instance = None
    if super_agent_id.startswith("psa-"):
        from ..db.project_sa_instances import get_project_sa_instance

        instance = get_project_sa_instance(super_agent_id)
        if not instance:
            return {
                "error_response": error_response(
                    "NOT_FOUND", "Instance not found", HTTPStatus.NOT_FOUND
                )
            }
        # Use the template SA for backend resolution
        if not effective_backend:
            sa = get_super_agent(instance["template_sa_id"])
            effective_backend = (sa.get("backend_type") if sa else None) or "claude"
    else:
        if not effective_backend:
            sa = get_super_agent(super_agent_id)
            effective_backend = (sa.get("backend_type") if sa else None) or "claude"

    # Resolve chat_mode
    chat_mode = data.get("chat_mode")
    if not chat_mode and instance:
        chat_mode = instance.get("default_chat_mode", "management")

    # Resolve cwd for work mode
    cwd = instance["worktree_path"] if instance and chat_mode == "work" else None

    return {
        "session": session,
        "effective_backend": effective_backend,
        "backend": backend,
        "account_id": data.get("account_id"),
        "model": data.get("model"),
        "mode": data.get("mode", "single"),
        "instance": instance,
        "chat_mode": chat_mode,
        "cwd": cwd,
    }


def _dispatch_by_mode(
    mode: str,
    session_id: str,
    super_agent_id: str,
    effective_backend: str,
    account_id: Optional[str],
    model: Optional[str],
    message_id: str,
) -> dict:
    """Fan-out dispatch for 'all' or 'compound' mode. Returns response body dict."""
    from ..db.backends import get_all_backends
    from ..services.chat_state_service import ChatStateService

    all_backends = get_all_backends()
    unavailable_backends = (
        [b["type"] for b in all_backends if not b.get("is_installed")] if all_backends else []
    )
    backend_names = (
        [b["type"] for b in all_backends if b.get("is_installed")] if all_backends else []
    )
    if not backend_names:
        logger.warning(
            "No installed backends found for '%s' mode; falling back to ['claude']. "
            "Unavailable backends: %s",
            mode,
            unavailable_backends or "none detected",
        )
        backend_names = ["claude"]
    elif unavailable_backends:
        logger.info(
            "Some backends unavailable for '%s' mode (not installed): %s",
            mode,
            unavailable_backends,
        )

    system_prompt = SuperAgentSessionService.assemble_system_prompt(super_agent_id, session_id)
    state = SuperAgentSessionService.get_session_state(session_id)
    llm_messages = []
    if system_prompt:
        llm_messages.append({"role": "system", "content": system_prompt})
    if state and state.get("conversation_log"):
        for msg in state["conversation_log"]:
            llm_messages.append(
                {"role": msg.get("role", "user"), "content": msg.get("content", "")}
            )

    ChatStateService.push_status(session_id, "streaming")

    if mode == "all":
        from ..services.all_mode_service import AllModeService

        execution_map = AllModeService.fan_out(
            session_id=session_id,
            messages=llm_messages,
            backends=backend_names,
            model=model,
            account_email=account_id,
            timeout=30,
        )
        return {
            "status": "streaming",
            "mode": "all",
            "message_id": message_id,
            "backends": execution_map,
        }
    else:  # compound
        from ..services.all_mode_service import CompoundModeService

        primary_backend = effective_backend if effective_backend else backend_names[0]
        execution_map = CompoundModeService.start(
            session_id=session_id,
            messages=llm_messages,
            backends=backend_names,
            primary_backend=primary_backend,
            model=model,
            account_email=account_id,
            timeout=30,
        )
        return {
            "status": "streaming",
            "mode": "compound",
            "message_id": message_id,
            "backends": execution_map,
        }


def _launch_background_thread(
    session_id: str,
    super_agent_id: str,
    effective_backend: str,
    account_id: Optional[str],
    model: Optional[str],
    cwd: Optional[str] = None,
    chat_mode: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> None:
    """Launch background thread for LLM streaming using shared helper."""
    from ..services.streaming_helper import run_streaming_response

    run_streaming_response(
        session_id=session_id,
        super_agent_id=super_agent_id,
        backend=effective_backend,
        account_id=account_id,
        model=model,
        cwd=cwd,
        chat_mode=chat_mode,
        instance_id=instance_id,
    )


@super_agent_chat_bp.get("/<super_agent_id>/sessions/<session_id>/chat/stream")
def stream_chat_sse(path: SessionPath):
    """Stream chat events via versioned SSE with cursor-based reconnection.

    SSE Protocol:
    - Event 'state_delta': {"type": str, "data": dict, "seq": int}
      Delta types: message, content_delta, tool_call, finish, status_change, error
    - Event 'full_sync': {"events": [dict]} -- replays all log entries when cursor
      is too old (evicted from the capped event log)
    - Comment heartbeat: sent every 30 seconds to keep proxies from closing

    Supports Last-Event-ID header for cursor-based reconnection. On reconnect,
    missed events are replayed from the event log. If the client's cursor has been
    evicted, a full_sync event is sent instead.
    """
    from ..services.chat_state_service import ChatStateService

    last_event_id = request.headers.get("Last-Event-ID", "0")
    try:
        last_seq = int(last_event_id)
    except (ValueError, TypeError):
        last_seq = 0

    def generate():
        """Yield SSE state_delta events from the chat state subscription."""
        yield from ChatStateService.subscribe(path.session_id, last_seq)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@super_agent_chat_bp.post("/<super_agent_id>/sessions/<session_id>/chat")
def send_chat_message(path: SessionPath):
    """Send a chat message and trigger proxy or subprocess based on routing.

    Adds the user message to the session conversation log, pushes it as a
    state delta, and initiates streaming via CLIProxyChatService (if proxy)
    or logs the subprocess path (default).
    """
    from ..services.chat_state_service import ChatStateService

    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    content = data.get("content", "").strip()
    if not content:
        return error_response("BAD_REQUEST", "content is required", HTTPStatus.BAD_REQUEST)

    resolved = _resolve_session(data, path.super_agent_id, path.session_id)
    if "error_response" in resolved:
        return resolved["error_response"]

    effective_backend = resolved["effective_backend"]
    account_id = resolved["account_id"]
    model = resolved["model"]
    mode = resolved["mode"]
    cwd = resolved.get("cwd")
    chat_mode = resolved.get("chat_mode")
    instance = resolved.get("instance")

    # Add user message to session via SuperAgentSessionService
    success, error = SuperAgentSessionService.send_message(
        path.session_id, content, backend=effective_backend
    )
    if not success:
        return error_response("BAD_REQUEST", error, HTTPStatus.BAD_REQUEST)

    message_id = _generate_message_id()

    ChatStateService.push_delta(
        path.session_id,
        "message",
        {"role": "user", "content": content, "message_id": message_id},
    )

    if mode in ("all", "compound"):
        result = _dispatch_by_mode(
            mode,
            path.session_id,
            path.super_agent_id,
            effective_backend,
            account_id,
            model,
            message_id,
        )
        return result, HTTPStatus.OK

    _launch_background_thread(
        path.session_id,
        path.super_agent_id,
        effective_backend,
        account_id,
        model,
        cwd=cwd,
        chat_mode=chat_mode,
        instance_id=instance["id"] if instance else None,
    )

    return {"status": "ok", "message_id": message_id}, HTTPStatus.OK
