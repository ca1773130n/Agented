"""Migrated to Litestar :20002 in wave 61."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="hooks", description="Migrated to Litestar")
hooks_bp = APIBlueprint("hooks_bp", __name__, url_prefix="/admin/hooks", abp_tags=[tag])
