"""Replay comparison database CRUD operations.

Stores relationships between original and replayed executions
for A/B comparison and regression detection.
"""

import logging
from typing import Optional

from .connection import get_connection
from .ids import _generate_short_id

logger = logging.getLogger(__name__)

REPLAY_ID_PREFIX = "rpl-"
REPLAY_ID_LENGTH = 6


def _generate_replay_id() -> str:
    """Generate a unique replay comparison ID with rpl- prefix."""
    return f"{REPLAY_ID_PREFIX}{_generate_short_id(REPLAY_ID_LENGTH)}"


def create_replay_comparison(
    original_execution_id: str,
    replay_execution_id: str,
    notes: Optional[str] = None,
) -> Optional[str]:
    """Create a replay comparison record. Returns comparison_id on success, None on failure.

    IMPORTANT: This must be called BEFORE starting the replay subprocess
    so the relationship survives crashes.
    """
    with get_connection() as conn:
        try:
            comparison_id = _generate_replay_id()
            conn.execute(
                """INSERT INTO replay_comparisons
                   (id, original_execution_id, replay_execution_id, notes)
                   VALUES (?, ?, ?, ?)""",
                (comparison_id, original_execution_id, replay_execution_id, notes),
            )
            conn.commit()
            return comparison_id
        except Exception as e:
            logger.error("Failed to create replay comparison: %s", e)
            return None


def get_replay_comparison(comparison_id: str) -> Optional[dict]:
    """Get a single replay comparison by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM replay_comparisons WHERE id = ?", (comparison_id,)
        ).fetchone()
        if row:
            return dict(row)
        return None


def get_replay_comparisons_for_execution(execution_id: str) -> list:
    """Get all comparisons where execution_id is either the original or replay."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM replay_comparisons
               WHERE original_execution_id = ? OR replay_execution_id = ?
               ORDER BY created_at DESC""",
            (execution_id, execution_id),
        ).fetchall()
        return [dict(row) for row in rows]


def get_all_replay_comparisons(limit: int = 50, offset: int = 0) -> list:
    """Get all replay comparisons with pagination."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM replay_comparisons
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]
