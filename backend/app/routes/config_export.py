"""Migrated to Litestar :20002 in wave 67 — see app_litestar/routes/leaf_crud_c.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="config", description="Migrated to Litestar")
config_export_bp = APIBlueprint("config_export", __name__, url_prefix="/admin", abp_tags=[tag])
