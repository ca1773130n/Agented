"""SuperAgent export and import API endpoints."""

import tempfile
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag

tag = Tag(
    name="super-agent-exports",
    description="SuperAgent export and import operations",
)
super_agent_exports_bp = APIBlueprint(
    "super_agent_exports",
    __name__,
    url_prefix="/admin/super-agent-exports",
    abp_tags=[tag],
)


@super_agent_exports_bp.post("/export")
def export_super_agent():
    """Export a SuperAgent as a directory structure or ZIP archive."""
    from ..services.super_agent_export_service import SuperAgentExportService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    super_agent_id = data.get("super_agent_id")
    if not super_agent_id:
        return {"error": "super_agent_id is required"}, HTTPStatus.BAD_REQUEST

    export_format = data.get("export_format", "zip")
    if export_format not in ("directory", "zip"):
        return {"error": "export_format must be 'directory' or 'zip'"}, HTTPStatus.BAD_REQUEST

    try:
        if export_format == "directory":
            output_dir = data.get("output_dir")
            if not output_dir:
                output_dir = tempfile.mkdtemp(prefix="hive-sa-export-")
            result = SuperAgentExportService.export_super_agent(
                super_agent_id=super_agent_id,
                output_dir=output_dir,
            )
        else:
            output_dir = data.get("output_dir")
            if not output_dir:
                output_dir = tempfile.mkdtemp(prefix="hive-sa-export-")
            output_path = f"{output_dir}/super_agent_export.zip"
            result = SuperAgentExportService.export_as_zip(
                super_agent_id=super_agent_id,
                output_path=output_path,
            )

        return result, HTTPStatus.OK
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.NOT_FOUND
    except Exception as e:
        return {"error": f"Export failed: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR


@super_agent_exports_bp.post("/import")
def import_super_agent():
    """Import a SuperAgent from a directory or ZIP archive."""
    from ..services.super_agent_export_service import SuperAgentExportService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    source_path = data.get("source_path")
    if not source_path:
        return {"error": "source_path is required"}, HTTPStatus.BAD_REQUEST

    try:
        # Auto-detect format from path
        if source_path.endswith(".zip"):
            result = SuperAgentExportService.import_from_zip(source_path)
        else:
            result = SuperAgentExportService.import_from_directory(source_path)

        # Check for validation failure
        if "error" in result:
            return result, HTTPStatus.BAD_REQUEST

        return result, HTTPStatus.CREATED
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.BAD_REQUEST
    except Exception as e:
        return {"error": f"Import failed: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR


@super_agent_exports_bp.post("/validate")
def validate_super_agent_package():
    """Validate a SuperAgent package manifest."""
    from ..services.super_agent_export_service import SuperAgentExportService, _read_json

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    source_path = data.get("source_path")
    if not source_path:
        return {"error": "source_path is required"}, HTTPStatus.BAD_REQUEST

    try:
        from pathlib import Path

        manifest_path = Path(source_path) / "manifest.json"
        if not manifest_path.exists():
            return {"error": "manifest.json not found"}, HTTPStatus.NOT_FOUND

        manifest = _read_json(manifest_path)
        result = SuperAgentExportService.validate_manifest(manifest)
        return result, HTTPStatus.OK
    except Exception as e:
        return {"error": f"Validation failed: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR
