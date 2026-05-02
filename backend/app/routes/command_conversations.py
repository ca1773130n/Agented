"""Command conversation CRUD migrated to Litestar :20002 in wave 72.

Only the SSE `/stream` route stays on Flask until the streaming wave.
"""

from flask import Response
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..services.command_conversation_service import CommandConversationService

tag = Tag(
    name="command-conversations", description="Command conversation streaming (Flask leftover)"
)
command_conversations_bp = APIBlueprint(
    "command_conversations",
    __name__,
    url_prefix="/api/commands/conversations",
    abp_tags=[tag],
)


class ConversationPath(BaseModel):
    conv_id: str = Field(..., description="Conversation ID")


@command_conversations_bp.get("/<conv_id>/stream")
def stream_conversation(path: ConversationPath):
    def generate():
        for event in CommandConversationService.subscribe(path.conv_id):
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
