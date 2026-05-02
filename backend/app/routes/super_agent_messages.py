"""SuperAgent message CRUD migrated to Litestar :20002 in wave 76.

Only /admin/super-agents/{id}/messages/stream stays on Flask.
"""

from flask import Response
from flask_openapi3 import APIBlueprint, Tag

from .super_agents import SuperAgentPath

tag = Tag(name="super-agent-messages", description="Message streaming (Flask leftover)")
super_agent_messages_bp = APIBlueprint(
    "super_agent_messages",
    __name__,
    url_prefix="/admin/super-agents",
    abp_tags=[tag],
)


@super_agent_messages_bp.get("/<super_agent_id>/messages/stream")
def stream_messages(path: SuperAgentPath):
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
