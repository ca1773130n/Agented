"""Health alerts CRUD operations.

Provides create/read/update/delete for the health_alerts table used by
the HealthMonitorService to persist bot health issues.
"""

import json
import logging
from typing import List, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def create_health_alert(
    alert_type: str,
    trigger_id: str,
    message: str,
    details: Optional[dict] = None,
    severity: str = "warning",
) -> Optional[int]:
    """Insert a health alert, returning its id.

    Deduplicates: skips if same alert_type+trigger_id exists within last 30 minutes.
    Returns None if deduplicated (skipped).
    """
    details_json = json.dumps(details) if details else None

    with get_connection() as conn:
        # Deduplication: check for same alert_type+trigger_id within 30 minutes
        cursor = conn.execute(
            """
            SELECT id FROM health_alerts
            WHERE alert_type = ? AND trigger_id = ?
              AND created_at > datetime('now', '-30 minutes')
            LIMIT 1
            """,
            (alert_type, trigger_id),
        )
        if cursor.fetchone():
            logger.debug("Deduplicated health alert: %s for trigger %s", alert_type, trigger_id)
            return None

        cursor = conn.execute(
            """
            INSERT INTO health_alerts (alert_type, trigger_id, message, details, severity)
            VALUES (?, ?, ?, ?, ?)
            """,
            (alert_type, trigger_id, message, details_json, severity),
        )
        conn.commit()
        return cursor.lastrowid


def get_recent_alerts(
    limit: int = 50,
    trigger_id: Optional[str] = None,
    acknowledged: Optional[bool] = None,
) -> List[dict]:
    """Return recent health alerts with optional filters."""
    with get_connection() as conn:
        query = "SELECT * FROM health_alerts WHERE 1=1"
        params: list = []

        if trigger_id is not None:
            query += " AND trigger_id = ?"
            params.append(trigger_id)
        if acknowledged is not None:
            query += " AND acknowledged = ?"
            params.append(1 if acknowledged else 0)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def acknowledge_alert(alert_id: int) -> bool:
    """Set acknowledged=1 for a specific alert. Returns True if updated."""
    with get_connection() as conn:
        cursor = conn.execute("UPDATE health_alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
        conn.commit()
        return cursor.rowcount > 0


def delete_old_alerts(days: int = 7) -> int:
    """Delete alerts older than specified days. Returns count deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM health_alerts WHERE created_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        conn.commit()
        return cursor.rowcount


def get_alert_count(trigger_id: Optional[str] = None, since: Optional[str] = None) -> int:
    """Count health alerts with optional filters."""
    with get_connection() as conn:
        query = "SELECT COUNT(*) FROM health_alerts WHERE 1=1"
        params: list = []

        if trigger_id is not None:
            query += " AND trigger_id = ?"
            params.append(trigger_id)
        if since is not None:
            query += " AND created_at >= ?"
            params.append(since)

        cursor = conn.execute(query, params)
        return cursor.fetchone()[0]
