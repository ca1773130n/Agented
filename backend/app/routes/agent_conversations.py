"""Agent conversations CRUD migrated to Litestar :20002 in wave 71.

The /api/agents/conversations/{id}/stream SSE route stays on Flask until
the dedicated streaming wave so we can lift the Litestar `Stream` pattern
across all conversation streams in one pass.
"""

from flask import Response
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..services.agent_conversation_service import AgentConversationService

tag = Tag(name="agent-conversations", description="Agent conversation streaming (Flask leftover)")
agent_conversations_bp = APIBlueprint(
    "agent_conversations",
    __name__,
    url_prefix="/api/agents/conversations",
    abp_tags=[tag],
)


class ConversationPath(BaseModel):
    conv_id: str = Field(..., description="Conversation ID")


@agent_conversations_bp.get("/<conv_id>/stream")
def stream_conversation(path: ConversationPath):
    """SSE endpoint for real-time conversation streaming."""

    def generate():
        for event in AgentConversationService.subscribe(path.conv_id):
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
