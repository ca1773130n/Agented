"""Migrated to Litestar :20002 in wave 60."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="agents", description="Migrated to Litestar")
agents_bp = APIBlueprint("agents_bp", __name__, url_prefix="/admin/agents", abp_tags=[tag])
