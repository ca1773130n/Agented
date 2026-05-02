"""Migrated to Litestar :20002 (waves 71 + 78)."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="agent-conversations", description="Migrated to Litestar")
agent_conversations_bp = APIBlueprint(
    "agent_conversations",
    __name__,
    url_prefix="/api/agents/conversations",
    abp_tags=[tag],
)
