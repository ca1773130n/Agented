"""Persistent audit event database operations.

Stores audit trail events in SQLite for queryable history with indexed columns
for entity_type, actor, and date range filtering.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def add_audit_event(
    action: str,
    entity_type: str,
    entity_id: str,
    outcome: str,
    actor: str = "system",
    details: Optional[Dict[str, Any]] = None,
) -> bool:
    """Persist an audit event to SQLite.

    Args:
        action: Short verb describing the operation (e.g. "trigger.update").
        entity_type: Domain object type (e.g. "trigger", "workflow").
        entity_id: Primary identifier of the entity.
        outcome: Result of the action (e.g. "success", "denied").
        actor: Who performed the action (default "system").
        details: Optional structured context dict (stored as JSON).

    Returns:
        True if event was persisted, False on error.
    """
    try:
        details_json = json.dumps(details) if details else None
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO audit_events
                   (action, entity_type, entity_id, outcome, actor, details)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (action, entity_type, entity_id, outcome, actor, details_json),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Failed to persist audit event: %s", e)
        return False


def query_audit_events(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    actor: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Query audit events with optional filters.

    Args:
        entity_type: Filter by entity type.
        entity_id: Filter by entity ID.
        actor: Filter by actor.
        start_date: Filter events on or after this ISO date (inclusive).
        end_date: Filter events on or before this ISO date (inclusive).
        limit: Maximum number of events to return.
        offset: Number of events to skip.

    Returns:
        List of audit event dicts, newest first.
    """
    conditions = []
    params: list = []

    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)
    if entity_id:
        conditions.append("entity_id = ?")
        params.append(entity_id)
    if actor:
        conditions.append("actor = ?")
        params.append(actor)
    if start_date:
        conditions.append("created_at >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("created_at <= ?")
        params.append(end_date)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    with get_connection() as conn:
        conn.row_factory = _dict_factory
        rows = conn.execute(
            f"""SELECT id, action, entity_type, entity_id, outcome, actor, details, created_at
                FROM audit_events
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
        conn.row_factory = None

    # Parse details JSON strings back to dicts
    for row in rows:
        if row.get("details"):
            try:
                row["details"] = json.loads(row["details"])
            except (json.JSONDecodeError, TypeError):
                pass

    return rows


def count_audit_events(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    actor: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> int:
    """Count audit events matching filters.

    Args:
        Same filters as query_audit_events.

    Returns:
        Total count of matching events.
    """
    conditions = []
    params: list = []

    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)
    if entity_id:
        conditions.append("entity_id = ?")
        params.append(entity_id)
    if actor:
        conditions.append("actor = ?")
        params.append(actor)
    if start_date:
        conditions.append("created_at >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("created_at <= ?")
        params.append(end_date)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    with get_connection() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) FROM audit_events WHERE {where_clause}",
            params,
        ).fetchone()
        return row[0] if row else 0


def _dict_factory(cursor, row):
    """Convert sqlite3 row to dict."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
