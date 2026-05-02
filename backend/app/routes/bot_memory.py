"""Migrated to Litestar :20002 in wave 65 — see app_litestar/routes/leaf_crud_a.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="bot-memory", description="Migrated to Litestar")
bot_memory_bp = APIBlueprint(
    "bot_memory", __name__, url_prefix="/admin", abp_tags=[tag]
)
