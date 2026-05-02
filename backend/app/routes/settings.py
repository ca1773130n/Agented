"""Migrated to Litestar :20002 in wave 64."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="settings", description="Migrated to Litestar")
settings_bp = APIBlueprint("settings_bp", __name__, url_prefix="/api/settings", abp_tags=[tag])
