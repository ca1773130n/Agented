"""Migrated to Litestar :20002 (waves 74 + 78)."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="grd", description="Migrated to Litestar")
grd_bp = APIBlueprint("grd", __name__, url_prefix="/api/projects", abp_tags=[tag])
