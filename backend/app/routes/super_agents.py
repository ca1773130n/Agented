"""SuperAgent, Document, and Session management API endpoints."""

import json
import logging
import sqlite3
import threading
import time
from http import HTTPStatus
from typing import Optional

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

logger = logging.getLogger(__name__)

from ..database import (
    add_super_agent_document,
    delete_super_agent,
    delete_super_agent_document,
    get_all_super_agents,
    get_super_agent,
    get_super_agent_document,
    get_super_agent_documents,
    get_super_agent_session,
    get_super_agent_sessions,
    update_super_agent,
    update_super_agent_document,
)
from ..database import (
    create_super_agent as db_create_super_agent,
)
from ..models.common import PaginationQuery
from ..services.super_agent_session_service import SuperAgentSessionService

tag = Tag(name="super-agents", description="SuperAgent management operations")
super_agents_bp = APIBlueprint(
    "super_agents", __name__, url_prefix="/admin/super-agents", abp_tags=[tag]
)


class SuperAgentPath(BaseModel):
    super_agent_id: str = Field(..., description="SuperAgent ID")


class DocumentPath(BaseModel):
    super_agent_id: str = Field(..., description="SuperAgent ID")
    doc_id: int = Field(..., description="Document ID")


class SessionPath(BaseModel):
    super_agent_id: str = Field(..., description="SuperAgent ID")
    session_id: str = Field(..., description="Session ID")


# =============================================================================
# SuperAgent endpoints
# =============================================================================


@super_agents_bp.get("/")
def list_super_agents(query: PaginationQuery):
    """List all super agents."""
    from ..db.super_agents import count_all_super_agents

    super_agents = get_all_super_agents(limit=query.limit, offset=query.offset or 0)
    total_count = count_all_super_agents()
    return {"super_agents": super_agents, "total_count": total_count}, HTTPStatus.OK


@super_agents_bp.post("/")
def create_super_agent():
    """Create a new super agent."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    name = data.get("name")
    if not name:
        return error_response("BAD_REQUEST", "name is required", HTTPStatus.BAD_REQUEST)

    try:
        sa_id = db_create_super_agent(
            name=name,
            description=data.get("description"),
            backend_type=data.get("backend_type", "claude"),
            preferred_model=data.get("preferred_model"),
            team_id=data.get("team_id"),
            parent_super_agent_id=data.get("parent_super_agent_id"),
            max_concurrent_sessions=data.get("max_concurrent_sessions", 10),
            config_json=data.get("config_json"),
        )
    except sqlite3.IntegrityError as e:
        logger.error("Integrity error creating super agent: %s", e)
        return error_response(
            "CONFLICT",
            "A super agent with this name or configuration already exists",
            HTTPStatus.CONFLICT,
        )
    except sqlite3.OperationalError as e:
        logger.error("DB error creating super agent: %s", e)
        return error_response(
            "SERVICE_UNAVAILABLE",
            "Database unavailable, please retry",
            HTTPStatus.SERVICE_UNAVAILABLE,
        )
    if not sa_id:
        return error_response(
            "INTERNAL_SERVER_ERROR",
            "Failed to create super agent — the database insert returned no ID",
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    return {"message": "SuperAgent created", "super_agent_id": sa_id}, HTTPStatus.CREATED


@super_agents_bp.get("/<super_agent_id>")
def get_super_agent_endpoint(path: SuperAgentPath):
    """Get a super agent by ID."""
    sa = get_super_agent(path.super_agent_id)
    if not sa:
        return error_response("NOT_FOUND", "SuperAgent not found", HTTPStatus.NOT_FOUND)
    return sa, HTTPStatus.OK


@super_agents_bp.put("/<super_agent_id>")
def update_super_agent_endpoint(path: SuperAgentPath):
    """Update a super agent."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    if not update_super_agent(
        path.super_agent_id,
        name=data.get("name"),
        description=data.get("description"),
        backend_type=data.get("backend_type"),
        preferred_model=data.get("preferred_model"),
        team_id=data.get("team_id"),
        parent_super_agent_id=data.get("parent_super_agent_id"),
        max_concurrent_sessions=data.get("max_concurrent_sessions"),
        enabled=data.get("enabled"),
        config_json=data.get("config_json"),
    ):
        return error_response(
            "NOT_FOUND", "SuperAgent not found or no changes made", HTTPStatus.NOT_FOUND
        )

    return {"message": "SuperAgent updated"}, HTTPStatus.OK


