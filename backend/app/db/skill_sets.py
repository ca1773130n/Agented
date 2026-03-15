"""Skill sets CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import generate_id

logger = logging.getLogger(__name__)


def _generate_skill_set_id() -> str:
    """Generate a unique skill set ID like 'sset-abc123'."""
    return generate_id("sset-", 6)


def create_skill_set(name: str, skill_ids_json: str = "[]") -> Optional[str]:
    """Create a new skill set. Returns the new ID on success, None on failure."""
    with get_connection() as conn:
        try:
            sset_id = _generate_skill_set_id()
            conn.execute(
                """
                INSERT INTO skill_sets (id, name, skill_ids)
                VALUES (?, ?, ?)
                """,
                (sset_id, name, skill_ids_json),
            )
            conn.commit()
            return sset_id
        except sqlite3.IntegrityError:
            return None


def get_all_skill_sets() -> List[dict]:
    """Get all skill sets ordered by creation date descending."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM skill_sets ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]


def get_skill_set(sset_id: str) -> Optional[dict]:
    """Get a single skill set by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM skill_sets WHERE id = ?", (sset_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_skill_set(
    sset_id: str,
    name: str = None,
    skill_ids_json: str = None,
) -> bool:
    """Update a skill set. Returns True on success."""
    updates = []
    values = []

    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if skill_ids_json is not None:
        updates.append("skill_ids = ?")
        values.append(skill_ids_json)

    if not updates:
        return False

    updates.append("updated_at = datetime('now')")
    values.append(sset_id)

    with get_connection() as conn:
        try:
            cursor = conn.execute(
                f"UPDATE skill_sets SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            return False


def delete_skill_set(sset_id: str) -> bool:
    """Delete a skill set. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM skill_sets WHERE id = ?", (sset_id,))
        conn.commit()
        return cursor.rowcount > 0
