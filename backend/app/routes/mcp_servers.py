"""MCP server configuration management API endpoints."""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag

from ..database import (
    add_mcp_server,
    assign_mcp_to_project,
    count_mcp_servers,
    delete_mcp_server,
    get_all_mcp_servers,
    get_mcp_server,
    get_project,
    get_project_mcp_servers,
    unassign_mcp_from_project,
    update_mcp_server,
    update_project_mcp_assignment,
)
from ..models.common import PaginationQuery
from ..models.mcp_server import (
    AssignMcpToProjectRequest,
    CreateMcpServerRequest,
    McpServerIdPath,
    ProjectMcpPath,
    SyncProjectPath,
    UpdateMcpServerRequest,
    UpdateProjectMcpAssignmentRequest,
)
from ..services.mcp_sync_service import McpSyncService

tag = Tag(name="mcp-servers", description="MCP server configuration management")
mcp_servers_bp = APIBlueprint(
    "mcp_servers", __name__, url_prefix="/admin/mcp-servers", abp_tags=[tag]
)

# Secondary blueprint for project-scoped MCP routes (different url_prefix)
project_mcp_tag = Tag(name="project-mcp", description="Project MCP server assignment")
project_mcp_bp = APIBlueprint(
    "project_mcp",
    __name__,
    url_prefix="/admin/projects",
    abp_tags=[project_mcp_tag],
)


# =============================================================================
# MCP Server CRUD
# =============================================================================


@mcp_servers_bp.get("/")
def list_mcp_servers(query: PaginationQuery):
    """List all MCP servers (presets + custom) with optional pagination."""
    total_count = count_mcp_servers()
    servers = get_all_mcp_servers(limit=query.limit, offset=query.offset or 0)
    return {"servers": servers, "total_count": total_count}, HTTPStatus.OK


@mcp_servers_bp.get("/<server_id>")
def get_mcp_server_endpoint(path: McpServerIdPath):
    """Get a single MCP server by ID."""
    server = get_mcp_server(path.server_id)
    if not server:
        return {"error": "MCP server not found"}, HTTPStatus.NOT_FOUND
    return server, HTTPStatus.OK


@mcp_servers_bp.post("/")
def create_mcp_server(body: CreateMcpServerRequest):
    """Create a custom MCP server. Presets cannot be created via API."""
    server_id = add_mcp_server(
        name=body.name,
        description=body.description,
        server_type=body.server_type or "stdio",
        command=body.command,
        args=body.args,
        env_json=body.env_json,
        url=body.url,
        display_name=body.display_name,
        category=body.category or "general",
        headers_json=body.headers_json,
        timeout_ms=body.timeout_ms or 30000,
        is_preset=0,  # Never allow creating presets via API
        icon=body.icon,
        documentation_url=body.documentation_url,
        npm_package=body.npm_package,
    )
    if not server_id:
        return {"error": "Failed to create MCP server (duplicate name?)"}, HTTPStatus.BAD_REQUEST
    return {"id": server_id}, HTTPStatus.CREATED


@mcp_servers_bp.put("/<server_id>")
def update_mcp_server_endpoint(path: McpServerIdPath, body: UpdateMcpServerRequest):
    """Update an MCP server. Cannot change preset name or is_preset flag."""
    server = get_mcp_server(path.server_id)
    if not server:
        return {"error": "MCP server not found"}, HTTPStatus.NOT_FOUND

    # Build update kwargs, filtering out None values
    updates = {}
    for field in (
        "name",
        "description",
        "server_type",
        "command",
        "args",
        "env_json",
        "url",
        "enabled",
        "display_name",
        "category",
        "headers_json",
        "timeout_ms",
        "icon",
        "documentation_url",
        "npm_package",
    ):
        value = getattr(body, field, None)
        if value is not None:
            updates[field] = value

    # Prevent changing preset name
    if server.get("is_preset") and "name" in updates:
        return {"error": "Cannot change name of a preset MCP server"}, HTTPStatus.BAD_REQUEST

    if not updates:
        return {"error": "No fields to update"}, HTTPStatus.BAD_REQUEST

    update_mcp_server(path.server_id, **updates)
    updated = get_mcp_server(path.server_id)
    return updated, HTTPStatus.OK


