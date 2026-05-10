"""v0.7.13: POST /admin/system/cliproxy/upgrade — manual upgrade trigger.

Admin-only. Invokes CLIProxyManager.upgrade() and returns the result
along with the resulting installed version.
"""

from __future__ import annotations

from typing import Any

from litestar import Router, post

from app_litestar.auth_guards import requires_role


@post(
    "/upgrade",
    sync_to_thread=True,
    guards=[requires_role("admin")],
)
def upgrade_cliproxy() -> dict[str, Any]:
    """Manually trigger a cliproxyapi upgrade. Admin-only."""
    from app.services.cliproxy_manager import CLIProxyManager

    ok, msg = CLIProxyManager.upgrade()
    return {
        "success": ok,
        "message": msg,
        "version": CLIProxyManager.detect_version(),
    }


cliproxy_lifecycle_router = Router(
    path="/admin/system/cliproxy",
    route_handlers=[upgrade_cliproxy],
)
