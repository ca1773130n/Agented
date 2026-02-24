"""Marketplace management API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    add_marketplace,
    add_marketplace_plugin,
    delete_marketplace,
    delete_marketplace_plugin,
    get_all_marketplaces,
    get_marketplace,
    get_marketplace_plugins,
    update_marketplace,
)
from ..services.github_service import GitHubService

tag = Tag(name="marketplaces", description="Plugin marketplace management operations")
marketplace_bp = APIBlueprint(
    "marketplaces", __name__, url_prefix="/admin/marketplaces", abp_tags=[tag]
)


class MarketplacePath(BaseModel):
    marketplace_id: str = Field(..., description="Marketplace ID")


class MarketplacePluginPath(BaseModel):
    marketplace_id: str = Field(..., description="Marketplace ID")
    plugin_id: str = Field(..., description="Marketplace plugin ID")


@marketplace_bp.get("/")
def list_marketplaces():
    """List all marketplaces."""
    marketplaces = get_all_marketplaces()
    return {"marketplaces": marketplaces}, HTTPStatus.OK


@marketplace_bp.get("/search")
def search_marketplace_items():
    """Search plugins and skills across all registered marketplaces."""
    query = request.args.get("q", "").strip().lower()
    item_type = request.args.get("type", "plugin")  # "plugin" or "skill"

    from ..services.plugin_deploy_service import DeployService

    all_marketplaces = get_all_marketplaces()
    results = []

    for marketplace in all_marketplaces:
        try:
            discovered = DeployService.discover_available_plugins_cached(marketplace["id"])
            # Support both "plugins" and "skills" arrays in marketplace.json
            items_key = "skills" if item_type == "skill" else "plugins"
            items = discovered.get(items_key, [])

            for item in items:
                name = (item.get("name") or "").lower()
                desc = (item.get("description") or "").lower()
                if not query or query in name or query in desc:
                    results.append(
                        {
                            **item,
                            "marketplace_id": marketplace["id"],
                            "marketplace_name": marketplace["name"],
                        }
                    )
        except Exception:
            continue  # Skip unreachable marketplaces gracefully

    return {
        "results": results,
        "total": len(results),
        "query": query,
        "type": item_type,
    }, HTTPStatus.OK


@marketplace_bp.post("/search/refresh")
def refresh_marketplace_cache():
    """Clear marketplace discovery cache to force fresh fetch."""
    from ..services.plugin_deploy_service import DeployService

    DeployService.clear_marketplace_cache()
    return {"message": "Marketplace cache cleared"}, HTTPStatus.OK


@marketplace_bp.post("/")
def create_marketplace():
    """Create a new marketplace."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    name = data.get("name")
    if not name:
        return {"error": "name is required"}, HTTPStatus.BAD_REQUEST

    url = data.get("url")
    if not url:
        return {"error": "url is required"}, HTTPStatus.BAD_REQUEST

    marketplace_type = data.get("type", "git")

    # Validate GitHub URL format for git type marketplaces
    if marketplace_type == "git" and url.startswith(("https://", "http://")):
        if not GitHubService.validate_github_url_format(url):
            return {
                "error": f"Invalid GitHub URL format: {url}. Expected format: https://github.com/owner/repo"
            }, HTTPStatus.BAD_REQUEST

    marketplace_id = add_marketplace(
        name=name,
        url=url,
        marketplace_type=data.get("type", "git"),
        is_default=data.get("is_default", False),
    )
    if not marketplace_id:
        return {"error": "Failed to create marketplace"}, HTTPStatus.INTERNAL_SERVER_ERROR

    marketplace = get_marketplace(marketplace_id)
    return {"message": "Marketplace created", "marketplace": marketplace}, HTTPStatus.CREATED


@marketplace_bp.get("/<marketplace_id>")
def get_marketplace_detail(path: MarketplacePath):
    """Get marketplace details."""
    marketplace = get_marketplace(path.marketplace_id)
    if not marketplace:
        return {"error": "Marketplace not found"}, HTTPStatus.NOT_FOUND
    return marketplace, HTTPStatus.OK


@marketplace_bp.put("/<marketplace_id>")
def update_marketplace_endpoint(path: MarketplacePath):
    """Update a marketplace."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    if not update_marketplace(
        path.marketplace_id,
        name=data.get("name"),
        url=data.get("url"),
        marketplace_type=data.get("type"),
        is_default=data.get("is_default"),
    ):
        return {"error": "Marketplace not found or no changes made"}, HTTPStatus.NOT_FOUND

    marketplace = get_marketplace(path.marketplace_id)
    return marketplace, HTTPStatus.OK


@marketplace_bp.delete("/<marketplace_id>")
def delete_marketplace_endpoint(path: MarketplacePath):
    """Delete a marketplace."""
    if not delete_marketplace(path.marketplace_id):
        return {"error": "Marketplace not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Marketplace deleted"}, HTTPStatus.OK


# Marketplace plugins routes
@marketplace_bp.get("/<marketplace_id>/plugins")
def list_marketplace_plugins(path: MarketplacePath):
    """List plugins installed from a marketplace."""
    plugins = get_marketplace_plugins(path.marketplace_id)
    return {"plugins": plugins}, HTTPStatus.OK


@marketplace_bp.get("/<marketplace_id>/plugins/available")
def discover_marketplace_plugins(path: MarketplacePath):
    """Discover all available plugins from marketplace repository."""
    from ..services.plugin_deploy_service import DeployService

    try:
        result = DeployService.discover_available_plugins(path.marketplace_id)
        return result, HTTPStatus.OK
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}, HTTPStatus.BAD_REQUEST


@marketplace_bp.post("/<marketplace_id>/plugins")
def install_plugin(path: MarketplacePath):
    """Install a plugin from a marketplace."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    remote_name = data.get("remote_name")
    if not remote_name:
        return {"error": "remote_name is required"}, HTTPStatus.BAD_REQUEST

    plugin_id = add_marketplace_plugin(
        marketplace_id=path.marketplace_id,
        remote_name=remote_name,
        plugin_id=data.get("plugin_id"),
        version=data.get("version"),
    )
    if not plugin_id:
        return {"error": "Failed to install plugin"}, HTTPStatus.INTERNAL_SERVER_ERROR

    plugins = get_marketplace_plugins(path.marketplace_id)
    plugin = next((p for p in plugins if p["id"] == plugin_id), None)
    return {"message": "Plugin installed", "plugin": plugin}, HTTPStatus.CREATED


@marketplace_bp.delete("/<marketplace_id>/plugins/<plugin_id>")
def uninstall_plugin(path: MarketplacePluginPath):
    """Uninstall a plugin from a marketplace."""
    if not delete_marketplace_plugin(path.plugin_id):
        return {"error": "Plugin not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Plugin uninstalled"}, HTTPStatus.OK
