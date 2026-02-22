"""Plugin-related Pydantic models."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PluginComponent(BaseModel):
    """Plugin component entity."""

    id: int
    plugin_id: str
    name: str
    type: str
    content: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class Plugin(BaseModel):
    """Plugin entity."""

    id: str = Field(..., pattern=r"^plug-[a-z0-9]+$", examples=["plug-abc123"])
    name: str = Field(..., examples=["Security Scanner"])
    description: Optional[str] = None
    version: str = Field(default="1.0.0")
    status: str = Field(default="draft")
    author: Optional[str] = None
    component_count: int = Field(default=0)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PluginDetail(Plugin):
    """Plugin with full component list."""

    components: List[PluginComponent] = Field(default_factory=list)


class PluginListResponse(BaseModel):
    """Response for list plugins endpoint."""

    plugins: List[Plugin]


class CreatePluginRequest(BaseModel):
    """Request body for creating a plugin."""

    name: str = Field(..., min_length=1, examples=["Security Scanner"])
    description: Optional[str] = None
    version: Optional[str] = Field(default="1.0.0")
    status: Optional[str] = Field(default="draft")
    author: Optional[str] = None


class CreatePluginResponse(BaseModel):
    """Response for create plugin endpoint."""

    message: str
    plugin: Plugin


class UpdatePluginRequest(BaseModel):
    """Request body for updating a plugin."""

    name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    status: Optional[str] = None
    author: Optional[str] = None


class CreatePluginComponentRequest(BaseModel):
    """Request body for adding a plugin component."""

    name: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    content: Optional[str] = None


class AddPluginComponentResponse(BaseModel):
    """Response for add plugin component endpoint."""

    message: str
    component: PluginComponent


class UpdatePluginComponentRequest(BaseModel):
    """Request body for updating a plugin component."""

    name: Optional[str] = None
    type: Optional[str] = None
    content: Optional[str] = None


# =============================================================================
# Phase 5: Export / Import / Deploy / Sync Models
# =============================================================================


# --- Path models (for flask-openapi3 URL parameters) ---


class ExportPath(BaseModel):
    """Path parameters for export endpoints."""

    plugin_id: str = Field(..., description="Plugin ID to export")


class MarketplaceDeployPath(BaseModel):
    """Path parameters for marketplace deploy endpoints."""

    marketplace_id: str = Field(..., description="Marketplace ID to deploy to")


# --- Request models ---


class ExportRequest(BaseModel):
    """Request body for exporting a team as a plugin."""

    team_id: str = Field(..., description="Team ID whose entities to export")
    export_format: Literal["claude", "hive"] = Field(
        ..., description="Export format: 'claude' for Claude Code plugin, 'hive' for Hive package"
    )
    output_dir: Optional[str] = Field(
        default=None, description="Output directory path (auto-generated if not provided)"
    )


class ImportRequest(BaseModel):
    """Request body for importing a plugin from a local directory."""

    source_path: str = Field(..., description="Path to the plugin directory to import")
    plugin_name: Optional[str] = Field(
        default=None,
        description="Override plugin name (uses manifest or directory name if not set)",
    )


class ImportFromMarketplaceRequest(BaseModel):
    """Request body for importing a plugin from a marketplace."""

    marketplace_id: str = Field(..., description="Marketplace to import from")
    remote_plugin_name: str = Field(..., description="Name of the plugin in the marketplace")


class DeployRequest(BaseModel):
    """Request body for deploying a plugin to a marketplace."""

    plugin_id: str = Field(..., description="Plugin ID to deploy")
    marketplace_id: str = Field(..., description="Target marketplace ID")
    version: Optional[str] = Field(default="1.0.0", description="Version string for the deployment")


class SyncToggleRequest(BaseModel):
    """Request body for toggling bidirectional sync on a plugin."""

    plugin_id: str = Field(..., description="Plugin ID to sync")
    plugin_dir: str = Field(..., description="Local directory path for the plugin files")
    enabled: bool = Field(..., description="Whether to enable or disable sync")


# --- Response models ---


class ExportResponse(BaseModel):
    """Response after exporting a plugin."""

    export_path: str = Field(..., description="Path where the plugin was exported")
    plugin_name: str = Field(..., description="Name of the exported plugin")
    format: str = Field(..., description="Export format used")
    agents: int = Field(default=0, description="Number of agents exported")
    skills: int = Field(default=0, description="Number of skills exported")
    commands: int = Field(default=0, description="Number of commands exported")
    hooks: int = Field(default=0, description="Number of hooks exported")
    rules: int = Field(default=0, description="Number of rules exported")


class ImportResponse(BaseModel):
    """Response after importing a plugin."""

    plugin_id: str = Field(..., description="ID of the created plugin")
    plugin_name: str = Field(..., description="Name of the imported plugin")
    agents_imported: int = Field(default=0, description="Number of agents imported")
    skills_imported: int = Field(default=0, description="Number of skills imported")
    commands_imported: int = Field(default=0, description="Number of commands imported")
    hooks_imported: int = Field(default=0, description="Number of hooks imported")
    rules_imported: int = Field(default=0, description="Number of rules imported")


class DeployResponse(BaseModel):
    """Response after deploying a plugin to a marketplace."""

    message: str = Field(..., description="Deployment status message")
    marketplace_url: str = Field(..., description="URL of the marketplace")
    plugin_name: str = Field(..., description="Name of the deployed plugin")


class SyncStateResponse(BaseModel):
    """Response for sync state queries."""

    plugin_id: str = Field(..., description="Plugin ID")
    status: str = Field(..., description="Sync status (active, paused, error)")
    entities_synced: int = Field(default=0, description="Number of entities currently synced")
    last_synced_at: Optional[str] = Field(default=None, description="ISO timestamp of last sync")
    watching: bool = Field(default=False, description="Whether filesystem watcher is active")


class PluginExportRecord(BaseModel):
    """Record of a plugin export operation."""

    id: int = Field(..., description="Export record ID")
    plugin_id: str = Field(..., description="Plugin ID that was exported")
    team_id: Optional[str] = Field(default=None, description="Team ID if exported from a team")
    export_format: str = Field(..., description="Format used for export")
    export_path: Optional[str] = Field(default=None, description="Path where exported")
    status: str = Field(default="completed", description="Export status")
    version: str = Field(default="1.0.0", description="Version exported")
    last_exported_at: Optional[str] = Field(default=None, description="ISO timestamp of the export")
