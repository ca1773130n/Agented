"""Execution tag CRUD operations.

Provides functions for managing execution tags and their assignments to
execution log entries for categorization and filtering.
"""

import logging
import sqlite3
from typing import Optional

from .connection import get_connection
from .ids import generate_id

logger = logging.getLogger(__name__)

ETAG_PREFIX = "etag-"
ETAG_ID_LENGTH = 6


def _generate_etag_id() -> str:
    """Generate a unique execution tag ID like 'etag-abc123'."""
    return generate_id(ETAG_PREFIX, ETAG_ID_LENGTH)


def list_tags() -> list[dict]:
    """List all execution tags with their assignment counts.

    Returns each tag with a computed ``execution_count`` field showing
    how many executions have been assigned that tag.
    """
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT t.id, t.name, t.color, t.created_at,
                   COUNT(a.execution_id) AS execution_count
            FROM execution_tags t
            LEFT JOIN execution_tag_assignments a ON t.id = a.tag_id
            GROUP BY t.id, t.name, t.color, t.created_at
            ORDER BY t.created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def create_tag(name: str, color: str = "blue") -> Optional[dict]:
    """Create a new execution tag.

    Args:
        name: Unique tag name.
        color: Tag color (e.g. 'blue', 'green', 'amber', 'red', 'purple').

    Returns:
        The created tag dict, or None on failure (e.g. duplicate name).
    """
    tag_id = _generate_etag_id()
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO execution_tags (id, name, color) VALUES (?, ?, ?)",
                (tag_id, name, color),
            )
            conn.commit()
            cursor = conn.execute(
                "SELECT id, name, color, created_at, 0 AS execution_count "
                "FROM execution_tags WHERE id = ?",
                (tag_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.IntegrityError:
            logger.warning("Failed to create execution tag (name conflict?): %s", name)
            return None


def delete_tag(tag_id: str) -> bool:
    """Delete an execution tag and all its assignments.

    Returns True if a tag was deleted, False if not found.
    """
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM execution_tags WHERE id = ?", (tag_id,))
        conn.commit()
        return cursor.rowcount > 0


def add_tag_to_execution(tag_id: str, execution_id: str) -> bool:
    """Assign a tag to an execution.

    Args:
        tag_id: The tag ID to assign.
        execution_id: The execution_id from execution_logs.

    Returns:
        True on success, False on failure (e.g. duplicate assignment or missing FK).
    """
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO execution_tag_assignments (tag_id, execution_id) "
                "VALUES (?, ?)",
                (tag_id, execution_id),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            logger.warning(
                "Failed to add tag %s to execution %s (FK violation?)", tag_id, execution_id
            )
            return False


def remove_tag_from_execution(tag_id: str, execution_id: str) -> bool:
    """Remove a tag assignment from an execution.

    Returns True if the assignment was removed, False if it did not exist.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM execution_tag_assignments WHERE tag_id = ? AND execution_id = ?",
            (tag_id, execution_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_executions_with_tags(
    limit: int = 50,
    offset: int = 0,
    tag_ids: Optional[list[str]] = None,
) -> list[dict]:
    """Fetch execution logs with their associated tag IDs.

    Each result row includes fields from execution_logs plus ``trigger_name``
    (from the joined triggers table) and a JSON-aggregated ``tags`` list of
    tag IDs assigned to that execution.

    Args:
        limit: Max number of results.
        offset: Pagination offset.
        tag_ids: Optional list of tag IDs to filter by (AND logic — only
            executions that have ALL of the given tags are returned).

    Returns:
        List of execution dicts with a ``tags`` key containing a list of tag_ids.
    """
    params: list = []

    if tag_ids:
        # Build a subquery that filters executions having ALL requested tags
        placeholders = ",".join("?" * len(tag_ids))
        having_clause = f"""
            HAVING COUNT(DISTINCT CASE WHEN a_filter.tag_id IN ({placeholders})
                         THEN a_filter.tag_id END) = ?
        """
        params.extend(tag_ids)
        params.append(len(tag_ids))
        filter_join = """
            LEFT JOIN execution_tag_assignments a_filter
                ON e.execution_id = a_filter.execution_id
        """
    else:
        having_clause = ""
        filter_join = ""

    query = f"""
        SELECT e.execution_id AS id,
               t.name AS trigger_name,
               e.trigger_id AS bot_id,
               e.started_at,
               e.duration_ms,
               e.status,
               SUBSTR(COALESCE(e.stdout_log, ''), 1, 200) AS log_snippet,
               GROUP_CONCAT(a.tag_id) AS tags_csv
        FROM execution_logs e
        LEFT JOIN triggers t ON e.trigger_id = t.id
        LEFT JOIN execution_tag_assignments a ON e.execution_id = a.execution_id
        {filter_join}
        GROUP BY e.execution_id
        {having_clause}
        ORDER BY e.started_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    with get_connection() as conn:
        cursor = conn.execute(query, params)
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            tags_csv = d.pop("tags_csv", None)
            d["tags"] = tags_csv.split(",") if tags_csv else []
            rows.append(d)
        return rows
