"""Migrated to Litestar :20002 (waves 72 + 78)."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="plugin-conversations", description="Migrated to Litestar")
plugin_conversations_bp = APIBlueprint(
    "plugin_conversations",
    __name__,
    url_prefix="/api/plugins/conversations",
    abp_tags=[tag],
)
