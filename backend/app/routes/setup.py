"""Migrated to Litestar :20002 (waves 76 + 78)."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="setup", description="Migrated to Litestar")
setup_bp = APIBlueprint("setup", __name__, url_prefix="/api/setup", abp_tags=[tag])
