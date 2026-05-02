"""Migrated to Litestar :20002 in wave 61."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="plugins", description="Migrated to Litestar")
plugins_bp = APIBlueprint("plugins_bp", __name__, url_prefix="/admin/plugins", abp_tags=[tag])
