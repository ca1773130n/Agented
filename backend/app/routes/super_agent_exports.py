"""Migrated to Litestar :20002 in wave 63."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="super_agent_exports", description="Migrated to Litestar")
super_agent_exports_bp = APIBlueprint("super_agent_exports_bp", __name__, url_prefix="/admin/super-agent-exports", abp_tags=[tag])
