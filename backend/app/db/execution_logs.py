"""Execution log helpers for triggers.

Split out of triggers.py in v0.7.3 — pure file move, no logic
changes. Public API unchanged: this module's symbols are
re-exported from `app.db.triggers` for backward compatibility.
"""

import logging
from typing import Dict, List, Optional

from . import errors
from .connection import get_connection

logger = logging.getLogger(__name__)


def create_execution_log(
    execution_id: str,
    trigger_id: str,
    trigger_type: str,
    started_at: str,
    prompt: str,
    backend_type: str,
    command: str,
    trigger_config_snapshot: str = None,
    account_id: int = None,
    source_type: str = "bot",
    session_id: str = None,
) -> bool:
    """Create a new execution log entry. Returns True on success."""
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO execution_logs (execution_id, trigger_id, trigger_type, started_at, prompt, backend_type, command, status, trigger_config_snapshot, account_id, source_type, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?, ?)
            """,
                (
                    execution_id,
                    trigger_id,
                    trigger_type,
                    started_at,
                    prompt,
                    backend_type,
                    command,
                    trigger_config_snapshot,
                    account_id,
                    source_type,
                    session_id,
                ),
            )
            conn.commit()
            return True
        except errors.IntegrityError:
            return False


def update_execution_log(
    execution_id: str,
    status: str = None,
    finished_at: str = None,
    duration_ms: int = None,
    exit_code: int = None,
    error_message: str = None,
    stdout_log: str = None,
    stderr_log: str = None,
) -> bool:
    """Update an execution log entry. Returns True on success."""
    updates = []
    values = []

    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if finished_at is not None:
        updates.append("finished_at = ?")
        values.append(finished_at)
    if duration_ms is not None:
        updates.append("duration_ms = ?")
        values.append(duration_ms)
    if exit_code is not None:
        updates.append("exit_code = ?")
        values.append(exit_code)
    if error_message is not None:
        updates.append("error_message = ?")
        values.append(error_message)
    if stdout_log is not None:
        updates.append("stdout_log = ?")
        values.append(stdout_log)
    if stderr_log is not None:
        updates.append("stderr_log = ?")
        values.append(stderr_log)

    if not updates:
        return False

    values.append(execution_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE execution_logs SET {', '.join(updates)} WHERE execution_id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def mark_stale_executions_interrupted() -> int:
    """Mark running executions from previous sessions as interrupted. Returns count affected.

    This is a public API for use outside init_db() if needed.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE execution_logs SET status = 'interrupted', finished_at = datetime('now') WHERE status = 'running'"
        )
        conn.commit()
        return cursor.rowcount


def update_execution_status_cas(
    execution_id: str,
    new_status: str,
    expected_status: str = "running",
    **kwargs,
) -> bool:
    """Update execution status only if current status matches expected. Returns True if updated.

    Compare-and-swap update to prevent race conditions between cancel and normal completion.
    Accepts optional kwargs: finished_at, duration_ms, exit_code, error_message, stdout_log, stderr_log.
    """
    updates = ["status = ?"]
    values = [new_status]

    allowed_fields = {
        "finished_at",
        "duration_ms",
        "exit_code",
        "error_message",
        "stdout_log",
        "stderr_log",
    }
    for key, value in kwargs.items():
        if key in allowed_fields and value is not None:
            updates.append(f"{key} = ?")
            values.append(value)

    values.extend([execution_id, expected_status])

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE execution_logs SET {', '.join(updates)} WHERE execution_id = ? AND status = ?",
            values,
        )
        conn.commit()
        return cursor.rowcount > 0


