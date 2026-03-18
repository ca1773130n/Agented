"""System error and fix attempt database CRUD operations.

Tracks platform errors (backend and frontend) with deduplication,
status management, and autofix attempt history.
"""

import logging
import sqlite3
from typing import Optional

from .connection import get_connection
from .ids import _get_unique_error_id, _get_unique_fix_attempt_id

logger = logging.getLogger(__name__)


def create_system_error(
    source: str,
    category: str,
    message: str,
    error_hash: str,
    stack_trace: str = None,
    request_id: str = None,
    context_json: str = None,
) -> Optional[str]:
    """Insert a new system error. Returns error ID."""
    with get_connection() as conn:
        try:
            error_id = _get_unique_error_id(conn)
            conn.execute(
                """INSERT INTO system_errors
                   (id, source, category, message, error_hash,
                    stack_trace, request_id, context_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    error_id,
                    source,
                    category,
                    message,
                    error_hash,
                    stack_trace,
                    request_id,
                    context_json,
                ),
            )
            conn.commit()
            return error_id
        except sqlite3.IntegrityError:
            logger.exception("Failed to create system error")
            return None


def get_system_error(error_id: str) -> Optional[dict]:
    """Get a single error by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM system_errors WHERE id = ?", (error_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_system_error_with_fixes(error_id: str) -> Optional[dict]:
    """Get error with its fix_attempts joined."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM system_errors WHERE id = ?", (error_id,))
        row = cursor.fetchone()
        if not row:
            return None
        error = dict(row)
        fix_cursor = conn.execute(
            "SELECT * FROM fix_attempts WHERE error_id = ? ORDER BY created_at ASC",
            (error_id,),
        )
        error["fix_attempts"] = [dict(r) for r in fix_cursor.fetchall()]
        return error


def list_system_errors(
    status: str = None,
    category: str = None,
    source: str = None,
    since: str = None,
    search: str = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """List errors with filters. Returns (errors, total_count)."""
    conditions: list[str] = []
    params: list = []

    if status:
        conditions.append("status = ?")
        params.append(status)
    if category:
        conditions.append("category = ?")
        params.append(category)
    if source:
        conditions.append("source = ?")
        params.append(source)
    if since:
        conditions.append("timestamp >= ?")
        params.append(since)
    if search:
        conditions.append("(message LIKE ? OR category LIKE ?)")
        like_q = f"%{search}%"
        params.extend([like_q, like_q])

    where_clause = ""
    if conditions:
        where_clause = " WHERE " + " AND ".join(conditions)

    with get_connection() as conn:
        count_cursor = conn.execute(f"SELECT COUNT(*) FROM system_errors{where_clause}", params)
        total = count_cursor.fetchone()[0]

        query = (
            f"SELECT * FROM system_errors{where_clause} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        cursor = conn.execute(query, params)
        errors = [dict(row) for row in cursor.fetchall()]

    return errors, total


def update_system_error_status(error_id: str, status: str) -> bool:
    """Update error status. Returns True if updated."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE system_errors SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, error_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def find_recent_duplicate(error_hash: str, window_seconds: int = 60) -> Optional[dict]:
    """Find a recent error with the same hash within the dedup window."""
    with get_connection() as conn:
        cursor = conn.execute(
            """SELECT * FROM system_errors
               WHERE error_hash = ?
                 AND timestamp >= datetime('now', ? || ' seconds')
               ORDER BY timestamp DESC LIMIT 1""",
            (error_hash, str(-window_seconds)),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def create_fix_attempt(error_id: str, tier: int) -> Optional[str]:
    """Create a new fix attempt. Returns fix attempt ID."""
    with get_connection() as conn:
        try:
            fix_id = _get_unique_fix_attempt_id(conn)
            conn.execute(
                """INSERT INTO fix_attempts (id, error_id, tier)
                   VALUES (?, ?, ?)""",
                (fix_id, error_id, tier),
            )
            conn.commit()
            return fix_id
        except sqlite3.IntegrityError:
            logger.exception("Failed to create fix attempt")
            return None


def update_fix_attempt(
    fix_attempt_id: str,
    status: str,
    action_taken: str = None,
    completed_at: str = None,
) -> bool:
    """Update fix attempt status and result."""
    fields = ["status = ?"]
    params: list = [status]

    if action_taken is not None:
        fields.append("action_taken = ?")
        params.append(action_taken)
    if completed_at is not None:
        fields.append("completed_at = ?")
        params.append(completed_at)

    params.append(fix_attempt_id)
    sql = f"UPDATE fix_attempts SET {', '.join(fields)} WHERE id = ?"

    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.rowcount > 0


def list_fix_attempts(error_id: str) -> list[dict]:
    """List all fix attempts for an error."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM fix_attempts WHERE error_id = ? ORDER BY created_at ASC",
            (error_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def count_errors_by_status() -> dict:
    """Count errors grouped by status. Returns {'new': N, 'investigating': N, ...}."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT status, COUNT(*) as cnt FROM system_errors GROUP BY status")
        return {row["status"]: row["cnt"] for row in cursor.fetchall()}
