"""Health check endpoints."""

import hmac
import os
from datetime import datetime, timezone
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="health", description="Health check endpoints")
health_bp = APIBlueprint("health", __name__, url_prefix="/health", abp_tags=[tag])


def _is_authenticated_request() -> bool:
    """Check if request carries a valid API key.

    Self-contained auth check for the health endpoint (SEC-03).
    Compares X-API-Key header against AGENTED_API_KEY env var -- the same
    env var used by Phase 3's auth middleware in create_app().

    Returns False if AGENTED_API_KEY is not set (safe default: redact).
    """
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return False
    secret = os.environ.get("AGENTED_API_KEY", "")
    if not secret:
        return False
    return hmac.compare_digest(api_key, secret)


@health_bp.get("/liveness")
def liveness():
    """Liveness probe - service is alive."""
    return "", HTTPStatus.OK


@health_bp.get("/readiness")
def readiness():
    """Readiness probe with system health details.

    Unauthenticated callers receive a minimal response (SEC-03).
    Authenticated callers (valid X-API-Key header) receive full component health details.
    """
    # SEC-03: Unauthenticated callers get minimal response
    if not _is_authenticated_request():
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, 200

    # Full response for authenticated callers (existing logic below)
    from ..database import get_connection
    from ..services.process_manager import ProcessManager

    health = {"status": "ok", "components": {}}

    # DB check
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            health["components"]["database"] = {
                "status": "ok",
                "journal_mode": mode,
            }
    except Exception as e:
        health["status"] = "degraded"
        health["components"]["database"] = {
            "status": "error",
            "error": str(e),
        }

    # Process manager check
    health["components"]["process_manager"] = {
        "status": "ok",
        "active_executions": ProcessManager.get_active_count(),
        "active_execution_ids": ProcessManager.get_active_executions(),
    }

    # CLIProxy check (optional component — absent when not using Claude Code accounts)
    try:
        from ..services.cliproxy_manager import CLIProxyManager

        cli_proxy_healthy = CLIProxyManager.is_healthy()
        health["components"]["cli_proxy"] = {
            "status": "ok" if cli_proxy_healthy else "degraded",
            "port": CLIProxyManager._port,
        }
        if not cli_proxy_healthy:
            health["status"] = "degraded"
    except Exception as e:
        health["components"]["cli_proxy"] = {
            "status": "unknown",
            "error": str(e),
        }

    # Surface any non-fatal startup warnings
    from .. import _startup_warnings

    if _startup_warnings:
        health["components"]["startup"] = {
            "status": "degraded",
            "warnings": list(_startup_warnings),
        }
        if health["status"] == "ok":
            health["status"] = "degraded"
    else:
        health["components"]["startup"] = {"status": "ok"}

    status_code = 200 if health["status"] == "ok" else 503
    return health, status_code