@mcp_servers_bp.delete("/<server_id>")
def delete_mcp_server_endpoint(path: McpServerIdPath):
    """Delete an MCP server. Presets cannot be deleted."""
    server = get_mcp_server(path.server_id)
    if not server:
        return {"error": "MCP server not found"}, HTTPStatus.NOT_FOUND

    if server.get("is_preset"):
        return {"error": "Cannot delete a preset MCP server"}, HTTPStatus.BAD_REQUEST

    delete_mcp_server(path.server_id)
    return {"message": "Deleted"}, HTTPStatus.OK


# =============================================================================
# MCP Sync routes
# =============================================================================


@mcp_servers_bp.post("/sync/<project_id>")
def sync_mcp_to_project(path: SyncProjectPath):
    """Sync MCP config to project's .mcp.json file."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    local_path = project.get("local_path")
    if not local_path:
        return {
            "error": "Project has no local_path configured. "
            "Set a local path in project settings before syncing."
        }, HTTPStatus.BAD_REQUEST

    result = McpSyncService.sync_project(path.project_id, local_path, dry_run=False)
    if "error" in result:
        return result, HTTPStatus.BAD_REQUEST
    return result, HTTPStatus.OK


@mcp_servers_bp.get("/sync/<project_id>/preview")
def preview_mcp_sync(path: SyncProjectPath):
    """Preview (dry-run) sync: show what would change in .mcp.json."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    local_path = project.get("local_path")
    if not local_path:
        return {
            "error": "Project has no local_path configured. "
            "Set a local path in project settings before syncing."
        }, HTTPStatus.BAD_REQUEST

    result = McpSyncService.sync_project(path.project_id, local_path, dry_run=True)
    if "error" in result:
        return result, HTTPStatus.BAD_REQUEST
    return result, HTTPStatus.OK


# =============================================================================
# Project MCP Server Assignment
# =============================================================================


@project_mcp_bp.get("/<project_id>/mcp-servers")
def list_project_mcp_servers(path: SyncProjectPath):
    """List MCP servers assigned to a project."""
    servers = get_project_mcp_servers(path.project_id)
    return {"servers": servers}, HTTPStatus.OK


@project_mcp_bp.post("/<project_id>/mcp-servers/<server_id>")
def assign_mcp_to_project_endpoint(path: ProjectMcpPath, body: AssignMcpToProjectRequest):
    """Assign an MCP server to a project."""
    result = assign_mcp_to_project(
        project_id=path.project_id,
        mcp_server_id=path.server_id,
        env_overrides_json=body.env_overrides_json if body else None,
    )
    if result is None:
        return {"error": "Assignment already exists or invalid IDs"}, HTTPStatus.BAD_REQUEST
    return {"message": "Assigned"}, HTTPStatus.CREATED


@project_mcp_bp.put("/<project_id>/mcp-servers/<server_id>")
def update_project_mcp_assignment_endpoint(
    path: ProjectMcpPath, body: UpdateProjectMcpAssignmentRequest
):
    """Update a project MCP assignment (enable/disable, env overrides)."""
    success = update_project_mcp_assignment(
        project_id=path.project_id,
        mcp_server_id=path.server_id,
        enabled=body.enabled if body else None,
        env_overrides_json=body.env_overrides_json if body else None,
    )
    if not success:
        return {"error": "Assignment not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Updated"}, HTTPStatus.OK


@project_mcp_bp.delete("/<project_id>/mcp-servers/<server_id>")
def unassign_mcp_from_project_endpoint(path: ProjectMcpPath):
    """Unassign an MCP server from a project."""
    success = unassign_mcp_from_project(project_id=path.project_id, mcp_server_id=path.server_id)
    if not success:
        return {"error": "Assignment not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Unassigned"}, HTTPStatus.OK
