"""Database CRUD operations for integrations (external service adapters)."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from .connection import get_connection
from .ids import _get_unique_integration_id

logger = logging.getLogger(__name__)

VALID_INTEGRATION_TYPES = ("slack", "teams", "jira", "linear")


def _row_to_dict(row) -> dict:
    """Convert a sqlite3.Row to a dictionary, parsing JSON config."""
    d = dict(row)
    if "config" in d and isinstance(d["config"], str):
        try:
            d["config"] = json.loads(d["config"])
        except (json.JSONDecodeError, TypeError):
            d["config"] = {}
    return d


def create_integration(
    name: str,
    integration_type: str,
    config: Optional[dict] = None,
    trigger_id: Optional[str] = None,
    enabled: bool = True,
) -> str:
    """Create a new integration config. Returns the integration ID."""
    with get_connection() as conn:
        integration_id = _get_unique_integration_id(conn)
        config_json = json.dumps(config or {})
        conn.execute(
            """INSERT INTO integrations (id, name, type, config, trigger_id, enabled)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (integration_id, name, integration_type, config_json, trigger_id, 1 if enabled else 0),
        )
        conn.commit()
        return integration_id


def get_integration(integration_id: str) -> Optional[dict]:
    """Get a single integration by ID."""
    with get_connection() as conn:
        conn.row_factory = __import__("sqlite3").Row
        row = conn.execute("SELECT * FROM integrations WHERE id = ?", (integration_id,)).fetchone()
        return _row_to_dict(row) if row else None


def list_integrations(
    integration_type: Optional[str] = None,
    trigger_id: Optional[str] = None,
) -> list:
    """List integrations with optional filters."""
    with get_connection() as conn:
        conn.row_factory = __import__("sqlite3").Row
        query = "SELECT * FROM integrations WHERE 1=1"
        params = []
        if integration_type:
            query += " AND type = ?"
            params.append(integration_type)
        if trigger_id:
            query += " AND trigger_id = ?"
            params.append(trigger_id)
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(r) for r in rows]


def update_integration(
    integration_id: str,
    name: Optional[str] = None,
    config: Optional[dict] = None,
    trigger_id: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> bool:
    """Update an integration. Returns True if found and updated."""
    fields = []
    params = []
    if name is not None:
        fields.append("name = ?")
        params.append(name)
    if config is not None:
        fields.append("config = ?")
        params.append(json.dumps(config))
    if trigger_id is not None:
        fields.append("trigger_id = ?")
        params.append(trigger_id)
    if enabled is not None:
        fields.append("enabled = ?")
        params.append(1 if enabled else 0)
    if not fields:
        return False
    fields.append("updated_at = ?")
    params.append(datetime.now(timezone.utc).isoformat())
    params.append(integration_id)
    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE integrations SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_integration(integration_id: str) -> bool:
    """Delete an integration. Returns True if found and deleted."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM integrations WHERE id = ?", (integration_id,))
        conn.commit()
        return cursor.rowcount > 0


def list_integrations_for_trigger(trigger_id: str) -> list:
    """List all enabled integrations for a specific trigger (plus global ones)."""
    with get_connection() as conn:
        conn.row_factory = __import__("sqlite3").Row
        rows = conn.execute(
            """SELECT * FROM integrations
               WHERE enabled = 1 AND (trigger_id = ? OR trigger_id IS NULL)
               ORDER BY created_at DESC""",
            (trigger_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
