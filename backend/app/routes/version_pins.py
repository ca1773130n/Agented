"""Migrated to Litestar :20002 in wave 64."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="version_pins", description="Migrated to Litestar")
version_pins_bp = APIBlueprint("version_pins_bp", __name__, url_prefix="/admin/version-pins", abp_tags=[tag])
