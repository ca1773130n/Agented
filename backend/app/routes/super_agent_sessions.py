"""SuperAgent session management API endpoints."""

import json
import time
from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..database import (
    get_super_agent_session,
    get_super_agent_sessions,
)
from ..services.super_agent_session_service import SuperAgentSessionService
from .super_agents import SuperAgentPath

tag = Tag(name="super-agent-sessions", description="SuperAgent session operations")
super_agent_sessions_bp = APIBlueprint(
    "super_agent_sessions", __name__, url_prefix="/admin/super-agents", abp_tags=[tag]
)


class SessionPath(BaseModel):
    super_agent_id: str = Field(..., description="SuperAgent ID")
    session_id: str = Field(..., description="Session ID")


@super_agent_sessions_bp.get("/<super_agent_id>/sessions")
def list_sessions(path: SuperAgentPath):
    """List all sessions for a super agent or project-scoped instance."""
    if path.super_agent_id.startswith("psa-"):
        from ..db.super_agents import get_sessions_for_instance

        sessions = get_sessions_for_instance(path.super_agent_id)
    else:
        sessions = get_super_agent_sessions(path.super_agent_id)
    return {"sessions": sessions}, HTTPStatus.OK


@super_agent_sessions_bp.post("/<super_agent_id>/sessions")
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


@super_agent_sessions_bp.get("/<super_agent_id>/sessions/<session_id>")
def get_session_endpoint(path: SessionPath):
    """Get a session by ID."""
    session = get_super_agent_session(path.session_id)
    if not session:
        return error_response("NOT_FOUND", "Session not found", HTTPStatus.NOT_FOUND)
    return session, HTTPStatus.OK


@super_agent_sessions_bp.post("/<super_agent_id>/sessions/<session_id>/message")
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


@super_agent_sessions_bp.post("/<super_agent_id>/sessions/<session_id>/end")
def end_session(path: SessionPath):
    """End a session."""
    success, error = SuperAgentSessionService.end_session(path.session_id)
    if not success:
        return error_response("NOT_FOUND", error, HTTPStatus.NOT_FOUND)

    # Clean up chat state and poison-pill subscriber queues
    from ..services.chat_state_service import ChatStateService

    ChatStateService.remove_session(path.session_id)

    return {"message": "Session ended"}, HTTPStatus.OK


@super_agent_sessions_bp.get("/<super_agent_id>/sessions/<session_id>/stream")
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
