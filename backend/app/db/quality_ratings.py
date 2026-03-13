"""Quality ratings database CRUD operations.

Stores per-execution quality ratings (1-5 stars) with optional feedback text.
Supports per-trigger aggregation for the quality scoring dashboard.
"""

import json
import logging
import sqlite3
from typing import Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def upsert_quality_rating(
    execution_id: str,
    trigger_id: Optional[str],
    rating: int,
    feedback: str = "",
) -> dict:
    """Insert or update a quality rating for an execution.

    Args:
        execution_id: The execution ID to rate (must exist in execution_logs).
        trigger_id: The trigger ID associated with the execution (may be None).
        rating: Integer score 1–5 (inclusive).
        feedback: Optional free-text feedback.

    Returns:
        The upserted rating row as a dict.

    Raises:
        ValueError: If rating is not between 1 and 5.
        sqlite3.IntegrityError: If execution_id does not reference a valid execution.
    """
    if not (1 <= rating <= 5):
        raise ValueError(f"rating must be between 1 and 5, got {rating!r}")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO execution_quality_ratings (execution_id, trigger_id, rating, feedback)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(execution_id) DO UPDATE SET
                trigger_id = excluded.trigger_id,
                rating = excluded.rating,
                feedback = excluded.feedback,
                rated_at = CURRENT_TIMESTAMP
            """,
            (execution_id, trigger_id, rating, feedback),
        )
        conn.commit()
        cursor = conn.execute(
            "SELECT * FROM execution_quality_ratings WHERE execution_id = ?",
            (execution_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else {}


def get_quality_entries(
    trigger_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List quality rating entries with execution log preview.

    Args:
        trigger_id: Optional filter by trigger ID.
        limit: Max results to return (default 50).
        offset: Pagination offset.

    Returns:
        List of dicts with rating fields + execution preview columns.
    """
    params: list = []
    where = "WHERE 1=1"
    if trigger_id is not None:
        where += " AND r.trigger_id = ?"
        params.append(trigger_id)

    query = f"""
        SELECT
            r.id,
            r.execution_id,
            r.trigger_id,
            r.rating,
            r.feedback,
            r.rated_at,
            e.started_at as timestamp,
            COALESCE(SUBSTR(e.stdout_log, 1, 200), '') as output_preview,
            t.name as trigger_name
        FROM execution_quality_ratings r
        LEFT JOIN execution_logs e ON r.execution_id = e.execution_id
        LEFT JOIN triggers t ON r.trigger_id = t.id
        {where}
        ORDER BY r.rated_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    with get_connection() as conn:
        try:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error("Database error in get_quality_entries: %s", e)
            return []


def get_bot_quality_stats() -> list[dict]:
    """Aggregate quality stats per trigger.

    Returns list of dicts with:
        trigger_id, trigger_name, avg_score, total_rated,
        thumbs_up (rating >= 4), thumbs_down (rating <= 2),
        recent_scores (up to last 10, JSON array), trend ('up'|'down'|'stable')
    """
    with get_connection() as conn:
        try:
            # Aggregate stats per trigger
            cursor = conn.execute("""
                SELECT
                    r.trigger_id,
                    t.name as trigger_name,
                    ROUND(AVG(r.rating), 2) as avg_score,
                    COUNT(*) as total_rated,
                    SUM(CASE WHEN r.rating >= 4 THEN 1 ELSE 0 END) as thumbs_up,
                    SUM(CASE WHEN r.rating <= 2 THEN 1 ELSE 0 END) as thumbs_down
                FROM execution_quality_ratings r
                LEFT JOIN triggers t ON r.trigger_id = t.id
                GROUP BY r.trigger_id
                ORDER BY total_rated DESC
            """)
            stats = [dict(row) for row in cursor.fetchall()]

            # Attach recent scores and compute trend
            for stat in stats:
                tid = stat["trigger_id"]
                recent_cursor = conn.execute(
                    """
                    SELECT rating FROM execution_quality_ratings
                    WHERE trigger_id = ?
                    ORDER BY rated_at DESC
                    LIMIT 10
                    """,
                    (tid,),
                )
                recent = [row[0] for row in recent_cursor.fetchall()]
                stat["recent_scores"] = recent

                # Trend: compare first half vs second half of recent scores
                if len(recent) >= 4:
                    half = len(recent) // 2
                    # recent is DESC so recent[:half] is newest
                    newer_avg = sum(recent[:half]) / half
                    older_avg = sum(recent[half:]) / (len(recent) - half)
                    if newer_avg > older_avg + 0.2:
                        stat["trend"] = "up"
                    elif newer_avg < older_avg - 0.2:
                        stat["trend"] = "down"
                    else:
                        stat["trend"] = "stable"
                else:
                    stat["trend"] = "stable"

            return stats
        except sqlite3.Error as e:
            logger.error("Database error in get_bot_quality_stats: %s", e)
            return []
