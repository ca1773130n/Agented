"""Migrated to Litestar :20002 (waves 72 + 78)."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="hook-conversations", description="Migrated to Litestar")
hook_conversations_bp = APIBlueprint(
    "hook_conversations",
    __name__,
    url_prefix="/api/hooks/conversations",
    abp_tags=[tag],
)
