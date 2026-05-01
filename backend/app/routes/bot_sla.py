"""Migrated to Litestar :20002 in wave 48 — see app_litestar/routes/misc.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="bot-sla", description="Migrated to Litestar")
bot_sla_bp = APIBlueprint("bot_sla", __name__, url_prefix="/admin", abp_tags=[tag])
