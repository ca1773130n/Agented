"""Migrated to Litestar :20002 in wave 70 — see app_litestar/routes/leaf_crud_f.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="conversation-branches", description="Migrated to Litestar")
conversation_branches_bp = APIBlueprint(
    "conversation_branches", __name__, url_prefix="/admin", abp_tags=[tag]
)
