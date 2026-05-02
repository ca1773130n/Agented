"""Migrated to Litestar :20002 (waves 76 + 78)."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="super-agent-messages", description="Migrated to Litestar")
super_agent_messages_bp = APIBlueprint(
    "super_agent_messages",
    __name__,
    url_prefix="/admin/super-agents",
    abp_tags=[tag],
)
