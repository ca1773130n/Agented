"""Migrated to Litestar :20002 in wave 50."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="Bot Templates", description="Migrated to Litestar")
bot_templates_bp = APIBlueprint("bot_templates", __name__, url_prefix="/admin/bot-templates", abp_tags=[tag])
