"""User skills CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def add_user_skill(
    skill_name: str,
    skill_path: str,
    description: str = None,
    enabled: int = 1,
    selected_for_harness: int = 0,
    metadata: str = None,
) -> Optional[int]:
    """Add a user skill. Returns id on success, None on failure."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO user_skills (skill_name, skill_path, description, enabled, selected_for_harness, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (skill_name, skill_path, description, enabled, selected_for_harness, metadata),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def update_user_skill(
    skill_id: int,
    skill_name: str = None,
    skill_path: str = None,
    description: str = None,
    enabled: int = None,
    selected_for_harness: int = None,
    metadata: str = None,
) -> bool:
    """Update a user skill. Returns True on success."""
    updates = []
    values = []

    if skill_name is not None:
        updates.append("skill_name = ?")
        values.append(skill_name)
    if skill_path is not None:
        updates.append("skill_path = ?")
        values.append(skill_path)
    if description is not None:
        updates.append("description = ?")
        values.append(description)
    if enabled is not None:
        updates.append("enabled = ?")
        values.append(enabled)
    if selected_for_harness is not None:
        updates.append("selected_for_harness = ?")
        values.append(selected_for_harness)
    if metadata is not None:
        updates.append("metadata = ?")
        values.append(metadata)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(skill_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE user_skills SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_user_skill(skill_id: int) -> bool:
    """Delete a user skill. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM user_skills WHERE id = ?", (skill_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_user_skill(skill_id: int) -> Optional[dict]:
    """Get a single user skill by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM user_skills WHERE id = ?", (skill_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_user_skill_by_name(skill_name: str) -> Optional[dict]:
    """Get a user skill by name."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM user_skills WHERE skill_name = ?", (skill_name,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_user_skills() -> List[dict]:
    """Get all user skills."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM user_skills ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]


def get_enabled_user_skills() -> List[dict]:
    """Get all enabled user skills."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM user_skills WHERE enabled = 1 ORDER BY skill_name ASC")
        return [dict(row) for row in cursor.fetchall()]


def get_harness_skills() -> List[dict]:
    """Get all skills selected for harness integration."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM user_skills WHERE selected_for_harness = 1 ORDER BY skill_name ASC"
        )
        return [dict(row) for row in cursor.fetchall()]


def toggle_skill_harness(skill_id: int, selected: bool) -> bool:
    """Toggle a skill's harness selection. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE user_skills SET selected_for_harness = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if selected else 0, skill_id),
        )
        conn.commit()
        return cursor.rowcount > 0
