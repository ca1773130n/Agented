"""v0.6.4: GET /admin/plugins/discover — filesystem-discovered plugins."""

from __future__ import annotations

from typing import Any

from litestar import Router, get

from app.services.plugin_discovery_service import discover
from app_litestar.auth_guards import requires_role


@get(
    "/discover",
    sync_to_thread=False,
    guards=[requires_role("admin")],
)
def discover_plugins() -> dict[str, Any]:
    """List plugins found on disk. Admin-only.

    Complements the DB-tracked plugin CRUD: shows operator what is
    actually installed in the configured plugin directories,
    regardless of whether it's been explicitly registered."""
    plugins = discover()
    return {"plugins": plugins, "count": len(plugins)}


plugin_discovery_router = Router(
    path="/admin/plugins",
    route_handlers=[discover_plugins],
)
