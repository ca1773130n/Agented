"""Settings API endpoints."""

from http import HTTPStatus
from typing import Optional

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..database import delete_setting, get_all_settings, get_setting, set_setting

tag = Tag(name="settings", description="Application settings management")
settings_bp = APIBlueprint("settings", __name__, url_prefix="/api/settings", abp_tags=[tag])


class SettingPath(BaseModel):
    key: str = Field(..., description="Setting key")


class SetSettingBody(BaseModel):
    """Request body for setting a value."""

    value: str = Field(..., description="Setting value")


class SetHarnessPluginBody(BaseModel):
    """Request body for setting the harness plugin."""

    plugin_id: Optional[str] = None
    marketplace_id: Optional[str] = None
    plugin_name: Optional[str] = None


@settings_bp.get("/")
def list_settings():
    """Get all settings."""
    settings = get_all_settings()
    return {"settings": settings}, HTTPStatus.OK


@settings_bp.get("/<key>")
def get_setting_endpoint(path: SettingPath):
    """Get a specific setting by key."""
    value = get_setting(path.key)
    return {"key": path.key, "value": value or ""}, HTTPStatus.OK


@settings_bp.put("/<key>")
def set_setting_endpoint(path: SettingPath, body: SetSettingBody):
    """Set a setting value."""
    set_setting(path.key, str(body.value))
    return {"key": path.key, "value": body.value}, HTTPStatus.OK


@settings_bp.delete("/<key>")
def delete_setting_endpoint(path: SettingPath):
    """Delete a setting."""
    if not delete_setting(path.key):
        return error_response("NOT_FOUND", "Setting not found", HTTPStatus.NOT_FOUND)
    return {"message": "Setting deleted"}, HTTPStatus.OK


# Convenience endpoints for harness plugin


@settings_bp.get("/harness-plugin")
def get_harness_plugin():
    """Get the selected harness plugin ID."""
    plugin_id = get_setting("harness_plugin_id")
    marketplace_id = get_setting("harness_marketplace_id")
    plugin_name = get_setting("harness_plugin_name")
    return {
        "plugin_id": plugin_id,
        "marketplace_id": marketplace_id,
        "plugin_name": plugin_name,
    }, HTTPStatus.OK


@settings_bp.put("/harness-plugin")
def set_harness_plugin(body: SetHarnessPluginBody):
    """Set the harness plugin selection."""
    if body.plugin_id:
        set_setting("harness_plugin_id", str(body.plugin_id))
    if body.marketplace_id:
        set_setting("harness_marketplace_id", str(body.marketplace_id))
    if body.plugin_name:
        set_setting("harness_plugin_name", str(body.plugin_name))

    return {
        "plugin_id": body.plugin_id,
        "marketplace_id": body.marketplace_id,
        "plugin_name": body.plugin_name,
    }, HTTPStatus.OK
