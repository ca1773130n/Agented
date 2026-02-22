"""Plugin conversation API endpoints for interactive plugin creation."""

from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..services.plugin_conversation_service import PluginConversationService

tag = Tag(name="plugin-conversations", description="Plugin creation conversations")
plugin_conversations_bp = APIBlueprint(
    "plugin_conversations", __name__, url_prefix="/api/plugins/conversations", abp_tags=[tag]
)


class ConversationPath(BaseModel):
    conv_id: str = Field(..., description="Conversation ID")


@plugin_conversations_bp.post("/start")
def start_conversation():
    """Start a new plugin creation conversation."""
    result, status = PluginConversationService.start_conversation()
    return result, status


@plugin_conversations_bp.get("/<conv_id>")
def get_conversation(path: ConversationPath):
    """Get conversation details and messages."""
    result, status = PluginConversationService.get_conversation(path.conv_id)
    return result, status


@plugin_conversations_bp.post("/<conv_id>/message")
def send_message(path: ConversationPath):
    """Send a message to the conversation."""
    data = request.get_json()
    if not data or not data.get("message"):
        return {"error": "message is required"}, HTTPStatus.BAD_REQUEST
    result, status = PluginConversationService.send_message(
        path.conv_id,
        data["message"],
        backend=data.get("backend"),
        account_id=data.get("account_id"),
        model=data.get("model"),
    )
    return result, status


@plugin_conversations_bp.get("/<conv_id>/stream")
def stream_conversation(path: ConversationPath):
    """SSE endpoint for real-time conversation streaming.

    Returns Server-Sent Events with the following event types:
    - message: A conversation message
    - user_message: User message sent
    - response_start: Claude is generating a response
    - response_chunk: A chunk of Claude's response
    - response_complete: Claude's response is complete
    - error: An error occurred
    """

    def generate():
        for event in PluginConversationService.subscribe(path.conv_id):
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


@plugin_conversations_bp.post("/<conv_id>/finalize")
def finalize_plugin(path: ConversationPath):
    """Finalize the conversation and create the plugin."""
    result, status = PluginConversationService.finalize_plugin(path.conv_id)
    return result, status


@plugin_conversations_bp.post("/<conv_id>/abandon")
def abandon_conversation(path: ConversationPath):
    """Abandon a conversation without creating a plugin."""
    result, status = PluginConversationService.abandon_conversation(path.conv_id)
    return result, status
