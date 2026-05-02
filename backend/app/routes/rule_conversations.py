"""Migrated to Litestar :20002 (waves 72 + 78)."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="rule-conversations", description="Migrated to Litestar")
rule_conversations_bp = APIBlueprint(
    "rule_conversations",
    __name__,
    url_prefix="/api/rules/conversations",
    abp_tags=[tag],
)