def get_execution_logs_filtered(
    status: Optional[str] = None,
    trigger_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[dict]:
    """Query execution logs with composable filters and pagination.

    Args:
        status: Filter by execution status (e.g. 'running', 'success', 'failed').
        trigger_id: Filter by trigger ID.
        date_from: Filter by started_at >= date_from (ISO 8601 string).
        date_to: Filter by started_at <= date_to (ISO 8601 string).
        limit: Max rows to return (default 100).
        offset: Number of rows to skip (default 0).

    Returns:
        Matching rows ordered by started_at DESC.
    """
    with get_connection() as conn:
        query = "SELECT * FROM execution_logs WHERE 1=1"
        params: list = []

        if status is not None:
            query += " AND status = ?"
            params.append(status)
        if trigger_id is not None:
            query += " AND trigger_id = ?"
            params.append(trigger_id)
        if date_from is not None:
            query += " AND started_at >= ?"
            params.append(date_from)
        if date_to is not None:
            query += " AND started_at <= ?"
            params.append(date_to)

        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_execution_stats(trigger_id: Optional[str] = None) -> Dict:
    """Get aggregate execution statistics.

    Args:
        trigger_id: Optional filter by trigger ID.

    Returns:
        Dict with total, success_count, failed_count, avg_duration.
    """
    with get_connection() as conn:
        where = "WHERE 1=1"
        params: list = []
        if trigger_id is not None:
            where += " AND trigger_id = ?"
            params.append(trigger_id)

        cursor = conn.execute(
            f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count,
                AVG(CASE WHEN duration_ms IS NOT NULL
                    THEN duration_ms / 1000.0
                    ELSE NULL END
                ) as avg_duration_seconds
            FROM execution_logs {where}
            """,
            params,
        )
        row = cursor.fetchone()
        return {
            "total": row[0] or 0,
            "success_count": row[1] or 0,
            "failed_count": row[2] or 0,
            "avg_duration_seconds": round(row[3], 2) if row[3] else 0.0,
        }


def get_execution_log(execution_id: str) -> Optional[dict]:
    """Get a single execution log by execution_id or integer id.

    The list endpoints return rows with an integer ``id`` column and a string
    ``execution_id`` column.  This function first tries to match the string
    ``execution_id``, then falls back to matching the integer ``id`` so callers
    can use either identifier.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM execution_logs WHERE execution_id = ?", (execution_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)

        # Fallback: try matching by integer id
        try:
            int_id = int(execution_id)
        except (ValueError, TypeError):
            return None
        cursor = conn.execute("SELECT * FROM execution_logs WHERE id = ?", (int_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_execution_logs_for_trigger(
    trigger_id: str, limit: int = 50, offset: int = 0, status: str = None
) -> List[dict]:
    """Get execution logs for a trigger with pagination."""
    with get_connection() as conn:
        query = "SELECT * FROM execution_logs WHERE trigger_id = ?"
        params = [trigger_id]

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_all_execution_logs(limit: int = 100, offset: int = 0) -> List[dict]:
    """Get all execution logs with pagination."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT e.*, t.name as trigger_name
            FROM execution_logs e
            LEFT JOIN triggers t ON e.trigger_id = t.id
            ORDER BY e.started_at DESC
            LIMIT ? OFFSET ?
        """,
            (limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_running_execution_for_trigger(trigger_id: str) -> Optional[dict]:
    """Get the currently running execution for a trigger, if any."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM execution_logs WHERE trigger_id = ? AND status = 'running' ORDER BY started_at DESC LIMIT 1",
            (trigger_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_latest_execution_for_trigger(trigger_id: str) -> Optional[dict]:
    """Get the latest execution log entry for a trigger (any status)."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM execution_logs WHERE trigger_id = ? ORDER BY started_at DESC LIMIT 1",
            (trigger_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def count_execution_logs_for_trigger(trigger_id: str, status: str = None) -> int:
    """Count execution logs for a trigger with optional status filter."""
    with get_connection() as conn:
        query = "SELECT COUNT(*) FROM execution_logs WHERE trigger_id = ?"
        params: list = [trigger_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        cursor = conn.execute(query, params)
        return cursor.fetchone()[0]


def count_all_execution_logs() -> int:
    """Count all execution logs."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM execution_logs")
        return cursor.fetchone()[0]


def get_active_execution_count() -> int:
    """Get the count of currently running executions."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM execution_logs WHERE status = 'running'")
        return cursor.fetchone()[0]


def delete_old_execution_logs(days: int = 30) -> int:
    """Delete execution logs older than specified days. Returns count of deleted rows."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM execution_logs WHERE started_at < datetime('now', ?)", (f"-{days} days",)
        )
        conn.commit()
        return cursor.rowcount


def set_redispatched_from(execution_id: str, origin_execution_id: str) -> bool:
    """Provenance link: this execution is a re-dispatch of origin (Phase 4)."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE execution_logs SET redispatched_from = ? WHERE execution_id = ?",
            (origin_execution_id, execution_id),
        )
        conn.commit()
        return cur.rowcount > 0


def get_redispatch_child(origin_execution_id: str) -> Optional[dict]:
    """The execution that re-dispatched origin, if any (no-fan-out guard)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM execution_logs WHERE redispatched_from = ? LIMIT 1",
            (origin_execution_id,),
        ).fetchone()
    return dict(row) if row else None


def set_execution_session_id(execution_id: str, session_id: str) -> bool:
    """Persist the harness-reported session id (claude resume handle, Phase 4)."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE execution_logs SET session_id = ? WHERE execution_id = ?",
            (session_id, execution_id),
        )
        conn.commit()
        return cur.rowcount > 0
