"""Migrated to Litestar :20002 in wave 57."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="skill_conversations", description="Migrated to Litestar")
skill_conversations_bp = APIBlueprint("skill_conversations_bp", __name__, url_prefix="/api/skills/conversations", abp_tags=[tag])
