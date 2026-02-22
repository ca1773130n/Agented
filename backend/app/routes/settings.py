"""Settings API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import delete_setting, get_all_settings, get_setting, set_setting

tag = Tag(name="settings", description="Application settings management")
settings_bp = APIBlueprint("settings", __name__, url_prefix="/api/settings", abp_tags=[tag])


class SettingPath(BaseModel):
    key: str = Field(..., description="Setting key")


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
def set_setting_endpoint(path: SettingPath):
    """Set a setting value."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    value = data.get("value")
    if value is None:
        return {"error": "value is required"}, HTTPStatus.BAD_REQUEST

    set_setting(path.key, str(value))
    return {"key": path.key, "value": value}, HTTPStatus.OK


@settings_bp.delete("/<key>")
def delete_setting_endpoint(path: SettingPath):
    """Delete a setting."""
    if not delete_setting(path.key):
        return {"error": "Setting not found"}, HTTPStatus.NOT_FOUND
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
def set_harness_plugin():
    """Set the harness plugin selection."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    plugin_id = data.get("plugin_id")
    marketplace_id = data.get("marketplace_id")
    plugin_name = data.get("plugin_name")

    if plugin_id:
        set_setting("harness_plugin_id", str(plugin_id))
    if marketplace_id:
        set_setting("harness_marketplace_id", str(marketplace_id))
    if plugin_name:
        set_setting("harness_plugin_name", str(plugin_name))

    return {
        "plugin_id": plugin_id,
        "marketplace_id": marketplace_id,
        "plugin_name": plugin_name,
    }, HTTPStatus.OK
