"""Migrated to Litestar :20002 (waves 72 + 78)."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="command-conversations", description="Migrated to Litestar")
command_conversations_bp = APIBlueprint(
    "command_conversations",
    __name__,
    url_prefix="/api/commands/conversations",
    abp_tags=[tag],
)
