"""Trigger configuration export/import API endpoints."""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..models.config_export import (
    ConfigFormatQuery,
    ConfigImportRequest,
    ConfigImportResult,
    ConfigValidateRequest,
)
from ..services.config_export_service import (
    export_all_triggers,
    export_trigger,
    import_trigger,
    validate_config,
)

tag = Tag(name="config", description="Trigger configuration export/import")
config_export_bp = APIBlueprint(
    "config_export", __name__, url_prefix="/admin", abp_tags=[tag]
)


class TriggerIdPath(BaseModel):
    """Path parameter for trigger ID."""

    trigger_id: str = Field(..., description="Trigger ID")


@config_export_bp.get("/triggers/<trigger_id>/export")
def export_trigger_config(path: TriggerIdPath, query: ConfigFormatQuery):
    """Export a single trigger configuration as YAML or JSON."""
    fmt = query.format or "yaml"
    if fmt not in ("yaml", "json"):
        return {"error": "format must be 'yaml' or 'json'"}, HTTPStatus.BAD_REQUEST

    result = export_trigger(path.trigger_id, format=fmt)
    if result is None:
        return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

    content_type = "application/json" if fmt == "json" else "text/yaml"
    return result, HTTPStatus.OK, {"Content-Type": content_type}


@config_export_bp.post("/triggers/import")
def import_trigger_config(body: ConfigImportRequest):
    """Import a trigger from YAML or JSON configuration."""
    if body.format not in ("yaml", "json"):
        return {"error": "format must be 'yaml' or 'json'"}, HTTPStatus.BAD_REQUEST

    try:
        trigger_id, status = import_trigger(
            config_str=body.config,
            format=body.format,
            upsert=body.upsert,
        )
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.BAD_REQUEST

    result = ConfigImportResult(
        trigger_id=trigger_id,
        name="",  # will be filled from actual data
        status=status,
        message=f"Trigger {status} successfully",
    )

    # Get the actual name from DB
    from app.db import get_trigger as _get_trigger

    trigger = _get_trigger(trigger_id)
    if trigger:
        result.name = trigger["name"]

    return result.model_dump(), HTTPStatus.OK if status == "updated" else HTTPStatus.CREATED


@config_export_bp.post("/triggers/validate-config")
def validate_trigger_config(body: ConfigValidateRequest):
    """Validate a trigger configuration without importing."""
    if body.format not in ("yaml", "json"):
        return {"error": "format must be 'yaml' or 'json'"}, HTTPStatus.BAD_REQUEST

    valid, error = validate_config(body.config, format=body.format)
    return {"valid": valid, "error": error}, HTTPStatus.OK


@config_export_bp.get("/triggers/export-all")
def export_all_trigger_configs(query: ConfigFormatQuery):
    """Export all trigger configurations as YAML or JSON."""
    fmt = query.format or "yaml"
    if fmt not in ("yaml", "json"):
        return {"error": "format must be 'yaml' or 'json'"}, HTTPStatus.BAD_REQUEST

    result = export_all_triggers(format=fmt)
    content_type = "application/json" if fmt == "json" else "text/yaml"
    return result, HTTPStatus.OK, {"Content-Type": content_type}
