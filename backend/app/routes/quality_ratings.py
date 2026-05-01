"""Migrated to Litestar :20002 in wave 50."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="quality_ratings", description="Migrated to Litestar")
quality_ratings_bp = APIBlueprint("quality_ratings", __name__, url_prefix="/admin/quality", abp_tags=[tag])
