"""Rate limit snapshots, monitoring config, and setup execution CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def _utc_suffix(row: dict) -> dict:
    """Ensure recorded_at has 'Z' suffix so the frontend treats it as UTC."""
    ra = row.get("recorded_at", "")
    if ra and not ra.endswith("Z") and "+" not in ra:
        row["recorded_at"] = ra + "Z"
    return row


# =============================================================================
# Rate Limit Snapshot CRUD operations
# =============================================================================


def insert_rate_limit_snapshot(
    account_id: int,
    backend_type: str,
    window_type: str,
    tokens_used: int = 0,
    tokens_limit: int = 0,
    percentage: float = 0.0,
    threshold_level: str = "normal",
    resets_at: Optional[str] = None,
) -> Optional[int]:
    """Insert a rate limit snapshot row. Returns the row ID on success."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO rate_limit_snapshots
                    (account_id, backend_type, window_type, tokens_used, tokens_limit,
                     percentage, threshold_level, resets_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    backend_type,
                    window_type,
                    tokens_used,
                    tokens_limit,
                    percentage,
                    threshold_level,
                    resets_at,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Database error in insert_rate_limit_snapshot: {e}")
            return None


def get_latest_snapshots(max_age_minutes: int = 60) -> List[dict]:
    """Return the most recent snapshot per (account_id, window_type).

    Only includes snapshots recorded within the last ``max_age_minutes`` so
    stale data from accounts that haven't been polled recently is excluded.
    Excludes Gemini Vertex AI duplicates and deprecated 2.0 models.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT s.*
            FROM rate_limit_snapshots s
            INNER JOIN (
                SELECT account_id, window_type, MAX(id) as max_id
                FROM rate_limit_snapshots
                WHERE window_type NOT LIKE '%!_vertex' ESCAPE '!'
                  AND window_type NOT LIKE 'gemini-2.0%'
                  AND window_type NOT LIKE 'gemini-2.5%'
                  AND window_type != 'primary_window'
                  AND window_type != 'secondary_window'
                  AND recorded_at >= datetime('now', ?)
                GROUP BY account_id, window_type
            ) latest
            ON s.id = latest.max_id
            ORDER BY s.account_id, s.window_type
            """,
            (f"-{max_age_minutes} minutes",),
        )
        return [_utc_suffix(dict(row)) for row in cursor.fetchall()]


def get_snapshot_history(account_id: int, window_type: str, since_minutes: int = 360) -> List[dict]:
    """Return snapshots for the given account/window within the last N minutes, ordered ASC."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM rate_limit_snapshots
            WHERE account_id = ? AND window_type = ?
              AND recorded_at >= datetime('now', ?)
            ORDER BY recorded_at ASC
            """,
            (account_id, window_type, f"-{since_minutes} minutes"),
        )
        return [_utc_suffix(dict(row)) for row in cursor.fetchall()]


def delete_old_snapshots(days: int = 7) -> int:
    """Delete snapshots older than N days. Returns count of deleted rows."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM rate_limit_snapshots WHERE recorded_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        conn.commit()
        return cursor.rowcount


def get_rate_limit_stats_by_period(
    group_by: str = "week",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[dict]:
    """Aggregate rate limit snapshots by week or month."""
    date_fmt = "%Y-W%W" if group_by == "week" else "%Y-%m"
    query = f"""
        SELECT
            strftime('{date_fmt}', recorded_at) as period_start,
            ROUND(AVG(percentage), 1) as avg_percentage,
            ROUND(MAX(percentage), 1) as max_percentage,
            COUNT(*) as snapshot_count
        FROM rate_limit_snapshots
        WHERE 1=1
    """
    params: list = []
    if start_date:
        query += " AND date(recorded_at) >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date(recorded_at) <= ?"
        params.append(end_date)
    query += f" GROUP BY strftime('{date_fmt}', recorded_at) ORDER BY period_start DESC"

    with get_connection() as conn:
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# Monitoring Config CRUD operations
# =============================================================================


def get_monitoring_config() -> dict:
    """Read monitoring_config from settings table. Returns parsed JSON or default."""
    import json as _json

    with get_connection() as conn:
        cursor = conn.execute("SELECT value FROM settings WHERE key = 'monitoring_config'")
        row = cursor.fetchone()
        if row and row["value"]:
            try:
                return _json.loads(row["value"])
            except (_json.JSONDecodeError, TypeError):
                pass
    return {"enabled": False, "polling_minutes": 5, "accounts": {}}


def save_monitoring_config(config_dict: dict) -> bool:
    """Upsert monitoring_config key in settings table as JSON string."""
    import json as _json

    value = _json.dumps(config_dict)
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES ('monitoring_config', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (value,),
        )
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Setup Execution CRUD operations
# =============================================================================


def create_setup_execution(
    execution_id: str, project_id: str, command: str, status: str = "running"
) -> bool:
    """Create a setup execution record. Returns True on success."""
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO setup_executions (id, project_id, command, status, started_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (execution_id, project_id, command, status),
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Database error in create_setup_execution: {e}")
            return False


def update_setup_execution(execution_id: str, **kwargs) -> bool:
    """Update a setup execution record with dynamic SET clause. Returns True on success."""
    if not kwargs:
        return False
    allowed_fields = {"status", "finished_at", "exit_code", "error_message"}
    filtered = {k: v for k, v in kwargs.items() if k in allowed_fields}
    if not filtered:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in filtered)
    values = list(filtered.values()) + [execution_id]
    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE setup_executions SET {set_clause} WHERE id = ?",
            values,
        )
        conn.commit()
        return cursor.rowcount > 0


def get_setup_execution(execution_id: str) -> Optional[dict]:
    """Get a setup execution by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM setup_executions WHERE id = ?", (execution_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_setup_executions_for_project(project_id: str, limit: int = 20) -> List[dict]:
    """Get setup executions for a project, ordered by most recent."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM setup_executions WHERE project_id = ? ORDER BY started_at DESC LIMIT ?",
            (project_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]
