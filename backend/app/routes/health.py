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
    """Check if request carries a valid API key (DB or env var)."""
    from ..db.rbac import has_any_keys, get_role_for_api_key

    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return False

    # Check DB keys first
    if has_any_keys() and get_role_for_api_key(api_key):
        return True

    # Fallback: check env var
    secret = os.environ.get("AGENTED_API_KEY", "")
    if secret and hmac.compare_digest(api_key, secret):
        return True

    return False


@health_bp.get("/liveness")
def liveness():
    """Liveness probe - service is alive."""
    return {"status": "ok"}, HTTPStatus.OK


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


@health_bp.get("/auth-status")
def auth_status():
    """Public endpoint: tells the frontend whether auth is configured.

    Returns:
      - needs_setup: true when no API keys exist (first-run)
      - auth_required: true when keys exist and request isn't authenticated
      - authenticated: true when request carries a valid key
    """
    from ..db.rbac import has_any_keys

    has_db_keys = has_any_keys()
    env_key_set = bool(os.environ.get("AGENTED_API_KEY", ""))
    auth_configured = has_db_keys or env_key_set
    authenticated = _is_authenticated_request()

    return {
        "needs_setup": not auth_configured,
        "auth_required": auth_configured,
        "authenticated": authenticated,
    }, HTTPStatus.OK


@health_bp.post("/verify-key")
def verify_key():
    """Public endpoint: verify whether a provided API key is valid."""
    from ..db.rbac import has_any_keys, get_role_for_api_key

    data = request.get_json(silent=True) or {}
    provided = data.get("api_key", "")

    if not provided:
        return {"valid": False, "message": "No key provided"}, HTTPStatus.OK

    # Check DB
    if has_any_keys() and get_role_for_api_key(provided):
        return {"valid": True, "message": "Valid"}, HTTPStatus.OK

    # Fallback: env var
    secret = os.environ.get("AGENTED_API_KEY", "")
    if secret and hmac.compare_digest(provided, secret):
        return {"valid": True, "message": "Valid"}, HTTPStatus.OK

    # No auth configured at all
    if not has_any_keys() and not secret:
        return {"valid": True, "message": "No authentication configured"}, HTTPStatus.OK

    return {"valid": False, "message": "Invalid API key"}, HTTPStatus.OK


@health_bp.post("/setup")
def setup():
    """Public endpoint: generate the first admin API key.

    Only works when no API keys exist in the database (first-run bootstrap).
    Returns the generated key — this is the only time it will be shown.
    """
    from ..db.rbac import generate_api_key, invalidate_key_cache
    from ..db.connection import get_connection
    from ..db.ids import _get_unique_role_id

    data = request.get_json(silent=True) or {}
    label = data.get("label", "Admin")

    api_key = generate_api_key()

    # Atomic check-and-insert to prevent race conditions
    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM user_roles").fetchone()[0]
        if existing > 0:
            return {"error": "Already configured. Use the admin API to manage keys."}, 403

        role_id = _get_unique_role_id(conn)
        conn.execute(
            "INSERT INTO user_roles (id, api_key, label, role) VALUES (?, ?, ?, ?)",
            (role_id, api_key, label, "admin"),
        )
        conn.commit()

    invalidate_key_cache()

    return {
        "api_key": api_key,
        "role_id": role_id,
        "role": "admin",
        "label": label,
        "message": "Admin API key created. Save this key — it will not be shown again.",
    }, 201
