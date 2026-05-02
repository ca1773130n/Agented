"""GRD project management routes — SSE leftovers (wave 74).

CRUD/sync/sessions migrated to Litestar :20002. The two SSE streams stay
on Flask until the streaming wave:
- /api/projects/{id}/chat/stream
- /api/projects/{id}/sessions/{session_id}/stream
"""

from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response
from ..database import get_project, get_super_agent_sessions
from ..services.chat_state_service import ChatStateService
from ..services.project_session_manager import ProjectSessionManager

tag = Tag(name="grd", description="GRD streaming (Flask leftover)")
grd_bp = APIBlueprint("grd", __name__, url_prefix="/api/projects", abp_tags=[tag])


class ProjectIdPath(BaseModel):
    project_id: str = Field(..., description="Project ID")


class SessionPath(BaseModel):
    project_id: str = Field(..., description="Project ID")
    session_id: str = Field(..., description="Session ID")


@grd_bp.get("/<project_id>/chat/stream")
def project_chat_stream(path: ProjectIdPath):
    project = get_project(path.project_id)
    if not project:
        return error_response("NOT_FOUND", "Project not found", HTTPStatus.NOT_FOUND)
    sa_id = project.get("manager_super_agent_id")
    if not sa_id:
        return error_response("NOT_FOUND", "No manager agent configured", HTTPStatus.NOT_FOUND)

    sessions = get_super_agent_sessions(sa_id)
    active = [s for s in sessions if s.get("status") == "active"]
    if not active:
        return error_response("NOT_FOUND", "No active chat session", HTTPStatus.NOT_FOUND)
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


@grd_bp.get("/<project_id>/sessions/<session_id>/stream")
def stream_session(path: SessionPath):
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