@super_agents_bp.delete("/<super_agent_id>")
def delete_super_agent_endpoint(path: SuperAgentPath):
    """Delete a super agent."""
    if not delete_super_agent(path.super_agent_id):
        return error_response("NOT_FOUND", "SuperAgent not found", HTTPStatus.NOT_FOUND)
    return {"message": "SuperAgent deleted"}, HTTPStatus.OK


# =============================================================================
# Document endpoints (nested under super agent)
# =============================================================================


@super_agents_bp.get("/<super_agent_id>/documents")
def list_documents(path: SuperAgentPath):
    """List all documents for a super agent."""
    documents = get_super_agent_documents(path.super_agent_id)
    return {"documents": documents}, HTTPStatus.OK


@super_agents_bp.post("/<super_agent_id>/documents")
def create_document(path: SuperAgentPath):
    """Create a document for a super agent."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    doc_type = data.get("doc_type")
    if not doc_type:
        return error_response("BAD_REQUEST", "doc_type is required", HTTPStatus.BAD_REQUEST)

    title = data.get("title")
    if not title:
        return error_response("BAD_REQUEST", "title is required", HTTPStatus.BAD_REQUEST)

    doc_id = add_super_agent_document(
        super_agent_id=path.super_agent_id,
        doc_type=doc_type,
        title=title,
        content=data.get("content", ""),
    )
    if doc_id is None:
        return error_response(
            "BAD_REQUEST", "Invalid doc_type or failed to create document", HTTPStatus.BAD_REQUEST
        )

    return {"message": "Document created", "document_id": doc_id}, HTTPStatus.CREATED


@super_agents_bp.get("/<super_agent_id>/documents/<int:doc_id>")
def get_document_endpoint(path: DocumentPath):
    """Get a document by ID."""
    doc = get_super_agent_document(path.doc_id)
    if not doc:
        return error_response("NOT_FOUND", "Document not found", HTTPStatus.NOT_FOUND)
    return doc, HTTPStatus.OK


@super_agents_bp.put("/<super_agent_id>/documents/<int:doc_id>")
def update_document_endpoint(path: DocumentPath):
    """Update a document."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    if not update_super_agent_document(
        path.doc_id,
        title=data.get("title"),
        content=data.get("content"),
    ):
        return error_response(
            "NOT_FOUND", "Document not found or no changes made", HTTPStatus.NOT_FOUND
        )

    return {"message": "Document updated"}, HTTPStatus.OK


@super_agents_bp.delete("/<super_agent_id>/documents/<int:doc_id>")
def delete_document_endpoint(path: DocumentPath):
    """Delete a document."""
    if not delete_super_agent_document(path.doc_id):
        return error_response("NOT_FOUND", "Document not found", HTTPStatus.NOT_FOUND)
    return {"message": "Document deleted"}, HTTPStatus.OK


# =============================================================================
# Session endpoints (nested under super agent)
# =============================================================================


@super_agents_bp.get("/<super_agent_id>/sessions")
def list_sessions(path: SuperAgentPath):
    """List all sessions for a super agent."""
    sessions = get_super_agent_sessions(path.super_agent_id)
    return {"sessions": sessions}, HTTPStatus.OK


@super_agents_bp.post("/<super_agent_id>/sessions")
def create_session(path: SuperAgentPath):
    """Create a new session for a super agent."""
    session_id, error = SuperAgentSessionService.create_session(path.super_agent_id)
    if error:
        if "not found" in error.lower():
            return error_response("NOT_FOUND", error, HTTPStatus.NOT_FOUND)
        return error_response("BAD_REQUEST", error, HTTPStatus.BAD_REQUEST)

    # Initialize chat state for versioned SSE delivery
    from ..services.chat_state_service import ChatStateService

    ChatStateService.init_session(session_id)

    return {"message": "Session created", "session_id": session_id}, HTTPStatus.CREATED


@super_agents_bp.get("/<super_agent_id>/sessions/<session_id>")
def get_session_endpoint(path: SessionPath):
    """Get a session by ID."""
    session = get_super_agent_session(path.session_id)
    if not session:
        return error_response("NOT_FOUND", "Session not found", HTTPStatus.NOT_FOUND)
    return session, HTTPStatus.OK


