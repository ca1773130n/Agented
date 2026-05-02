"""Migrated to Litestar :20002 in wave 69 — see app_litestar/routes/leaf_crud_e.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="bot_pipes", description="Migrated to Litestar")
bot_pipes_bp = APIBlueprint(
    "bot_pipes", __name__, url_prefix="/admin/bot-pipes", abp_tags=[tag]
)
