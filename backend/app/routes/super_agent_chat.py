"""SuperAgent chat send migrated to Litestar :20002 in wave 76.

Only /admin/super-agents/{id}/sessions/{sid}/chat/stream stays on Flask.
"""

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..services.chat_state_service import ChatStateService

tag = Tag(name="super-agent-chat", description="SuperAgent chat streaming (Flask leftover)")
super_agent_chat_bp = APIBlueprint(
    "super_agent_chat",
    __name__,
    url_prefix="/admin/super-agents",
    abp_tags=[tag],
)


class SessionPath(BaseModel):
    super_agent_id: str = Field(..., description="SuperAgent ID")
    session_id: str = Field(..., description="Session ID")


@super_agent_chat_bp.get("/<super_agent_id>/sessions/<session_id>/chat/stream")
def stream_chat_sse(path: SessionPath):
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