@super_agents_bp.post("/<super_agent_id>/sessions/<session_id>/message")
def send_session_message(path: SessionPath):
    """Send a message to a session."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    message = data.get("message")
    if not message:
        return error_response("BAD_REQUEST", "message is required", HTTPStatus.BAD_REQUEST)

    success, error = SuperAgentSessionService.send_message(path.session_id, message)
    if not success:
        if "not found" in error.lower():
            return error_response("NOT_FOUND", error, HTTPStatus.NOT_FOUND)
        return error_response("BAD_REQUEST", error, HTTPStatus.BAD_REQUEST)
    return {"message": "Message sent"}, HTTPStatus.OK


@super_agents_bp.post("/<super_agent_id>/sessions/<session_id>/end")
def end_session(path: SessionPath):
    """End a session."""
    success, error = SuperAgentSessionService.end_session(path.session_id)
    if not success:
        return error_response("NOT_FOUND", error, HTTPStatus.NOT_FOUND)

    # Clean up chat state and poison-pill subscriber queues
    from ..services.chat_state_service import ChatStateService

    ChatStateService.remove_session(path.session_id)

    return {"message": "Session ended"}, HTTPStatus.OK


@super_agents_bp.get("/<super_agent_id>/sessions/<session_id>/stream")
def stream_session(path: SessionPath):
    """Stream session output via Server-Sent Events (SSE).

    SSE Protocol:
    - Event 'data': {"type": "output", "content": str} -- output line from session
    - Event 'data': {"type": "heartbeat"} -- keepalive sent every 5 seconds

    Polls session output lines and emits them as SSE data events.
    """

    def generate():
        """Yield SSE output and heartbeat events for the session stream."""
        while True:
            # Check for output lines
            lines = SuperAgentSessionService.get_output_lines(path.session_id)
            for line in lines:
                yield f"data: {json.dumps({'type': 'output', 'content': line})}\n\n"
            # Send heartbeat
            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            time.sleep(5)

    return Response(generate(), mimetype="text/event-stream")


# =============================================================================
# Chat endpoints (versioned SSE protocol with cursor-based delta delivery)
# =============================================================================


class ChatSendRequest(BaseModel):
    """Request body for sending a chat message."""

    content: str = Field(..., description="Message content")
    backend: str = Field("auto", description="Backend to use (auto, claude, opencode)")
    account_id: Optional[str] = Field(None, description="Account ID for proxy routing")
    model: Optional[str] = Field(None, description="Model override")
    mode: str = Field("single", description="Chat mode: single, all, compound")


def _generate_message_id() -> str:
    """Generate a unique message ID with msg- prefix."""
    from app.db.ids import generate_message_id

    return generate_message_id()


def _resolve_session(data: dict, super_agent_id: str, session_id: str) -> dict:
    """Resolve session and effective backend from request data.

    Returns a dict with resolved values, or a dict with 'error_response' key on failure.
    """
    session = get_super_agent_session(session_id)
    if not session:
        return {"error_response": error_response("NOT_FOUND", "Session not found", HTTPStatus.NOT_FOUND)}
    if session.get("status") != "active":
        return {"error_response": error_response("BAD_REQUEST", "Session is not active", HTTPStatus.BAD_REQUEST)}

    backend = data.get("backend", "auto")
    effective_backend = backend if backend != "auto" else None
    if not effective_backend:
        sa = get_super_agent(super_agent_id)
        effective_backend = (sa.get("backend_type") if sa else None) or "claude"

    return {
        "session": session,
        "effective_backend": effective_backend,
        "backend": backend,
        "account_id": data.get("account_id"),
        "model": data.get("model"),
        "mode": data.get("mode", "single"),
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
        return {"status": "streaming", "mode": "all", "message_id": message_id, "backends": execution_map}
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
        return {"status": "streaming", "mode": "compound", "message_id": message_id, "backends": execution_map}


def _launch_background_thread(
    session_id: str,
    super_agent_id: str,
    effective_backend: str,
    account_id: Optional[str],
    model: Optional[str],
) -> None:
    """Launch a background thread to stream a single-mode LLM response."""
    from ..services.chat_state_service import ChatStateService

    _session_id = session_id
    _super_agent_id = super_agent_id

    def _stream_response():
        try:
            from ..services.conversation_streaming import stream_llm_response

            ChatStateService.push_status(_session_id, "streaming")

            system_prompt = SuperAgentSessionService.assemble_system_prompt(
                _super_agent_id, _session_id
            )
            state = SuperAgentSessionService.get_session_state(_session_id)
            llm_messages = []
            if system_prompt:
                llm_messages.append({"role": "system", "content": system_prompt})
            if state and state.get("conversation_log"):
                for msg in state["conversation_log"]:
                    llm_messages.append(
                        {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                    )

            accumulated = []
            for chunk in stream_llm_response(
                llm_messages,
                model=model,
                account_email=account_id,
                backend=effective_backend,
            ):
                if chunk:
                    accumulated.append(chunk)
                    ChatStateService.push_delta(_session_id, "content_delta", {"content": chunk})

            full_response = "".join(accumulated)
            if full_response:
                SuperAgentSessionService.add_assistant_message(
                    _session_id, full_response, backend=effective_backend
                )
                if effective_backend:
                    try:
                        from ..db.backends import update_backend_last_used

                        update_backend_last_used(effective_backend)
                    except Exception:
                        logger.error("Unexpected error in super agent operation", exc_info=True)

            ChatStateService.push_delta(
                _session_id, "finish", {"content": full_response, "backend": effective_backend}
            )
            ChatStateService.push_status(_session_id, "idle")

        except Exception as e:
            logger.exception("Streaming error for session %s", _session_id)
            try:
                ChatStateService.push_delta(_session_id, "error", {"error": str(e)})
                ChatStateService.push_status(_session_id, "error")
            except Exception:
                logger.exception(
                    "Failed to propagate streaming error to client for session %s", _session_id
                )

    threading.Thread(target=_stream_response, daemon=True).start()


@super_agents_bp.get("/<super_agent_id>/sessions/<session_id>/chat/stream")
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


@super_agents_bp.post("/<super_agent_id>/sessions/<session_id>/chat")
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
            mode, path.session_id, path.super_agent_id,
            effective_backend, account_id, model, message_id,
        )
        return result, HTTPStatus.OK

    _launch_background_thread(
        path.session_id, path.super_agent_id, effective_backend, account_id, model
    )

    return {"status": "ok", "message_id": message_id}, HTTPStatus.OK


class MessagePath(BaseModel):
    super_agent_id: str = Field(..., description="SuperAgent ID")
    message_id: str = Field(..., description="Message ID")


# =============================================================================
# Message endpoints (nested under super agent)
# =============================================================================


@super_agents_bp.post("/<super_agent_id>/messages")
def send_agent_message(path: SuperAgentPath):
    """Send a message from this SuperAgent to another agent or broadcast."""
    from ..services.agent_message_bus_service import AgentMessageBusService

    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    content = data.get("content", "").strip()
    if not content:
        return error_response("BAD_REQUEST", "content is required", HTTPStatus.BAD_REQUEST)

    msg_id = AgentMessageBusService.send_message(
        from_agent_id=path.super_agent_id,
        to_agent_id=data.get("to_agent_id"),
        message_type=data.get("message_type", "message"),
        priority=data.get("priority", "normal"),
        subject=data.get("subject"),
        content=content,
        ttl_seconds=data.get("ttl_seconds"),
    )
    if not msg_id:
        return error_response(
            "INTERNAL_SERVER_ERROR", "Failed to send message", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    return {"message": "Message sent", "message_id": msg_id}, HTTPStatus.CREATED


@super_agents_bp.get("/<super_agent_id>/messages/inbox")
def get_inbox(path: SuperAgentPath):
    """List inbox messages for this SuperAgent."""
    from ..db.messages import get_inbox_messages

    status_filter = request.args.get("status")
    messages = get_inbox_messages(path.super_agent_id, status=status_filter)
    return {"messages": messages}, HTTPStatus.OK


@super_agents_bp.get("/<super_agent_id>/messages/outbox")
def get_outbox(path: SuperAgentPath):
    """List outbox messages from this SuperAgent."""
    from ..db.messages import get_outbox_messages

    messages = get_outbox_messages(path.super_agent_id)
    return {"messages": messages}, HTTPStatus.OK


@super_agents_bp.post("/<super_agent_id>/messages/<message_id>/read")
def mark_message_read(path: MessagePath):
    """Mark a message as read."""
    from ..db.messages import update_message_status

    if not update_message_status(path.message_id, "read"):
        return error_response("NOT_FOUND", "Message not found", HTTPStatus.NOT_FOUND)

    return {"message": "Message marked as read"}, HTTPStatus.OK


@super_agents_bp.get("/<super_agent_id>/messages/stream")
def stream_messages(path: SuperAgentPath):
    """Stream message notifications via Server-Sent Events (SSE).

    SSE Protocol:
    - Event 'message': {"id": str, "from": str, "content": str, "timestamp": str}
      Delivers real-time inter-agent messages from the message bus.
    """
    from ..services.agent_message_bus_service import AgentMessageBusService

    def generate():
        """Yield SSE events from the agent message bus subscription."""
        yield from AgentMessageBusService.subscribe(path.super_agent_id)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
