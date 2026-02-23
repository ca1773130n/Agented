"""Plugin export, import, deploy, and sync API endpoints."""

import tempfile
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import get_plugin_exports_for_plugin

tag = Tag(
    name="plugin-exports",
    description="Plugin export, import, deploy, and sync operations",
)
plugin_exports_bp = APIBlueprint(
    "plugin_exports",
    __name__,
    url_prefix="/admin/plugin-exports",
    abp_tags=[tag],
)


class PluginExportPath(BaseModel):
    plugin_id: str = Field(..., description="Plugin ID")


@plugin_exports_bp.post("/export")
def export_plugin():
    """Export a team as a Claude Code plugin or Agented package."""
    from ..services.plugin_export_service import ExportService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    team_id = data.get("team_id")
    if not team_id:
        return {"error": "team_id is required"}, HTTPStatus.BAD_REQUEST

    export_format = data.get("export_format")
    if export_format not in ("claude", "agented"):
        return {"error": "export_format must be 'claude' or 'agented'"}, HTTPStatus.BAD_REQUEST

    output_dir = data.get("output_dir")
    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix="agented-export-")

    try:
        if export_format == "claude":
            result = ExportService.export_as_claude_plugin(
                team_id=team_id,
                output_dir=output_dir,
            )
        else:
            result = ExportService.export_as_agented_package(
                team_id=team_id,
                output_dir=output_dir,
            )

        result["format"] = export_format
        return result, HTTPStatus.OK
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.NOT_FOUND
    except Exception as e:
        return {"error": f"Export failed: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR


@plugin_exports_bp.post("/import")
def import_plugin():
    """Import a plugin from a local directory."""
    from ..services.plugin_import_service import ImportService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    source_path = data.get("source_path")
    if not source_path:
        return {"error": "source_path is required"}, HTTPStatus.BAD_REQUEST

    plugin_name = data.get("plugin_name")

    try:
        result = ImportService.import_plugin_directory(
            plugin_dir=source_path,
            plugin_name=plugin_name,
        )
        return result, HTTPStatus.CREATED
    except FileNotFoundError as e:
        return {"error": str(e)}, HTTPStatus.NOT_FOUND
    except NotADirectoryError as e:
        return {"error": str(e)}, HTTPStatus.BAD_REQUEST
    except Exception as e:
        return {"error": f"Import failed: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR


@plugin_exports_bp.post("/import-from-marketplace")
def import_from_marketplace():
    """Import a plugin from a connected marketplace."""
    from ..services.plugin_deploy_service import DeployService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    marketplace_id = data.get("marketplace_id")
    if not marketplace_id:
        return {"error": "marketplace_id is required"}, HTTPStatus.BAD_REQUEST

    remote_plugin_name = data.get("remote_plugin_name")
    if not remote_plugin_name:
        return {"error": "remote_plugin_name is required"}, HTTPStatus.BAD_REQUEST

    try:
        result = DeployService.load_from_marketplace(
            marketplace_id=marketplace_id,
            remote_plugin_name=remote_plugin_name,
        )
        return result, HTTPStatus.CREATED
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.NOT_FOUND
    except RuntimeError as e:
        return {"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e:
        return {"error": f"Marketplace import failed: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR


@plugin_exports_bp.post("/deploy")
def deploy_plugin():
    """Deploy an exported plugin to a marketplace."""
    from ..services.plugin_deploy_service import DeployService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    plugin_id = data.get("plugin_id")
    if not plugin_id:
        return {"error": "plugin_id is required"}, HTTPStatus.BAD_REQUEST

    marketplace_id = data.get("marketplace_id")
    if not marketplace_id:
        return {"error": "marketplace_id is required"}, HTTPStatus.BAD_REQUEST

    version = data.get("version", "1.0.0")

    try:
        result = DeployService.deploy_to_marketplace(
            plugin_id=plugin_id,
            marketplace_id=marketplace_id,
            version=version,
        )
        return result, HTTPStatus.OK
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.NOT_FOUND
    except RuntimeError as e:
        return {"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR
    except Exception as e:
        return {"error": f"Deploy failed: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR


@plugin_exports_bp.post("/test-connection")
def test_marketplace_connection():
    """Test connectivity to a marketplace git repository."""
    from ..services.plugin_deploy_service import DeployService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    marketplace_id = data.get("marketplace_id")
    if not marketplace_id:
        return {"error": "marketplace_id is required"}, HTTPStatus.BAD_REQUEST

    result = DeployService.test_connection(marketplace_id=marketplace_id)
    return result, HTTPStatus.OK


@plugin_exports_bp.get("/<plugin_id>/exports")
def list_plugin_exports(path: PluginExportPath):
    """List all export records for a plugin."""
    exports = get_plugin_exports_for_plugin(path.plugin_id)
    return {"exports": exports}, HTTPStatus.OK


# =============================================================================
# Sync endpoints
# =============================================================================


@plugin_exports_bp.post("/sync")
def manual_sync_to_disk():
    """Sync all plugin entities from DB to disk.

    Triggers incremental sync -- only writes files where content hash has changed.
    """
    from ..services.plugin_sync_service import SyncService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    plugin_id = data.get("plugin_id")
    plugin_dir = data.get("plugin_dir")
    if not plugin_id or not plugin_dir:
        return {"error": "plugin_id and plugin_dir are required"}, HTTPStatus.BAD_REQUEST

    try:
        summary = SyncService.sync_all_to_disk(plugin_id, plugin_dir)
        return {"message": "Sync complete", **summary}, HTTPStatus.OK
    except Exception as e:
        return {"error": f"Sync failed: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR


@plugin_exports_bp.post("/sync/entity")
def sync_entity_to_disk():
    """Sync a single entity from DB to disk.

    Only writes the file if the content hash has changed since last sync.
    """
    from ..services.plugin_sync_service import SyncService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")
    plugin_id = data.get("plugin_id")
    plugin_dir = data.get("plugin_dir")

    if not all([entity_type, entity_id, plugin_id, plugin_dir]):
        return {
            "error": "entity_type, entity_id, plugin_id, and plugin_dir are required"
        }, HTTPStatus.BAD_REQUEST

    try:
        synced = SyncService.sync_entity_to_disk(entity_type, entity_id, plugin_id, plugin_dir)
        return {"synced": synced}, HTTPStatus.OK
    except Exception as e:
        return {"error": f"Sync failed: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR


@plugin_exports_bp.post("/watch")
def toggle_file_watcher():
    """Toggle the file watcher for a plugin directory.

    When enabled, external file changes are automatically synced back to DB.
    Uses debouncing (2s) to handle editor save patterns gracefully.
    """
    from ..services.plugin_sync_service import SyncService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    plugin_id = data.get("plugin_id")
    plugin_dir = data.get("plugin_dir")
    enabled = data.get("enabled", True)

    if not plugin_id:
        return {"error": "plugin_id is required"}, HTTPStatus.BAD_REQUEST

    try:
        if enabled:
            if not plugin_dir:
                return {
                    "error": "plugin_dir is required when enabling watch"
                }, HTTPStatus.BAD_REQUEST
            SyncService.start_watching(plugin_id, plugin_dir)
        else:
            SyncService.stop_watching(plugin_id)

        return {"watching": enabled, "plugin_id": plugin_id}, HTTPStatus.OK
    except Exception as e:
        return {"error": f"Watch toggle failed: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR


@plugin_exports_bp.get("/<plugin_id>/sync-status")
def get_plugin_sync_status(path: PluginExportPath):
    """Get sync status for a plugin.

    Returns entity count, last synced timestamp, and file watching state.
    """
    from ..services.plugin_sync_service import SyncService

    try:
        status = SyncService.get_sync_status(path.plugin_id)
        status["watching"] = SyncService.is_watching(path.plugin_id)
        return status, HTTPStatus.OK
    except Exception as e:
        return {"error": f"Failed to get sync status: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR
