"""Health endpoints — track A wave 37 migration.

Ports the entire /health/* namespace from Flask. Behaviour preserved
verbatim where it matters:
- /readiness still gates the components dict on authentication (SEC-03).
- /setup is still rate-limited per-IP (5 / 60s) and rejects when any
  user_roles row already exists (atomic check-and-insert).
- /verify-key still checks DB rows first, then falls back to the
  AGENTED_API_KEY env var.
"""

from __future__ import annotations

import hmac
import os
import time
from datetime import datetime, timezone
from typing import Any

from litestar import Request, Router, get, post
from litestar.exceptions import HTTPException
from msgspec import Struct

from app.db.rbac import (
    generate_api_key,
    get_role_for_api_key,
    has_any_keys,
    invalidate_key_cache,
    registration_open,
)


def _is_authenticated_request(request: Request) -> bool:
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return False
    if has_any_keys() and get_role_for_api_key(api_key):
        return True
    secret = os.environ.get("AGENTED_API_KEY", "")
    return bool(secret and hmac.compare_digest(api_key, secret))


@get("/liveness", sync_to_thread=False)
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@get("/readiness", sync_to_thread=False)
def readiness(request: Request) -> dict[str, Any]:
    """Readiness probe with system health details.

    Unauthenticated callers receive a minimal response (SEC-03).
    Authenticated callers get the full component breakdown.
    """
    if not _is_authenticated_request(request):
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

    from app.database import get_connection
    from app.services.process_manager import ProcessManager

    health: dict[str, Any] = {"status": "ok", "components": {}}

    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            health["components"]["database"] = {"status": "ok", "journal_mode": mode}
    except Exception as e:  # noqa: BLE001
        health["status"] = "degraded"
        health["components"]["database"] = {"status": "error", "error": str(e)}

    health["components"]["process_manager"] = {
        "status": "ok",
        "active_executions": ProcessManager.get_active_count(),
        "active_execution_ids": ProcessManager.get_active_executions(),
    }

    try:
        from app.services.cliproxy_manager import CLIProxyManager

        cli_proxy_healthy = CLIProxyManager.is_healthy()
        health["components"]["cli_proxy"] = {
            "status": "ok" if cli_proxy_healthy else "degraded",
            "port": CLIProxyManager._port,
        }
        if not cli_proxy_healthy:
            health["status"] = "degraded"
    except Exception as e:  # noqa: BLE001
        health["components"]["cli_proxy"] = {"status": "unknown", "error": str(e)}

    from app_litestar.lifecycle import _startup_warnings

    if _startup_warnings:
        health["components"]["startup"] = {
            "status": "degraded",
            "warnings": list(_startup_warnings),
        }
        if health["status"] == "ok":
            health["status"] = "degraded"
    else:
        health["components"]["startup"] = {"status": "ok"}

    # Readiness answers "can this instance serve requests?" — so gate the 503 on
    # CORE dependencies only (the database). A degraded OPTIONAL subsystem
    # (cli_proxy needs re-auth / cliproxyapi not up, or non-fatal startup
    # warnings) is surfaced in the body as status="degraded" but must NOT fail
    # readiness: a 503 here would pull a fully-functional instance out of
    # load-balancer rotation and make readiness pollers log a continuous stream
    # of errors — for a subsystem that only affects AI-account operations. The
    # frontend health indicator then reads status="degraded" from the 200 body
    # (instead of mis-rendering the 503 as a phantom database error).
    core_ok = health["components"].get("database", {}).get("status") == "ok"
    if not core_ok:
        raise HTTPException(status_code=503, detail=health)
    return health


@get("/instance-id", sync_to_thread=False)
def instance_id() -> dict[str, Any]:
    """Returns the database instance UUID for staleness detection.
    Public — no auth required."""
    from app.database import get_connection

    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key = 'instance_id'").fetchone()
    return {"instance_id": row[0] if row else None}


