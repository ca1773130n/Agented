"""Migrated to Litestar :20002 in wave 64."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="retention", description="Migrated to Litestar")
retention_bp = APIBlueprint("retention_bp", __name__, url_prefix="/admin/retention-policies", abp_tags=[tag])
