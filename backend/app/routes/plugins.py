"""Plugin management API endpoints."""

from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    add_plugin,
    add_plugin_component,
    count_plugins,
    delete_plugin,
    delete_plugin_component,
    get_all_plugins,
    get_plugin,
    get_plugin_components,
    get_plugin_detail,
    update_plugin,
    update_plugin_component,
)
from ..models.common import PaginationQuery

tag = Tag(name="plugins", description="Plugin management operations")
plugins_bp = APIBlueprint("plugins", __name__, url_prefix="/admin/plugins", abp_tags=[tag])


class PluginPath(BaseModel):
    plugin_id: str = Field(..., description="Plugin ID")


class ComponentPath(BaseModel):
    plugin_id: str = Field(..., description="Plugin ID")
    component_id: int = Field(..., description="Component ID")


@plugins_bp.get("/")
def list_plugins(query: PaginationQuery):
    """List all plugins with component counts and optional pagination."""
    total_count = count_plugins()
    plugins = get_all_plugins(limit=query.limit, offset=query.offset or 0)
    return {"plugins": plugins, "total_count": total_count}, HTTPStatus.OK


@plugins_bp.post("/")
def create_plugin():
    """Create a new plugin."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    name = data.get("name")
    if not name:
        return {"error": "name is required"}, HTTPStatus.BAD_REQUEST

    plugin_id = add_plugin(
        name=name,
        description=data.get("description"),
        version=data.get("version", "1.0.0"),
        status=data.get("status", "draft"),
        author=data.get("author"),
    )
    if not plugin_id:
        return {"error": "Failed to create plugin"}, HTTPStatus.INTERNAL_SERVER_ERROR

    plugin = get_plugin(plugin_id)
    return {"message": "Plugin created", "plugin": plugin}, HTTPStatus.CREATED


@plugins_bp.get("/<plugin_id>")
def get_plugin_detail_endpoint(path: PluginPath):
    """Get plugin details with components."""
    plugin = get_plugin_detail(path.plugin_id)
    if not plugin:
        return {"error": "Plugin not found"}, HTTPStatus.NOT_FOUND
    return plugin, HTTPStatus.OK


@plugins_bp.put("/<plugin_id>")
def update_plugin_endpoint(path: PluginPath):
    """Update a plugin."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    if not update_plugin(
        path.plugin_id,
        name=data.get("name"),
        description=data.get("description"),
        version=data.get("version"),
        status=data.get("status"),
        author=data.get("author"),
    ):
        return {"error": "Plugin not found or no changes made"}, HTTPStatus.NOT_FOUND

    plugin = get_plugin(path.plugin_id)
    return plugin, HTTPStatus.OK


@plugins_bp.delete("/<plugin_id>")
def delete_plugin_endpoint(path: PluginPath):
    """Delete a plugin."""
    if not delete_plugin(path.plugin_id):
        return {"error": "Plugin not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Plugin deleted"}, HTTPStatus.OK


# Component routes
@plugins_bp.get("/<plugin_id>/components")
def list_components(path: PluginPath):
    """List plugin components."""
    components = get_plugin_components(path.plugin_id)
    return {"components": components}, HTTPStatus.OK


@plugins_bp.post("/<plugin_id>/components")
def add_component(path: PluginPath):
    """Add a component to the plugin."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    name = data.get("name")
    component_type = data.get("type")
    if not name or not component_type:
        return {"error": "name and type are required"}, HTTPStatus.BAD_REQUEST

    component_id = add_plugin_component(
        plugin_id=path.plugin_id,
        name=name,
        component_type=component_type,
        content=data.get("content"),
    )
    if not component_id:
        return {"error": "Failed to add component"}, HTTPStatus.INTERNAL_SERVER_ERROR

    components = get_plugin_components(path.plugin_id)
    component = next((c for c in components if c["id"] == component_id), None)
    return {"message": "Component added", "component": component}, HTTPStatus.CREATED


@plugins_bp.put("/<plugin_id>/components/<int:component_id>")
def update_component(path: ComponentPath):
    """Update a plugin component."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    if not update_plugin_component(
        path.component_id,
        name=data.get("name"),
        component_type=data.get("type"),
        content=data.get("content"),
    ):
        return {"error": "Component not found or no changes made"}, HTTPStatus.NOT_FOUND

    components = get_plugin_components(path.plugin_id)
    component = next((c for c in components if c["id"] == path.component_id), None)
    return {"component": component}, HTTPStatus.OK


@plugins_bp.delete("/<plugin_id>/components/<int:component_id>")
def remove_component(path: ComponentPath):
    """Delete a plugin component."""
    if not delete_plugin_component(path.component_id):
        return {"error": "Component not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Component deleted"}, HTTPStatus.OK


@plugins_bp.post("/generate/stream")
def generate_plugin_stream():
    """Generate a plugin configuration from a description using AI (streaming)."""
    from ..services.plugin_generation_service import PluginGenerationService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    description = (data.get("description") or "").strip()
    if len(description) < 10:
        return {"error": "Description must be at least 10 characters"}, HTTPStatus.BAD_REQUEST

    return Response(
        PluginGenerationService.generate_streaming(description),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
