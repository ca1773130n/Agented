"""Execution queue CRUD operations.

SQLite-backed execution queue for per-trigger concurrency control.
Entries persist across server restarts, enabling durable dispatch.
"""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import _generate_short_id

logger = logging.getLogger(__name__)

QUEUE_ENTRY_ID_PREFIX = "qe-"
QUEUE_ENTRY_ID_LENGTH = 6


def _generate_queue_entry_id() -> str:
    """Generate a queue entry ID like 'qe-abc123'."""
    return f"{QUEUE_ENTRY_ID_PREFIX}{_generate_short_id(QUEUE_ENTRY_ID_LENGTH)}"


def enqueue_execution(
    trigger_id: str,
    trigger_type: str,
    message_text: str = "",
    event_data: str = "{}",
    priority: int = 0,
) -> str:
    """Insert a new execution into the queue. Returns the queue entry ID.

    Args:
        trigger_id: The trigger that generated this execution.
        trigger_type: One of webhook, github, schedule, manual.
        message_text: Rendered message/prompt text.
        event_data: JSON-serialized event payload.
        priority: Priority level (0 = normal). Higher values dispatch first.

    Returns:
        The generated queue entry ID (qe-XXXXXX).
    """
    entry_id = _generate_queue_entry_id()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO execution_queue
                (id, trigger_id, trigger_type, message_text, event_data, priority, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', datetime('now'))
            """,
            (entry_id, trigger_id, trigger_type, message_text, event_data, priority),
        )
        conn.commit()
    return entry_id


def get_pending_entries(limit: int = 10) -> List[dict]:
    """Return pending queue entries in FIFO order (priority DESC, created_at ASC).

    Args:
        limit: Maximum number of entries to return.

    Returns:
        List of queue entry dicts.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM execution_queue
            WHERE status = 'pending'
            ORDER BY priority DESC, created_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_entry_status(entry_id: str, new_status: str, expected_status: str = None) -> bool:
    """Update the status of a queue entry with optional CAS (compare-and-swap).

    Args:
        entry_id: The queue entry ID.
        new_status: The new status to set.
        expected_status: If provided, only update if current status matches.

    Returns:
        True if the update affected a row.
    """
    with get_connection() as conn:
        if expected_status:
            # Determine which timestamp column to set
            ts_col = ""
            if new_status == "dispatching":
                ts_col = ", dispatched_at = datetime('now')"
            elif new_status in ("completed", "failed", "cancelled"):
                ts_col = ", completed_at = datetime('now')"

            cursor = conn.execute(
                f"""
                UPDATE execution_queue
                SET status = ?{ts_col}
                WHERE id = ? AND status = ?
                """,
                (new_status, entry_id, expected_status),
            )
        else:
            ts_col = ""
            if new_status == "dispatching":
                ts_col = ", dispatched_at = datetime('now')"
            elif new_status in ("completed", "failed", "cancelled"):
                ts_col = ", completed_at = datetime('now')"

            cursor = conn.execute(
                f"""
                UPDATE execution_queue
                SET status = ?{ts_col}
                WHERE id = ?
                """,
                (new_status, entry_id),
            )
        conn.commit()
        return cursor.rowcount > 0


def count_active_for_trigger(trigger_id: str) -> int:
    """Count entries currently in 'dispatching' status for a given trigger.

    Args:
        trigger_id: The trigger to count active entries for.

    Returns:
        Number of entries with status 'dispatching'.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM execution_queue WHERE trigger_id = ? AND status = 'dispatching'",
            (trigger_id,),
        )
        return cursor.fetchone()[0]


def get_queue_depth(trigger_id: Optional[str] = None) -> int:
    """Return count of pending entries, optionally filtered by trigger.

    Args:
        trigger_id: If provided, count only entries for this trigger.

    Returns:
        Number of pending queue entries.
    """
    with get_connection() as conn:
        if trigger_id:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM execution_queue WHERE trigger_id = ? AND status = 'pending'",
                (trigger_id,),
            )
        else:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM execution_queue WHERE status = 'pending'"
            )
        return cursor.fetchone()[0]


def get_queue_summary() -> List[dict]:
    """Return per-trigger pending/dispatching counts for admin visibility.

    Returns:
        List of dicts with trigger_id, pending, dispatching counts.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                trigger_id,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'dispatching' THEN 1 ELSE 0 END) AS dispatching
            FROM execution_queue
            WHERE status IN ('pending', 'dispatching')
            GROUP BY trigger_id
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def cancel_pending_entries(trigger_id: Optional[str] = None) -> int:
    """Bulk cancel pending entries, optionally filtered by trigger.

    Args:
        trigger_id: If provided, only cancel entries for this trigger.

    Returns:
        Number of entries cancelled.
    """
    with get_connection() as conn:
        if trigger_id:
            cursor = conn.execute(
                """
                UPDATE execution_queue
                SET status = 'cancelled', completed_at = datetime('now')
                WHERE status = 'pending' AND trigger_id = ?
                """,
                (trigger_id,),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE execution_queue
                SET status = 'cancelled', completed_at = datetime('now')
                WHERE status = 'pending'
                """
            )
        conn.commit()
        return cursor.rowcount


def cleanup_completed_entries(max_age_hours: int = 24) -> int:
    """Remove old completed/failed/cancelled entries from the queue.

    Args:
        max_age_hours: Entries older than this many hours are removed.

    Returns:
        Number of entries removed.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            DELETE FROM execution_queue
            WHERE status IN ('completed', 'failed', 'cancelled')
              AND completed_at < datetime('now', ? || ' hours')
            """,
            (f"-{max_age_hours}",),
        )
        conn.commit()
        return cursor.rowcount


def reset_stale_dispatching() -> int:
    """Reset entries stuck in 'dispatching' back to 'pending' for stale recovery.

    Called on server startup to recover entries that were being dispatched when
    the server crashed/restarted.

    Returns:
        Number of entries reset.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE execution_queue
            SET status = 'pending', dispatched_at = NULL
            WHERE status = 'dispatching'
            """
        )
        conn.commit()
        return cursor.rowcount
