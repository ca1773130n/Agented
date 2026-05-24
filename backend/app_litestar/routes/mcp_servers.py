"""MCP servers + project-MCP assignments (track A, wave 56)."""

from __future__ import annotations

from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)
from msgspec import Struct

from app.database import (
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
from app.database import create_mcp_server as db_create_mcp_server
from app.db.owned_entities import get_for_user
from app.services.mcp_sync_service import McpSyncService
from app.services.project_workspace_service import ProjectWorkspaceService

from ..auth import Caller


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateMcpBody(Struct, kw_only=True):
    name: str = ""
    description: Optional[str] = None
    server_type: str = "stdio"
    command: Optional[str] = None
    args: Optional[Any] = None
    env_json: Optional[str] = None
    url: Optional[str] = None
    display_name: Optional[str] = None
    category: str = "general"
    headers_json: Optional[str] = None
    timeout_ms: int = 30000
    icon: Optional[str] = None
    documentation_url: Optional[str] = None
    npm_package: Optional[str] = None


class UpdateMcpBody(Struct, kw_only=True):
    name: Optional[str] = None
    description: Optional[str] = None
    server_type: Optional[str] = None
    command: Optional[str] = None
    args: Optional[Any] = None
    env_json: Optional[str] = None
    url: Optional[str] = None
    enabled: Optional[int] = None
    display_name: Optional[str] = None
    category: Optional[str] = None
    headers_json: Optional[str] = None
    timeout_ms: Optional[int] = None
    icon: Optional[str] = None
    documentation_url: Optional[str] = None
    npm_package: Optional[str] = None


class AssignMcpBody(Struct):
    env_overrides_json: Optional[str] = None


class UpdateAssignmentBody(Struct):
    enabled: Optional[int] = None
    env_overrides_json: Optional[str] = None


# ---------------------------------------------------------------------------
# /admin/mcp-servers/* CRUD + sync
# ---------------------------------------------------------------------------


@get("/", sync_to_thread=False)
def list_mcp_servers(
    caller: Caller, limit: Optional[int] = None, offset: Optional[int] = None
) -> dict[str, Any]:
    if caller.user_id:
        rows = get_for_user(
            "mcp_servers", caller.user_id, limit=limit, offset=offset or 0
        )
        return {"servers": rows, "total_count": len(rows)}
    return {
        "servers": get_all_mcp_servers(limit=limit, offset=offset or 0),
        "total_count": count_mcp_servers(),
    }


@get("/{server_id:str}", sync_to_thread=False)
def get_mcp_server_endpoint(server_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    server = get_mcp_server(server_id)
    if not server:
        raise NotFoundException(detail="MCP server not found")
    return server


@post("/", sync_to_thread=False)
def create_mcp_server_endpoint(
    data: CreateMcpBody, caller: Caller
) -> dict[str, Any]:
    del caller
    if not data.name:
        raise ClientException(detail="name is required")
    server_id = db_create_mcp_server(
        name=data.name,
        description=data.description,
        server_type=data.server_type,
        command=data.command,
        args=data.args,
        env_json=data.env_json,
        url=data.url,
        display_name=data.display_name,
        category=data.category,
        headers_json=data.headers_json,
        timeout_ms=data.timeout_ms,
        is_preset=0,
        icon=data.icon,
        documentation_url=data.documentation_url,
        npm_package=data.npm_package,
    )
    if not server_id:
        raise ClientException(detail="Failed to create MCP server (duplicate name?)")
    return {"id": server_id}


@put("/{server_id:str}", sync_to_thread=False)
def update_mcp_server_endpoint(
    server_id: str, data: UpdateMcpBody, caller: Caller
) -> dict[str, Any]:
    del caller
    server = get_mcp_server(server_id)
    if not server:
        raise NotFoundException(detail="MCP server not found")

    updates: dict[str, Any] = {}
    for f in (
        "name", "description", "server_type", "command", "args", "env_json",
        "url", "enabled", "display_name", "category", "headers_json",
        "timeout_ms", "icon", "documentation_url", "npm_package",
    ):
        v = getattr(data, f, None)
        if v is not None:
            updates[f] = v

    if server.get("is_preset") and "name" in updates:
        raise ClientException(detail="Cannot change name of a preset MCP server")
    if not updates:
        raise ClientException(detail="No fields to update")

    update_mcp_server(server_id, **updates)
    return get_mcp_server(server_id)


@delete("/{server_id:str}", status_code=200, sync_to_thread=False)
def delete_mcp_server_endpoint(server_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    server = get_mcp_server(server_id)
    if not server:
        raise NotFoundException(detail="MCP server not found")
    if server.get("is_preset"):
        raise ClientException(detail="Cannot delete a preset MCP server")
    delete_mcp_server(server_id)
    return {"message": "Deleted"}


@post("/{server_id:str}/test", sync_to_thread=False)
def test_mcp_server(server_id: str, caller: Caller) -> dict[str, Any]:
    """Probe an MCP server's reachability without launching it."""
    del caller
    server = get_mcp_server(server_id)
    if not server:
        raise NotFoundException(detail="MCP server not found")
    return McpSyncService.test_connection(server)


@post("/sync/{project_id:str}", sync_to_thread=False)
def sync_mcp_to_project(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    if not get_project(project_id):
        raise NotFoundException(detail="Project not found")
    try:
        local_path = ProjectWorkspaceService.resolve_working_directory(project_id)
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None
    result = McpSyncService.sync_project(project_id, local_path, dry_run=False)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


@get("/sync/{project_id:str}/preview", sync_to_thread=False)
def preview_mcp_sync(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    if not get_project(project_id):
        raise NotFoundException(detail="Project not found")
    try:
        local_path = ProjectWorkspaceService.resolve_working_directory(project_id)
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None
    result = McpSyncService.sync_project(project_id, local_path, dry_run=True)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result)
    return result


mcp_servers_router = Router(
    path="/admin/mcp-servers",
    route_handlers=[
        list_mcp_servers,
        get_mcp_server_endpoint,
        create_mcp_server_endpoint,
        update_mcp_server_endpoint,
        delete_mcp_server_endpoint,
        test_mcp_server,
        sync_mcp_to_project,
        preview_mcp_sync,
    ],
)


# ---------------------------------------------------------------------------
# /admin/projects/{id}/mcp-servers/* — project assignments
# ---------------------------------------------------------------------------


@get("/{project_id:str}/mcp-servers", sync_to_thread=False)
def list_project_mcp_servers(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return {"servers": get_project_mcp_servers(project_id)}


@post("/{project_id:str}/mcp-servers/{server_id:str}", sync_to_thread=False)
def assign_mcp(
    project_id: str, server_id: str, data: AssignMcpBody, caller: Caller
) -> dict[str, Any]:
    del caller
    result = assign_mcp_to_project(
        project_id=project_id,
        mcp_server_id=server_id,
        env_overrides_json=data.env_overrides_json,
    )
    if result is None:
        raise ClientException(detail="Assignment already exists or invalid IDs")
    return {"message": "Assigned"}


@put("/{project_id:str}/mcp-servers/{server_id:str}", sync_to_thread=False)
def update_project_mcp_assignment_endpoint(
    project_id: str, server_id: str, data: UpdateAssignmentBody, caller: Caller
) -> dict[str, Any]:
    del caller
    success = update_project_mcp_assignment(
        project_id=project_id,
        mcp_server_id=server_id,
        enabled=data.enabled,
        env_overrides_json=data.env_overrides_json,
    )
    if not success:
        raise NotFoundException(detail="Assignment not found")
    return {"message": "Updated"}


@delete(
    "/{project_id:str}/mcp-servers/{server_id:str}",
    status_code=200,
    sync_to_thread=False,
)
def unassign_mcp(
    project_id: str, server_id: str, caller: Caller
) -> dict[str, Any]:
    del caller
    success = unassign_mcp_from_project(
        project_id=project_id, mcp_server_id=server_id
    )
    if not success:
        raise NotFoundException(detail="Assignment not found")
    return {"message": "Unassigned"}


project_mcp_router = Router(
    path="/admin/projects",
    route_handlers=[
        list_project_mcp_servers,
        assign_mcp,
        update_project_mcp_assignment_endpoint,
        unassign_mcp,
    ],
)