@get("/setup-status", sync_to_thread=False)
def setup_status() -> dict[str, Any]:
    """Aggregate guard prefetch for the v0.5.0 onboarding tour (OB-07).

    Returns the instance_id plus a `has_*` boolean for each setup-tour step.
    Public — no auth required, same scope as `/health/instance-id`. The
    frontend tour calls this once at boot to populate guards without 6+
    sequential round-trips. Guard fields default to `False` if their backing
    table is missing or unreadable, so the tour can still advance.
    """
    from app.database import get_connection

    result: dict[str, Any] = {
        "instance_id": None,
        "has_workspace": False,
        "has_claude_account": False,
        "has_codex_account": False,
        "has_gemini_account": False,
        "has_opencode_account": False,
        "has_harness_synced": False,
        "has_first_product": False,
    }

    try:
        with get_connection() as conn:
            row = conn.execute("SELECT value FROM app_meta WHERE key = 'instance_id'").fetchone()
            if row:
                result["instance_id"] = row[0]

            row = conn.execute("SELECT value FROM settings WHERE key = 'workspace_root'").fetchone()
            result["has_workspace"] = bool(row and (row[0] or "").strip())

            row = conn.execute(
                "SELECT value FROM app_meta WHERE key = 'harness_synced_at'"
            ).fetchone()
            result["has_harness_synced"] = bool(row and row[0])

            for backend in ("claude", "codex", "gemini", "opencode"):
                row = conn.execute(
                    "SELECT 1 FROM backend_accounts ba "
                    "JOIN ai_backends ab ON ab.id = ba.backend_id "
                    "WHERE ab.type = ? LIMIT 1",
                    (backend,),
                ).fetchone()
                result[f"has_{backend}_account"] = row is not None

            row = conn.execute("SELECT 1 FROM products LIMIT 1").fetchone()
            result["has_first_product"] = row is not None
    except Exception:
        # DB unreadable — return the defaults so the tour treats it as a fresh
        # install rather than blocking forever on a 500.
        pass

    return result


@get("/auth-status", sync_to_thread=False)
def auth_status(request: Request) -> dict[str, Any]:
    """Tells the frontend whether auth is configured. Public."""
    from app.services.oidc_service import OidcService

    has_db_keys = has_any_keys()
    env_key_set = bool(os.environ.get("AGENTED_API_KEY", ""))
    auth_configured = has_db_keys or env_key_set
    return {
        "needs_setup": not auth_configured,
        "auth_required": auth_configured,
        "authenticated": _is_authenticated_request(request),
        "signup_enabled": registration_open(),
        # Phase 25 (25-04): configured OIDC providers (empty when no env secrets)
        # so the SPA renders only available SSO buttons. OIDC absent → unchanged.
        "oidc_providers": OidcService.configured_providers(),
    }


class VerifyKeyBody(Struct):
    api_key: str = ""


@post("/verify-key", status_code=200, sync_to_thread=False)
def verify_key(data: VerifyKeyBody) -> dict[str, Any]:
    """Verify whether the provided API key is valid. Public."""
    provided = data.api_key
    if not provided:
        return {"valid": False, "message": "No key provided"}

    if has_any_keys() and get_role_for_api_key(provided):
        return {"valid": True, "message": "Valid"}

    secret = os.environ.get("AGENTED_API_KEY", "")
    if secret and hmac.compare_digest(provided, secret):
        return {"valid": True, "message": "Valid"}

    if not has_any_keys() and not secret:
        return {"valid": True, "message": "No authentication configured"}

    return {"valid": False, "message": "Invalid API key"}


_setup_rate_limit: dict[str, list[float]] = {}
_SETUP_RATE_MAX = 5
_SETUP_RATE_WINDOW = 60.0


class SetupBody(Struct):
    label: str = "Admin"


@post("/setup", sync_to_thread=False)
def setup(data: SetupBody, request: Request) -> dict[str, Any]:
    """Generate the first admin API key. Bootstrap-only (rejects when
    any user_roles row already exists). Rate-limited per source IP."""
    ip = request.client.host if request.client and request.client.host else "unknown"
    now = time.monotonic()
    hits = _setup_rate_limit.setdefault(ip, [])
    hits[:] = [t for t in hits if now - t < _SETUP_RATE_WINDOW]
    if len(hits) >= _SETUP_RATE_MAX:
        raise HTTPException(status_code=429, detail="Too many requests")
    hits.append(now)

    from app.db.connection import get_connection
    from app.db.ids import _get_unique_role_id

    api_key = generate_api_key()
    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM user_roles").fetchone()[0]
        if existing > 0:
            raise HTTPException(
                status_code=403,
                detail="Already configured. Use the admin API to manage keys.",
            )
        role_id = _get_unique_role_id(conn)
        conn.execute(
            "INSERT INTO user_roles (id, api_key, label, role) VALUES (?, ?, ?, ?)",
            (role_id, api_key, data.label, "admin"),
        )
        conn.commit()

    invalidate_key_cache()
    return {
        "api_key": api_key,
        "role_id": role_id,
        "role": "admin",
        "label": data.label,
        "message": "Admin API key created. Save this key — it will not be shown again.",
    }


health_router = Router(
    path="/health",
    route_handlers=[
        liveness,
        readiness,
        instance_id,
        setup_status,
        auth_status,
        verify_key,
        setup,
    ],
)
