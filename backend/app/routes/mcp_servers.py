"""Migrated to Litestar :20002 in wave 56 — see app_litestar/routes/mcp_servers.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="mcp-servers", description="Migrated to Litestar")
mcp_servers_bp = APIBlueprint("mcp_servers", __name__, url_prefix="/admin/mcp-servers", abp_tags=[tag])

# Secondary blueprint stub (project-scoped MCP routes)
project_mcp_tag = Tag(name="project-mcp", description="Migrated to Litestar")
project_mcp_bp = APIBlueprint(
    "project_mcp", __name__, url_prefix="/admin/projects", abp_tags=[project_mcp_tag],
)
