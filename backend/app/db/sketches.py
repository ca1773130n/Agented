"""Sketch CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_sketch_id

logger = logging.getLogger(__name__)


# =============================================================================
# Sketch CRUD
# =============================================================================


def add_sketch(
    title: str,
    content: str = "",
    project_id: str = None,
) -> Optional[str]:
    """Add a new sketch. Returns sketch_id on success, None on failure."""
    with get_connection() as conn:
        try:
            sketch_id = _get_unique_sketch_id(conn)
            conn.execute(
                """
                INSERT INTO sketches (id, title, content, project_id)
                VALUES (?, ?, ?, ?)
            """,
                (sketch_id, title, content, project_id),
            )
            conn.commit()
            return sketch_id
        except sqlite3.IntegrityError:
            return None


def get_sketch(sketch_id: str) -> Optional[dict]:
    """Get a single sketch by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM sketches WHERE id = ?", (sketch_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_sketches(
    status: str = None,
    project_id: str = None,
) -> List[dict]:
    """Get all sketches with optional status and project_id filters."""
    query = "SELECT * FROM sketches"
    conditions = []
    values = []

    if status is not None:
        conditions.append("status = ?")
        values.append(status)
    if project_id is not None:
        conditions.append("project_id = ?")
        values.append(project_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY updated_at DESC"

    with get_connection() as conn:
        cursor = conn.execute(query, values)
        return [dict(row) for row in cursor.fetchall()]


def update_sketch(sketch_id: str, **kwargs) -> bool:
    """Update sketch fields. Returns True on success, False if no changes or not found."""
    allowed_fields = {
        "title",
        "content",
        "project_id",
        "status",
        "classification_json",
        "routing_json",
        "parent_sketch_id",
    }

    updates = []
    values = []

    for field in allowed_fields:
        if field in kwargs:
            updates.append(f"{field} = ?")
            values.append(kwargs[field])

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(sketch_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE sketches SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_sketch(sketch_id: str) -> bool:
    """Delete a sketch. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM sketches WHERE id = ?", (sketch_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_recent_classified_sketches(limit: int = 100) -> List[dict]:
    """Get recent sketches that have been classified (non-null classification_json)."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, title, content, classification_json
            FROM sketches
            WHERE classification_json IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT ?
        """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
