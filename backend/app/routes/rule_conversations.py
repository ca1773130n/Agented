"""Rule conversation API endpoints for interactive rule creation."""

from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..services.rule_conversation_service import RuleConversationService

tag = Tag(name="rule-conversations", description="Rule creation conversations")
rule_conversations_bp = APIBlueprint(
    "rule_conversations", __name__, url_prefix="/api/rules/conversations", abp_tags=[tag]
)


class ConversationPath(BaseModel):
    conv_id: str = Field(..., description="Conversation ID")


@rule_conversations_bp.get("/")
def list_conversations():
    """List active rule creation conversations."""
    result, status = RuleConversationService.list_conversations()
    return result, status


@rule_conversations_bp.post("/start")
def start_conversation():
    """Start a new rule creation conversation."""
    result, status = RuleConversationService.start_conversation()
    return result, status


@rule_conversations_bp.get("/<conv_id>")
def get_conversation(path: ConversationPath):
    """Get conversation details and messages."""
    result, status = RuleConversationService.get_conversation(path.conv_id)
    return result, status


@rule_conversations_bp.post("/<conv_id>/message")
def send_message(path: ConversationPath):
    """Send a message to the conversation."""
    data = request.get_json()
    if not data or not data.get("message"):
        return {"error": "message is required"}, HTTPStatus.BAD_REQUEST
    result, status = RuleConversationService.send_message(
        path.conv_id,
        data["message"],
        backend=data.get("backend"),
        account_id=data.get("account_id"),
        model=data.get("model"),
    )
    return result, status


@rule_conversations_bp.get("/<conv_id>/stream")
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
        for event in RuleConversationService.subscribe(path.conv_id):
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


@rule_conversations_bp.post("/<conv_id>/finalize")
def finalize_rule(path: ConversationPath):
    """Finalize the conversation and create the rule."""
    result, status = RuleConversationService._finalize_entity(path.conv_id)
    return result, status


@rule_conversations_bp.post("/<conv_id>/resume")
def resume_conversation(path: ConversationPath):
    """Resume a rule conversation from the database."""
    result, status = RuleConversationService.resume_conversation(path.conv_id)
    return result, status


@rule_conversations_bp.post("/<conv_id>/abandon")
def abandon_conversation(path: ConversationPath):
    """Abandon a conversation without creating a rule."""
    result, status = RuleConversationService.abandon_conversation(path.conv_id)
    return result, status
