"""Cached + auth-aware wrapper around ModelDiscoveryService._discover_raw.

Reads from model_discovery_cache; on miss / expiry / force refresh, runs
the underlying subprocess/PTY discovery, applies auth-method filtering,
and persists the result. Background refresh job runs daily; users only
ever block on first-discovery-after-deploy or after a manual invalidate.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.connection import get_connection
from app.services.model_auth_constraints import filter_models
from app.services.model_discovery_service import ModelDiscoveryService

logger = logging.getLogger(__name__)

DEFAULT_TTL_DAYS = 7


def _ttl_days() -> int:
    return int(os.environ.get("MODEL_DISCOVERY_TTL_DAYS", str(DEFAULT_TTL_DAYS)))


def get_models(
    *,
    backend_kind: str,
    auth_method: str = "unknown",
    force_refresh: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    if not force_refresh:
        cached = _read_cache(backend_kind, auth_method)
        if cached and not _is_expired(cached["expires_at"]):
            models = json.loads(cached["models_json"])
            filtered = filter_models(backend_kind, auth_method, models)
            return filtered, _meta_from_row(cached, fresh=False)
    return _discover_and_store(backend_kind, auth_method)


def refresh(backend_kind: str, auth_method: str = "unknown") -> dict[str, Any]:
    _models, meta = _discover_and_store(backend_kind, auth_method)
    return meta


def invalidate(backend_kind: str, auth_method: str | None = None) -> int:
    sql = "DELETE FROM model_discovery_cache WHERE backend_kind = ?"
    params: list[Any] = [backend_kind]
    if auth_method is not None:
        sql += " AND auth_method = ?"
        params.append(auth_method)
    with get_connection() as conn:
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur.rowcount or 0


def list_stale(*, grace_seconds: int = 0) -> list[dict[str, Any]]:
    """Cache rows whose expires_at <= now + grace. Used by background refresh."""
    cutoff = (datetime.now(timezone.utc) + timedelta(seconds=grace_seconds)).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM model_discovery_cache WHERE expires_at <= ? "
            "ORDER BY expires_at ASC",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_all() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM model_discovery_cache ORDER BY backend_kind, auth_method"
        ).fetchall()
    return [dict(r) for r in rows]


# --- internals ---


def _read_cache(backend_kind: str, auth_method: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM model_discovery_cache WHERE backend_kind = ? AND auth_method = ?",
            (backend_kind, auth_method),
        ).fetchone()
    return dict(row) if row else None


def _is_expired(expires_at: str) -> bool:
    return datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc)


def _meta_from_row(row: dict[str, Any], *, fresh: bool) -> dict[str, Any]:
    return {
        "backend_kind": row.get("backend_kind"),
        "auth_method": row.get("auth_method"),
        "discovery_method": row.get("discovery_method"),
        "discovered_at": row.get("discovered_at"),
        "expires_at": row.get("expires_at"),
        "error_message": row.get("error_message"),
        "fresh": fresh,
    }


def _discover_and_store(backend_kind: str, auth_method: str) -> tuple[list[str], dict[str, Any]]:
    raw_models: list[str] = []
    discovery_method = "mixed"
    error_message: str | None = None
    try:
        raw_models = ModelDiscoveryService._discover_raw(backend_kind)
        if not raw_models:
            error_message = "no models discovered"
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "Model discovery failed for %s/%s: %s",
            backend_kind,
            auth_method,
            error_message,
            exc_info=True,
        )
    discovered_at = datetime.now(timezone.utc)
    expires_at = discovered_at + timedelta(days=_ttl_days())
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO model_discovery_cache
                 (backend_kind, auth_method, models_json, discovery_method,
                  discovered_at, expires_at, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(backend_kind, auth_method) DO UPDATE SET
                 models_json = excluded.models_json,
                 discovery_method = excluded.discovery_method,
                 discovered_at = excluded.discovered_at,
                 expires_at = excluded.expires_at,
                 error_message = excluded.error_message""",
            (
                backend_kind,
                auth_method,
                json.dumps(raw_models),
                discovery_method,
                discovered_at.isoformat(),
                expires_at.isoformat(),
                error_message,
            ),
        )
        conn.commit()
    filtered = filter_models(backend_kind, auth_method, raw_models)
    row = _read_cache(backend_kind, auth_method)
    return filtered, _meta_from_row(row or {}, fresh=True)
