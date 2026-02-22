"""MCP server and execution type handler Pydantic models."""

from typing import List, Optional

from pydantic import BaseModel, Field

# --- Entity models ---


class McpServer(BaseModel):
    """MCP server entity -- a registered MCP tool server."""

    id: str = Field(..., pattern=r"^mcp-[a-z0-9]+$", examples=["mcp-abc123"])
    name: str
    description: Optional[str] = None
    server_type: str = "stdio"
    command: Optional[str] = None
    args: Optional[str] = None
    env_json: Optional[str] = None
    url: Optional[str] = None
    enabled: int = 1
    display_name: Optional[str] = None
    category: str = "general"
    headers_json: Optional[str] = None
    timeout_ms: int = 30000
    is_preset: int = 0
    icon: Optional[str] = None
    documentation_url: Optional[str] = None
    npm_package: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProjectMcpServer(BaseModel):
    """Junction entity -- MCP server assigned to a project."""

    id: int
    project_id: str
    mcp_server_id: str
    config_override: Optional[str] = None
    enabled: int = 1
    env_overrides_json: Optional[str] = None
    created_at: Optional[str] = None


class ProjectMcpServerDetail(BaseModel):
    """MCP server details with project assignment fields (JOINed result shape)."""

    # Assignment fields from project_mcp_servers
    id: int
    project_id: str
    mcp_server_id: str
    config_override: Optional[str] = None
    assignment_enabled: int = 1
    env_overrides_json: Optional[str] = None
    created_at: Optional[str] = None
    # Server fields from mcp_servers (via JOIN)
    server_name: str
    server_description: Optional[str] = None
    server_type: str = "stdio"
    command: Optional[str] = None
    args: Optional[str] = None
    env_json: Optional[str] = None
    url: Optional[str] = None
    enabled: int = 1
    display_name: Optional[str] = None
    category: str = "general"
    headers_json: Optional[str] = None
    timeout_ms: int = 30000
    is_preset: int = 0
    icon: Optional[str] = None
    documentation_url: Optional[str] = None
    npm_package: Optional[str] = None


class ExecutionTypeHandler(BaseModel):
    """Execution type handler entity -- maps execution types to handler configs."""

    id: int
    execution_type: str
    handler_type: str
    handler_config: Optional[str] = None
    priority: int = 0
    enabled: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# --- List response models ---


class McpServerListResponse(BaseModel):
    """Response for listing MCP servers."""

    servers: List[McpServer]


class ProjectMcpServerListResponse(BaseModel):
    """Response for listing MCP servers assigned to a project."""

    servers: List[ProjectMcpServerDetail]


class ExecutionTypeHandlerListResponse(BaseModel):
    """Response for listing execution type handlers."""

    handlers: List[ExecutionTypeHandler]


# --- Create request models ---


class CreateMcpServerRequest(BaseModel):
    """Request body for creating an MCP server."""

    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    server_type: Optional[str] = "stdio"
    command: Optional[str] = None
    args: Optional[str] = None
    env_json: Optional[str] = None
    url: Optional[str] = None
    display_name: Optional[str] = None
    category: Optional[str] = "general"
    headers_json: Optional[str] = None
    timeout_ms: Optional[int] = 30000
    icon: Optional[str] = None
    documentation_url: Optional[str] = None
    npm_package: Optional[str] = None


class CreateExecutionTypeHandlerRequest(BaseModel):
    """Request body for creating an execution type handler."""

    execution_type: str = Field(..., min_length=1)
    handler_type: str = Field(..., min_length=1)
    handler_config: Optional[str] = None
    priority: Optional[int] = 0


# --- Update request models ---


class UpdateMcpServerRequest(BaseModel):
    """Request body for updating an MCP server."""

    name: Optional[str] = None
    description: Optional[str] = None
    server_type: Optional[str] = None
    command: Optional[str] = None
    args: Optional[str] = None
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


class UpdateExecutionTypeHandlerRequest(BaseModel):
    """Request body for updating an execution type handler."""

    handler_config: Optional[str] = None
    priority: Optional[int] = None
    enabled: Optional[int] = None


# --- Assignment request models ---


class AssignMcpToProjectRequest(BaseModel):
    """Request body for assigning an MCP server to a project."""

    env_overrides_json: Optional[str] = None


class UpdateProjectMcpAssignmentRequest(BaseModel):
    """Request body for updating a project MCP assignment."""

    enabled: Optional[int] = None
    env_overrides_json: Optional[str] = None


# --- Path parameter models ---


class McpServerIdPath(BaseModel):
    """Path parameter for MCP server ID."""

    server_id: str = Field(..., description="MCP server ID")


class ProjectMcpPath(BaseModel):
    """Path parameters for project MCP server operations."""

    project_id: str = Field(..., description="Project ID")
    server_id: str = Field(..., description="MCP server ID")


class SyncProjectPath(BaseModel):
    """Path parameter for sync operations."""

    project_id: str = Field(..., description="Project ID")
