"""Hooks CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def add_hook(
    name: str,
    event: str,
    description: Optional[str] = None,
    content: Optional[str] = None,
    enabled: bool = True,
    project_id: Optional[str] = None,
    source_path: Optional[str] = None,
) -> Optional[int]:
    """Add a new hook."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO hooks (name, event, description, content, enabled, project_id, source_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (name, event, description, content, 1 if enabled else 0, project_id, source_path),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Database error in add_hook: {e}")
            return None


def update_hook(
    hook_id: int,
    name: Optional[str] = None,
    event: Optional[str] = None,
    description: Optional[str] = None,
    content: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> bool:
    """Update an existing hook."""
    with get_connection() as conn:
        updates = []
        values = []
        if name is not None:
            updates.append("name = ?")
            values.append(name)
        if event is not None:
            updates.append("event = ?")
            values.append(event)
        if description is not None:
            updates.append("description = ?")
            values.append(description)
        if content is not None:
            updates.append("content = ?")
            values.append(content)
        if enabled is not None:
            updates.append("enabled = ?")
            values.append(1 if enabled else 0)
        if not updates:
            return False
        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(hook_id)
        cursor = conn.execute(f"UPDATE hooks SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_hook(hook_id: int) -> bool:
    """Delete a hook."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM hooks WHERE id = ?", (hook_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_hook(hook_id: int) -> Optional[dict]:
    """Get a hook by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM hooks WHERE id = ?", (hook_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_hooks(
    project_id: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[dict]:
    """Get all hooks, optionally filtered by project, with optional pagination."""
    with get_connection() as conn:
        params: list = []
        if project_id:
            sql = "SELECT * FROM hooks WHERE project_id = ? OR project_id IS NULL ORDER BY name ASC"
            params.append(project_id)
        else:
            sql = "SELECT * FROM hooks ORDER BY name ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def count_hooks(project_id: Optional[str] = None) -> int:
    """Count total number of hooks, optionally filtered by project."""
    with get_connection() as conn:
        if project_id:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM hooks WHERE project_id = ? OR project_id IS NULL",
                (project_id,),
            )
        else:
            cursor = conn.execute("SELECT COUNT(*) FROM hooks")
        return cursor.fetchone()[0]


def get_hooks_by_project(project_id: str) -> List[dict]:
    """Get hooks for a specific project only."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM hooks WHERE project_id = ? ORDER BY name ASC",
            (project_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_hooks_by_event(event: str) -> List[dict]:
    """Get hooks by event type."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM hooks WHERE event = ? AND enabled = 1 ORDER BY name ASC",
            (event,),
        )
        return [dict(row) for row in cursor.fetchall()]
