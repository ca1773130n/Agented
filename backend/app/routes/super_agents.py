"""SuperAgent, Document, and Session management API endpoints."""

import json
import logging
import random
import string
import threading
import time
from http import HTTPStatus
from typing import Optional

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from ..database import (
    add_super_agent,
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
def list_super_agents():
    """List all super agents."""
    super_agents = get_all_super_agents()
    return {"super_agents": super_agents}, HTTPStatus.OK


@super_agents_bp.post("/")
def create_super_agent():
    """Create a new super agent."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    name = data.get("name")
    if not name:
        return {"error": "name is required"}, HTTPStatus.BAD_REQUEST

    sa_id = add_super_agent(
        name=name,
        description=data.get("description"),
        backend_type=data.get("backend_type", "claude"),
        preferred_model=data.get("preferred_model"),
        team_id=data.get("team_id"),
        parent_super_agent_id=data.get("parent_super_agent_id"),
        max_concurrent_sessions=data.get("max_concurrent_sessions", 10),
        config_json=data.get("config_json"),
    )
    if not sa_id:
        return {"error": "Failed to create super agent"}, HTTPStatus.INTERNAL_SERVER_ERROR

    return {"message": "SuperAgent created", "super_agent_id": sa_id}, HTTPStatus.CREATED


@super_agents_bp.get("/<super_agent_id>")
def get_super_agent_endpoint(path: SuperAgentPath):
    """Get a super agent by ID."""
    sa = get_super_agent(path.super_agent_id)
    if not sa:
        return {"error": "SuperAgent not found"}, HTTPStatus.NOT_FOUND
    return sa, HTTPStatus.OK


@super_agents_bp.put("/<super_agent_id>")
def update_super_agent_endpoint(path: SuperAgentPath):
    """Update a super agent."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

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
        return {"error": "SuperAgent not found or no changes made"}, HTTPStatus.NOT_FOUND

    return {"message": "SuperAgent updated"}, HTTPStatus.OK


@super_agents_bp.delete("/<super_agent_id>")
def delete_super_agent_endpoint(path: SuperAgentPath):
    """Delete a super agent."""
    if not delete_super_agent(path.super_agent_id):
        return {"error": "SuperAgent not found"}, HTTPStatus.NOT_FOUND
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
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    doc_type = data.get("doc_type")
    if not doc_type:
        return {"error": "doc_type is required"}, HTTPStatus.BAD_REQUEST

    title = data.get("title")
    if not title:
        return {"error": "title is required"}, HTTPStatus.BAD_REQUEST

    doc_id = add_super_agent_document(
        super_agent_id=path.super_agent_id,
        doc_type=doc_type,
        title=title,
        content=data.get("content", ""),
    )
    if doc_id is None:
        return {"error": "Invalid doc_type or failed to create document"}, HTTPStatus.BAD_REQUEST

    return {"message": "Document created", "document_id": doc_id}, HTTPStatus.CREATED


@super_agents_bp.get("/<super_agent_id>/documents/<int:doc_id>")
def get_document_endpoint(path: DocumentPath):
    """Get a document by ID."""
    doc = get_super_agent_document(path.doc_id)
    if not doc:
        return {"error": "Document not found"}, HTTPStatus.NOT_FOUND
    return doc, HTTPStatus.OK


@super_agents_bp.put("/<super_agent_id>/documents/<int:doc_id>")
def update_document_endpoint(path: DocumentPath):
    """Update a document."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    if not update_super_agent_document(
        path.doc_id,
        title=data.get("title"),
        content=data.get("content"),
    ):
        return {"error": "Document not found or no changes made"}, HTTPStatus.NOT_FOUND

    return {"message": "Document updated"}, HTTPStatus.OK


@super_agents_bp.delete("/<super_agent_id>/documents/<int:doc_id>")
def delete_document_endpoint(path: DocumentPath):
    """Delete a document."""
    if not delete_super_agent_document(path.doc_id):
        return {"error": "Document not found"}, HTTPStatus.NOT_FOUND
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
            return {"error": error}, HTTPStatus.NOT_FOUND
        return {"error": error}, HTTPStatus.BAD_REQUEST

    # Initialize chat state for versioned SSE delivery
    from ..services.chat_state_service import ChatStateService

    ChatStateService.init_session(session_id)

    return {"message": "Session created", "session_id": session_id}, HTTPStatus.CREATED


@super_agents_bp.get("/<super_agent_id>/sessions/<session_id>")
def get_session_endpoint(path: SessionPath):
    """Get a session by ID."""
    session = get_super_agent_session(path.session_id)
    if not session:
        return {"error": "Session not found"}, HTTPStatus.NOT_FOUND
    return session, HTTPStatus.OK


@super_agents_bp.post("/<super_agent_id>/sessions/<session_id>/message")
def send_session_message(path: SessionPath):
    """Send a message to a session."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    message = data.get("message")
    if not message:
        return {"error": "message is required"}, HTTPStatus.BAD_REQUEST

    success, error = SuperAgentSessionService.send_message(path.session_id, message)
    if not success:
        if "not found" in error.lower():
            return {"error": error}, HTTPStatus.NOT_FOUND
        return {"error": error}, HTTPStatus.BAD_REQUEST
    return {"message": "Message sent"}, HTTPStatus.OK


@super_agents_bp.post("/<super_agent_id>/sessions/<session_id>/end")
def end_session(path: SessionPath):
    """End a session."""
    success, error = SuperAgentSessionService.end_session(path.session_id)
    if not success:
        return {"error": error}, HTTPStatus.NOT_FOUND

    # Clean up chat state and poison-pill subscriber queues
    from ..services.chat_state_service import ChatStateService

    ChatStateService.remove_session(path.session_id)

    return {"message": "Session ended"}, HTTPStatus.OK


@super_agents_bp.get("/<super_agent_id>/sessions/<session_id>/stream")
def stream_session(path: SessionPath):
    """Stream session output via Server-Sent Events (SSE).

    Stub implementation: sends heartbeat events every 5 seconds.
    Real content streaming will be added with AI backend integration.
    """

    def generate():
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
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"msg-{suffix}"


@super_agents_bp.get("/<super_agent_id>/sessions/<session_id>/chat/stream")
def stream_chat_sse(path: SessionPath):
    """Stream chat events via versioned SSE with cursor-based reconnection.

    Reads Last-Event-ID from request headers for reconnection recovery.
    Replays missed events from the event log when last_seq is provided.
    Falls back to full_sync when client cursor is too old (evicted from log).
    Sends heartbeat comments every 30 seconds to keep connection alive.
    """
    from ..services.chat_state_service import ChatStateService

    last_event_id = request.headers.get("Last-Event-ID", "0")
    try:
        last_seq = int(last_event_id)
    except (ValueError, TypeError):
        last_seq = 0

    def generate():
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
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    content = data.get("content", "").strip()
    if not content:
        return {"error": "content is required"}, HTTPStatus.BAD_REQUEST

    backend = data.get("backend", "auto")
    account_id = data.get("account_id")
    model = data.get("model")

    # Verify session exists and is active
    session = get_super_agent_session(path.session_id)
    if not session:
        return {"error": "Session not found"}, HTTPStatus.NOT_FOUND
    if session.get("status") != "active":
        return {"error": "Session is not active"}, HTTPStatus.BAD_REQUEST

    # Determine effective backend (resolve before persisting so both
    # user and assistant messages carry backend attribution in the log)
    effective_backend = backend if backend != "auto" else None
    if not effective_backend:
        sa = get_super_agent(path.super_agent_id)
        effective_backend = (sa.get("backend_type") if sa else None) or "claude"

    # Add user message to session via SuperAgentSessionService
    success, error = SuperAgentSessionService.send_message(
        path.session_id, content, backend=effective_backend
    )
    if not success:
        return {"error": error}, HTTPStatus.BAD_REQUEST

    # Generate a message ID for this user message
    message_id = _generate_message_id()

    # Push user message as state delta
    ChatStateService.push_delta(
        path.session_id,
        "message",
        {"role": "user", "content": content, "message_id": message_id},
    )

    # Mode dispatch: all/compound use multi-backend fan-out, single is default
    mode = data.get("mode", "single")

    if mode in ("all", "compound"):
        from ..db.backends import get_all_backends

        all_backends = get_all_backends()
        backend_names = (
            [b["type"] for b in all_backends if b.get("is_installed")] if all_backends else []
        )
        if not backend_names:
            backend_names = ["claude"]  # Fallback

        # Build messages for LLM (same as single-mode assembly)
        system_prompt = SuperAgentSessionService.assemble_system_prompt(
            path.super_agent_id, path.session_id
        )
        state = SuperAgentSessionService.get_session_state(path.session_id)
        llm_messages = []
        if system_prompt:
            llm_messages.append({"role": "system", "content": system_prompt})
        if state and state.get("conversation_log"):
            for msg in state["conversation_log"]:
                llm_messages.append(
                    {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                )

        ChatStateService.push_status(path.session_id, "streaming")

        if mode == "all":
            from ..services.all_mode_service import AllModeService

            execution_map = AllModeService.fan_out(
                session_id=path.session_id,
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
            }, HTTPStatus.OK

        else:  # compound
            from ..services.all_mode_service import CompoundModeService

            primary_backend = effective_backend if effective_backend else backend_names[0]
            execution_map = CompoundModeService.start(
                session_id=path.session_id,
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
            }, HTTPStatus.OK

    # Capture path values for the background thread (Flask request context
    # is not available inside the thread)
    _session_id = path.session_id
    _super_agent_id = path.super_agent_id

    def _stream_response():
        try:
            from ..services.conversation_streaming import stream_llm_response

            ChatStateService.push_status(_session_id, "streaming")

            # Assemble system prompt from identity documents + session summary
            system_prompt = SuperAgentSessionService.assemble_system_prompt(
                _super_agent_id, _session_id
            )

            # Build messages from conversation log (now includes user + assistant)
            state = SuperAgentSessionService.get_session_state(_session_id)
            llm_messages = []
            if system_prompt:
                llm_messages.append({"role": "system", "content": system_prompt})
            if state and state.get("conversation_log"):
                for msg in state["conversation_log"]:
                    llm_messages.append(
                        {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                    )

            # Stream via unified function (handles claude/codex/gemini via CLIProxyAPI)
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

            # Persist assistant response to conversation log
            full_response = "".join(accumulated)
            if full_response:
                SuperAgentSessionService.add_assistant_message(
                    _session_id, full_response, backend=effective_backend
                )
                # Track last used timestamp on the backend
                if effective_backend:
                    try:
                        from ..db.backends import update_backend_last_used

                        update_backend_last_used(effective_backend)
                    except Exception:
                        pass

            # Push finish with full content and resolved backend so frontend
            # can store per-message backend attribution
            ChatStateService.push_delta(
                _session_id, "finish", {"content": full_response, "backend": effective_backend}
            )
            ChatStateService.push_status(_session_id, "idle")

        except Exception as e:
            logger.exception("Streaming error for session %s", _session_id)
            ChatStateService.push_delta(_session_id, "error", {"error": str(e)})
            ChatStateService.push_status(_session_id, "error")

    thread = threading.Thread(target=_stream_response, daemon=True)
    thread.start()

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
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    content = data.get("content", "").strip()
    if not content:
        return {"error": "content is required"}, HTTPStatus.BAD_REQUEST

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
        return {"error": "Failed to send message"}, HTTPStatus.INTERNAL_SERVER_ERROR

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
        return {"error": "Message not found"}, HTTPStatus.NOT_FOUND

    return {"message": "Message marked as read"}, HTTPStatus.OK


@super_agents_bp.get("/<super_agent_id>/messages/stream")
def stream_messages(path: SuperAgentPath):
    """Stream message notifications via Server-Sent Events (SSE)."""
    from ..services.agent_message_bus_service import AgentMessageBusService

    def generate():
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
