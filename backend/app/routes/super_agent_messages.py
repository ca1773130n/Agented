"""SuperAgent messaging API endpoints."""

from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from .super_agents import SuperAgentPath

tag = Tag(name="super-agent-messages", description="SuperAgent messaging operations")
super_agent_messages_bp = APIBlueprint(
    "super_agent_messages", __name__, url_prefix="/admin/super-agents", abp_tags=[tag]
)


class MessagePath(BaseModel):
    super_agent_id: str = Field(..., description="SuperAgent ID")
    message_id: str = Field(..., description="Message ID")


@super_agent_messages_bp.post("/<super_agent_id>/messages")
def send_agent_message(path: SuperAgentPath):
    """Send a message from this SuperAgent to another agent or broadcast."""
    from ..services.agent_message_bus_service import AgentMessageBusService

    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    content = data.get("content", "").strip()
    if not content:
        return error_response("BAD_REQUEST", "content is required", HTTPStatus.BAD_REQUEST)

    # Resolve psa- instance IDs to template SA ID
    sa_id = path.super_agent_id
    if sa_id.startswith("psa-"):
        from ..db.project_sa_instances import get_project_sa_instance

        instance = get_project_sa_instance(sa_id)
        if not instance:
            return error_response("NOT_FOUND", "Instance not found", HTTPStatus.NOT_FOUND)
        sa_id = instance["template_sa_id"]

    msg_id = AgentMessageBusService.send_message(
        from_agent_id=sa_id,
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


@super_agent_messages_bp.get("/<super_agent_id>/messages/inbox")
def get_inbox(path: SuperAgentPath):
    """List inbox messages for this SuperAgent."""
    from ..db.messages import get_inbox_messages

    status_filter = request.args.get("status")
    messages = get_inbox_messages(path.super_agent_id, status=status_filter)
    return {"messages": messages}, HTTPStatus.OK


@super_agent_messages_bp.get("/<super_agent_id>/messages/outbox")
def get_outbox(path: SuperAgentPath):
    """List outbox messages from this SuperAgent."""
    from ..db.messages import get_outbox_messages

    messages = get_outbox_messages(path.super_agent_id)
    return {"messages": messages}, HTTPStatus.OK


@super_agent_messages_bp.post("/<super_agent_id>/messages/<message_id>/read")
def mark_message_read(path: MessagePath):
    """Mark a message as read."""
    from ..db.messages import update_message_status

    if not update_message_status(path.message_id, "read"):
        return error_response("NOT_FOUND", "Message not found", HTTPStatus.NOT_FOUND)

    return {"message": "Message marked as read"}, HTTPStatus.OK


@super_agent_messages_bp.get("/<super_agent_id>/messages/stream")
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
