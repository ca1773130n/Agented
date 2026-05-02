"""Migrated to Litestar :20002 in wave 63."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="super_agent_sessions", description="Migrated to Litestar")
super_agent_sessions_bp = APIBlueprint("super_agent_sessions_bp", __name__, url_prefix="/admin/super-agents", abp_tags=[tag])
