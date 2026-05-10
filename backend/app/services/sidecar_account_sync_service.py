"""Sidecar → local account sync for monitoring + dashboards.

Post-wave-80 the ai-accounts sidecar owns AI-backend identity. Agented's
local ``backend_accounts`` table is empty unless the user happens to run
a CLI login flow through Agented itself (most don't). All Agented surfaces
that depend on the local table — rate-limit monitoring gauges, the token
dashboard's per-account breakdown, the auth-status checks — silently
degrade to "no data" because they never see the sidecar's accounts.

This service mirrors the sidecar's account list into the local
``backend_accounts`` table so the existing monitoring pipeline (which
expects integer ``account_id`` values referenced by ``rate_limit_snapshots``)
can poll them. We use ``create_backend_account``'s built-in upsert
(matches by whitespace-insensitive ``account_name`` or by ``config_path``)
so subsequent syncs update in place rather than producing duplicates.

The sync is best-effort: a sidecar outage returns 0 and never raises
into the monitoring loop. Local rows are *not* deleted when the sidecar
forgets an account — preserving snapshot history if the user toggles
visibility or temporarily shuts the sidecar down.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


_SIDECAR_DEFAULT_URL = "http://127.0.0.1:20001"
_BACKEND_KIND_TO_TYPE = {
    "claude": "claude",
    "codex": "codex",
    "gemini": "gemini",
    "opencode": "opencode",
}


def _resolve_admin_key() -> Optional[str]:
    """Pick the admin key for the sidecar's bearer auth.

    Priority matches `_discover_via_sidecar`: explicit env var first,
    then fall back to the first admin row in ``user_roles``. Returning
    None signals the caller to skip the sync silently.
    """
    api_key = os.environ.get("AI_ACCOUNTS_API_KEY") or os.environ.get("AGENTED_API_KEY")
    if api_key:
        return api_key
    try:
        from ..db.connection import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT api_key FROM user_roles WHERE role = 'admin' LIMIT 1"
            ).fetchone()
        if row:
            return row["api_key"] if hasattr(row, "keys") else row[0]
    except Exception as exc:
        logger.debug("Sidecar sync: could not read admin key: %s", exc)
    return None


def _resolve_backend_id(backend_kind: str) -> Optional[str]:
    """Map a sidecar ``kind`` (e.g. ``claude``) to the local
    ``ai_backends.id`` (e.g. ``backend-claude``)."""
    btype = _BACKEND_KIND_TO_TYPE.get(backend_kind)
    if not btype:
        return None
    try:
        from ..db.connection import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM ai_backends WHERE type = ? LIMIT 1", (btype,)
            ).fetchone()
        if row:
            return row["id"] if hasattr(row, "keys") else row[0]
    except Exception as exc:
        logger.debug("Sidecar sync: backend lookup failed for %s: %s", backend_kind, exc)
    return None


def sync_sidecar_accounts(*, timeout: float = 10.0) -> int:
    """Mirror sidecar accounts into the local ``backend_accounts`` table.

    Returns the number of accounts upserted. Returns 0 (and does not
    raise) on sidecar errors so callers in monitoring loops degrade
    gracefully — the next sync attempt may succeed once the sidecar
    is reachable again.
    """
    import httpx

    base_url = os.environ.get(
        "AGENTED_SIDECAR_URL",
        os.environ.get("AI_ACCOUNTS_SIDECAR_URL", _SIDECAR_DEFAULT_URL),
    )
    api_key = _resolve_admin_key()
    if not api_key:
        logger.debug("Sidecar sync: no admin key available; skipping")
        return 0

    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{base_url}/api/v1/backends/?limit=200", headers=headers)
        if resp.status_code != 200:
            logger.warning("Sidecar sync: list-backends returned %d", resp.status_code)
            return 0
        body = resp.json()
    except (httpx.HTTPError, OSError, ValueError) as exc:
        logger.warning("Sidecar sync: HTTP failure: %s", exc)
        return 0

    items = body.get("items") if isinstance(body, dict) else body
    if not isinstance(items, list):
        logger.debug("Sidecar sync: unexpected response shape: %s", type(body).__name__)
        return 0

    from ..db.backends import create_backend_account

    synced = 0
    for entry in items:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        backend_id = _resolve_backend_id(kind) if kind else None
        if not backend_id:
            continue

        config = entry.get("config") or {}
        # Sidecar's display_name is the operator-facing label; fall back to
        # the sidecar id (`bkd-...`) if missing so we never insert NULL.
        account_name = (
            entry.get("display_name")
            or config.get("account_name")
            or entry.get("id")
            or f"{kind}-account"
        )
        config_path = config.get("config_path")
        email = config.get("email")
        plan = config.get("plan")
        is_default = 1 if config.get("is_default") else 0

        try:
            create_backend_account(
                backend_id=backend_id,
                account_name=account_name,
                email=email,
                config_path=config_path,
                api_key_env=None,
                is_default=is_default,
                plan=plan,
                usage_data=None,
            )
            synced += 1
        except Exception as exc:
            logger.warning(
                "Sidecar sync: upsert failed for %s/%s: %s", kind, account_name, exc
            )

    if synced:
        logger.info("Sidecar sync: upserted %d account(s)", synced)
    return synced
