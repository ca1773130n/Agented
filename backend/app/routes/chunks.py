"""Migrated to Litestar :20002 in wave 76 — see app_litestar/routes/leaf_crud_i.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="chunks", description="Migrated to Litestar")
chunks_bp = APIBlueprint("chunks", __name__, url_prefix="/admin", abp_tags=[tag])
