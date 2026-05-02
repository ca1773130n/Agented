"""Migrated to Litestar :20002 (waves 76 + 78)."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="super-agent-chat", description="Migrated to Litestar")
super_agent_chat_bp = APIBlueprint(
    "super_agent_chat",
    __name__,
    url_prefix="/admin/super-agents",
    abp_tags=[tag],
)
