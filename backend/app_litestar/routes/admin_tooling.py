"""Wave 64 — settings + system + secrets + gitops + version_pins + retention.

Six small admin namespaces, ~37 routes total. Mechanical CRUD with
preserved error semantics from the Flask versions.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from litestar import Router, delete, get, patch, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)

from app.database import (
    delete_setting,
    get_all_settings,
    get_setting,
    set_setting,
)
from app.db.gitops import (
    create_gitops_repo,
    delete_gitops_repo,
    get_gitops_repo,
    list_gitops_repos,
    list_sync_logs,
    update_gitops_repo,
)
from app.db.system_errors import (
    count_errors_by_status,
    get_system_error_with_fixes,
    list_system_errors,
    update_system_error_status,
)
from app.db.version_pins import (
    get_all_version_pins,
    get_version_history,
    get_version_pin,
    set_pin_unpinned,
    update_pin_status,
)
from app.services.error_capture import capture_error
from app.services.gitops_sync_service import GitOpsSyncService
from app.services.secret_vault_service import SecretVaultService

# ===========================================================================
# /api/settings/* (6)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_settings() -> dict[str, Any]:
    return {"settings": get_all_settings()}


@get("/harness-plugin", sync_to_thread=False)
def get_harness_plugin() -> dict[str, Any]:
    return {
        "plugin_id": get_setting("harness_plugin_id"),
        "marketplace_id": get_setting("harness_marketplace_id"),
        "plugin_name": get_setting("harness_plugin_name"),
    }


@put("/harness-plugin", sync_to_thread=False)
def set_harness_plugin(data: dict) -> dict[str, Any]:
    if data.get("plugin_id"):
        set_setting("harness_plugin_id", str(data["plugin_id"]))
    if data.get("marketplace_id"):
        set_setting("harness_marketplace_id", str(data["marketplace_id"]))
    if data.get("plugin_name"):
        set_setting("harness_plugin_name", str(data["plugin_name"]))
    return {
        "plugin_id": data.get("plugin_id"),
        "marketplace_id": data.get("marketplace_id"),
        "plugin_name": data.get("plugin_name"),
    }


@get("/{key:str}", sync_to_thread=False)
def get_setting_endpoint(key: str) -> dict[str, Any]:
    return {"key": key, "value": get_setting(key) or ""}


@put("/{key:str}", sync_to_thread=False)
def set_setting_endpoint(key: str, data: dict) -> dict[str, Any]:
    if "value" not in data:
        raise ClientException(detail="value is required")
    set_setting(key, str(data["value"]))
    return {"key": key, "value": data["value"]}


@delete("/{key:str}", status_code=200, sync_to_thread=False)
def delete_setting_endpoint(key: str) -> dict[str, Any]:
    if not delete_setting(key):
        raise NotFoundException(detail="Setting not found")
    return {"message": "Setting deleted"}


settings_router = Router(
    path="/api/settings",
    route_handlers=[
        list_settings,
        get_harness_plugin,
        set_harness_plugin,
        get_setting_endpoint,
        set_setting_endpoint,
        delete_setting_endpoint,
    ],
)


# ===========================================================================
# /admin/system/* (7)
# ===========================================================================


@get("/errors", sync_to_thread=False)
def list_errors(
    status: Optional[str] = None,
    category: Optional[str] = None,
    source: Optional[str] = None,
    since: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    errors, total_count = list_system_errors(
        status=status,
        category=category,
        source=source,
        since=since,
        search=search,
        limit=limit,
        offset=offset,
    )
    return {"errors": errors, "total_count": total_count}


@post("/errors", sync_to_thread=False)
def report_error(data: dict) -> dict[str, Any]:
    error_id = capture_error(
        category=data.get("category", "unknown"),
        message=data.get("message", ""),
        stack_trace=data.get("stack_trace"),
        context=({"raw": data["context_json"]} if data.get("context_json") else None),
        source=data.get("source"),
    )
    if not error_id:
        raise HTTPException(status_code=500, detail="Failed to capture error")
    return {"error_id": error_id}


@get("/errors/counts", sync_to_thread=False)
def get_error_counts() -> dict[str, Any]:
    return {"counts": count_errors_by_status()}


@get("/errors/{error_id:str}", sync_to_thread=False)
def get_error_detail(error_id: str) -> dict[str, Any]:
    error = get_system_error_with_fixes(error_id)
    if not error:
        raise NotFoundException(detail="Error not found")
    return error


@patch("/errors/{error_id:str}", sync_to_thread=False)
def update_error(error_id: str, data: dict) -> dict[str, Any]:
    if "status" not in data:
        raise ClientException(detail="status is required")
    if not update_system_error_status(error_id, data["status"]):
        raise NotFoundException(detail="Error not found")
    return {"message": "Status updated"}


@post("/errors/{error_id:str}/retry-fix", sync_to_thread=False)
def retry_fix(error_id: str) -> dict[str, Any]:
    from app.db.system_errors import get_system_error
    from app.services.autofix_service import trigger_autofix

    error = get_system_error(error_id)
    if not error:
        raise NotFoundException(detail="Error not found")
    trigger_autofix(error_id=error["id"])
    return {"message": "Autofix triggered"}


@get("/logs", sync_to_thread=False)
def get_logs(lines: int = 200) -> dict[str, Any]:
    log_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data",
        "logs",
        "agented.log",
    )
    if not os.path.exists(log_file):
        return {"lines": []}
    try:
        with open(log_file, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            if file_size == 0:
                return {"lines": []}
            chunk_size = min(file_size, lines * 500)
            f.seek(max(0, file_size - chunk_size))
            content = f.read().decode("utf-8", errors="replace")
            all_lines = content.splitlines()
        return {"lines": all_lines[-lines:]}
    except Exception:  # noqa: BLE001
        return {"lines": []}


system_router = Router(
    path="/admin/system",
    route_handlers=[
        list_errors,
        report_error,
        get_error_counts,
        get_error_detail,
        update_error,
        retry_fix,
        get_logs,
    ],
)


# ===========================================================================
# /admin/secrets/* (7)
# ===========================================================================


def _secret_metadata(secret: dict) -> dict[str, Any]:
    return {
        "id": secret["id"],
        "name": secret["name"],
        "description": secret.get("description"),
        "scope": secret.get("scope"),
        "created_at": secret.get("created_at"),
        "updated_at": secret.get("updated_at"),
    }


def _ensure_vault_configured() -> None:
    if not SecretVaultService.is_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Secrets vault not configured",
                "detail": "Set AGENTED_VAULT_KEYS environment variable to enable the secrets vault.",
            },
        )


@get("/status", sync_to_thread=False)
def vault_status() -> dict[str, Any]:
    configured = SecretVaultService.is_configured()
    count = 0
    if configured:
        try:
            from app.db.secrets import count_secrets

            count = count_secrets()
        except Exception:  # noqa: BLE001
            pass
    return {"configured": configured, "secret_count": count}


@post("/", sync_to_thread=False)
def create_secret(data: dict) -> dict[str, Any]:
    _ensure_vault_configured()
    if not data:
        raise ClientException(detail="JSON body required")
    name = data.get("name")
    value = data.get("value")
    if not name or value is None:
        raise ClientException(detail="name and value are required")
    try:
        secret_id = SecretVaultService.create_secret(
            name=name,
            value=value,
            description=data.get("description"),
            scope=data.get("scope"),
        )
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(
                status_code=409, detail=f"Secret with name '{name}' already exists"
            ) from None
        raise HTTPException(status_code=500, detail=str(exc)) from None
    from app.db.secrets import get_secret

    secret = get_secret(secret_id)
    return _secret_metadata(secret)


@get("/", sync_to_thread=False)
def list_secrets_endpoint() -> dict[str, Any]:
    _ensure_vault_configured()
    from app.db.secrets import list_secrets as db_list_secrets

    return {"secrets": db_list_secrets()}


@get("/{secret_id:str}", sync_to_thread=False)
def get_secret_detail(secret_id: str) -> dict[str, Any]:
    _ensure_vault_configured()
    from app.db.secrets import get_secret

    secret = get_secret(secret_id)
    if not secret:
        raise NotFoundException(detail="Secret not found")
    return _secret_metadata(secret)


@post("/{secret_id:str}/reveal", sync_to_thread=False)
def reveal_secret(secret_id: str) -> dict[str, Any]:
    _ensure_vault_configured()
    value = SecretVaultService.get_secret_value(secret_id, accessor="api")
    if value is None:
        raise NotFoundException(detail="Secret not found")
    from app.db.secrets import get_secret

    secret = get_secret(secret_id)
    return {"id": secret["id"], "name": secret["name"], "value": value}


@put("/{secret_id:str}", sync_to_thread=False)
def update_secret(secret_id: str, data: dict) -> dict[str, Any]:
    _ensure_vault_configured()
    if not data or (data.get("value") is None and data.get("description") is None):
        raise ClientException(detail="At least one of value or description is required")
    if not SecretVaultService.update_secret(
        secret_id=secret_id,
        value=data.get("value"),
        description=data.get("description"),
    ):
        raise NotFoundException(detail="Secret not found")
    from app.db.secrets import get_secret

    return _secret_metadata(get_secret(secret_id))


@delete("/{secret_id:str}", status_code=200, sync_to_thread=False)
def delete_secret(secret_id: str) -> dict[str, Any]:
    _ensure_vault_configured()
    if not SecretVaultService.delete_secret(secret_id):
        raise NotFoundException(detail="Secret not found")
    return {"message": "Secret deleted"}


secrets_router = Router(
    path="/admin/secrets",
    route_handlers=[
        vault_status,
        create_secret,
        list_secrets_endpoint,
        get_secret_detail,
        reveal_secret,
        update_secret,
        delete_secret,
    ],
)


# ===========================================================================
# /admin/gitops/* (7)
# ===========================================================================


@post("/gitops/repos", sync_to_thread=False)
def create_repo(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    repo_id = create_gitops_repo(
        name=data.get("name", ""),
        repo_url=data.get("repo_url", ""),
        branch=data.get("branch", "main"),
        config_path=data.get("config_path", ""),
        poll_interval=data.get("poll_interval_seconds", 60),
    )
    return get_gitops_repo(repo_id)


@get("/gitops/repos", sync_to_thread=False)
def list_repos() -> Any:
    return list_gitops_repos()


@get("/gitops/repos/{repo_id:str}", sync_to_thread=False)
def get_repo(repo_id: str) -> Any:
    repo = get_gitops_repo(repo_id)
    if not repo:
        raise NotFoundException(detail="GitOps repo not found")
    return repo


@put("/gitops/repos/{repo_id:str}", sync_to_thread=False)
def update_repo(repo_id: str, data: dict) -> Any:
    if not data:
        raise ClientException(detail="JSON body required")
    updates = {k: v for k, v in data.items() if v is not None}
    if "enabled" in updates:
        updates["enabled"] = 1 if updates["enabled"] else 0
    if not updates:
        raise ClientException(detail="No fields to update")
    if not update_gitops_repo(repo_id, **updates):
        raise NotFoundException(detail="GitOps repo not found")
    return get_gitops_repo(repo_id)


@delete("/gitops/repos/{repo_id:str}", status_code=200, sync_to_thread=False)
def delete_repo(repo_id: str) -> dict[str, Any]:
    if not delete_gitops_repo(repo_id):
        raise NotFoundException(detail="GitOps repo not found")
    return {"message": "GitOps repo deleted"}


@post("/gitops/repos/{repo_id:str}/sync", sync_to_thread=False)
def trigger_sync(repo_id: str, dry_run: bool = False) -> Any:
    if not get_gitops_repo(repo_id):
        raise NotFoundException(detail="GitOps repo not found")
    try:
        return GitOpsSyncService.sync_repo(repo_id, dry_run=dry_run)
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None


@get("/gitops/repos/{repo_id:str}/logs", sync_to_thread=False)
def get_sync_logs(repo_id: str, limit: int = 20) -> Any:
    if not get_gitops_repo(repo_id):
        raise NotFoundException(detail="GitOps repo not found")
    return list_sync_logs(repo_id, limit=limit)


gitops_router = Router(
    path="/admin",
    route_handlers=[
        create_repo,
        list_repos,
        get_repo,
        update_repo,
        delete_repo,
        trigger_sync,
        get_sync_logs,
    ],
)


# ===========================================================================
# /admin/version-pins/* (5)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_version_pins() -> dict[str, Any]:
    pins = get_all_version_pins()
    return {"pins": pins, "total": len(pins)}


@put("/{pin_id:str}", sync_to_thread=False)
def update_version_pin(pin_id: str, data: dict) -> Any:
    if not get_version_pin(pin_id):
        raise NotFoundException(detail="Version pin not found")
    if "pinned_version" not in data:
        raise ClientException(detail="pinned_version is required")
    pinned_at = data.get("pinned_at") or datetime.now(timezone.utc).isoformat()
    if not update_pin_status(
        pin_id=pin_id,
        pinned_version=data["pinned_version"],
        status=data.get("status") or "pinned",
        pinned_at=pinned_at,
    ):
        raise HTTPException(status_code=500, detail="Failed to update pin")
    return get_version_pin(pin_id)


@post("/{pin_id:str}/unpin", sync_to_thread=False)
def unpin_version_pin(pin_id: str) -> Any:
    if not get_version_pin(pin_id):
        raise NotFoundException(detail="Version pin not found")
    if not set_pin_unpinned(pin_id):
        raise HTTPException(status_code=500, detail="Failed to unpin")
    return get_version_pin(pin_id)


@post("/upgrade-all", sync_to_thread=False)
def upgrade_all_pins() -> dict[str, Any]:
    pins = get_all_version_pins()
    outdated = [p for p in pins if p.get("status") == "outdated"]
    now = datetime.now(timezone.utc).isoformat()
    upgraded = 0
    for pin in outdated:
        latest = pin.get("latest_version")
        if latest and update_pin_status(
            pin_id=pin["id"],
            pinned_version=latest,
            status="pinned",
            pinned_at=now,
        ):
            upgraded += 1
    return {"upgraded": upgraded, "total_outdated": len(outdated)}


@get("/{component_id:str}/versions", sync_to_thread=False)
def get_component_version_history(component_id: str) -> dict[str, Any]:
    history = get_version_history(component_id)
    return {"history": history, "total": len(history)}


version_pins_router = Router(
    path="/admin/version-pins",
    route_handlers=[
        list_version_pins,
        update_version_pin,
        unpin_version_pin,
        upgrade_all_pins,
        get_component_version_history,
    ],
)


# /admin/retention-policies/* moved to app_litestar.routes.retention (PR-R,
# wave 83). Persistence is real, validation lives in
# ``app.services.retention_service``; destructive enforcement is deferred.
