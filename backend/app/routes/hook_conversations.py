"""Hook conversation API endpoints for interactive hook creation."""

from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..services.hook_conversation_service import HookConversationService

tag = Tag(name="hook-conversations", description="Hook creation conversations")
hook_conversations_bp = APIBlueprint(
    "hook_conversations", __name__, url_prefix="/api/hooks/conversations", abp_tags=[tag]
)


class ConversationPath(BaseModel):
    conv_id: str = Field(..., description="Conversation ID")


@hook_conversations_bp.get("/")
def list_conversations():
    """List active hook creation conversations."""
    result, status = HookConversationService.list_conversations()
    return result, status


@hook_conversations_bp.post("/start")
def start_conversation():
    """Start a new hook creation conversation."""
    result, status = HookConversationService.start_conversation()
    return result, status


@hook_conversations_bp.get("/<conv_id>")
def get_conversation(path: ConversationPath):
    """Get conversation details and messages."""
    result, status = HookConversationService.get_conversation(path.conv_id)
    return result, status


@hook_conversations_bp.post("/<conv_id>/message")
def send_message(path: ConversationPath):
    """Send a message to the conversation."""
    data = request.get_json()
    if not data or not data.get("message"):
        return {"error": "message is required"}, HTTPStatus.BAD_REQUEST
    result, status = HookConversationService.send_message(
        path.conv_id,
        data["message"],
        backend=data.get("backend"),
        account_id=data.get("account_id"),
        model=data.get("model"),
    )
    return result, status


@hook_conversations_bp.get("/<conv_id>/stream")
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
        for event in HookConversationService.subscribe(path.conv_id):
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


@hook_conversations_bp.post("/<conv_id>/finalize")
def finalize_hook(path: ConversationPath):
    """Finalize the conversation and create the hook."""
    result, status = HookConversationService._finalize_entity(path.conv_id)
    return result, status


@hook_conversations_bp.post("/<conv_id>/resume")
def resume_conversation(path: ConversationPath):
    """Resume a hook conversation from the database."""
    result, status = HookConversationService.resume_conversation(path.conv_id)
    return result, status


@hook_conversations_bp.post("/<conv_id>/abandon")
def abandon_conversation(path: ConversationPath):
    """Abandon a conversation without creating a hook."""
    result, status = HookConversationService.abandon_conversation(path.conv_id)
    return result, status
