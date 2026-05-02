"""Migrated to Litestar :20002 in wave 70 — see app_litestar/routes/leaf_crud_f.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="replay", description="Migrated to Litestar")
replay_bp = APIBlueprint("replay", __name__, url_prefix="/admin", abp_tags=[tag])
