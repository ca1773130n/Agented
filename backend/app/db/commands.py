"""Commands CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def add_command(
    name: str,
    description: Optional[str] = None,
    content: Optional[str] = None,
    arguments: Optional[str] = None,
    enabled: bool = True,
    project_id: Optional[str] = None,
    source_path: Optional[str] = None,
) -> Optional[int]:
    """Add a new command."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO commands (name, description, content, arguments, enabled, project_id, source_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    name,
                    description,
                    content,
                    arguments,
                    1 if enabled else 0,
                    project_id,
                    source_path,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Database error in add_command: {e}")
            return None


def update_command(
    command_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    content: Optional[str] = None,
    arguments: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> bool:
    """Update an existing command."""
    with get_connection() as conn:
        updates = []
        values = []
        if name is not None:
            updates.append("name = ?")
            values.append(name)
        if description is not None:
            updates.append("description = ?")
            values.append(description)
        if content is not None:
            updates.append("content = ?")
            values.append(content)
        if arguments is not None:
            updates.append("arguments = ?")
            values.append(arguments)
        if enabled is not None:
            updates.append("enabled = ?")
            values.append(1 if enabled else 0)
        if not updates:
            return False
        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(command_id)
        cursor = conn.execute(f"UPDATE commands SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_command(command_id: int) -> bool:
    """Delete a command."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM commands WHERE id = ?", (command_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_command(command_id: int) -> Optional[dict]:
    """Get a command by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM commands WHERE id = ?", (command_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_commands(
    project_id: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[dict]:
    """Get all commands, optionally filtered by project, with optional pagination."""
    with get_connection() as conn:
        params: list = []
        if project_id:
            sql = "SELECT * FROM commands WHERE project_id = ? OR project_id IS NULL ORDER BY name ASC"
            params.append(project_id)
        else:
            sql = "SELECT * FROM commands ORDER BY name ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def count_commands(project_id: Optional[str] = None) -> int:
    """Count total number of commands, optionally filtered by project."""
    with get_connection() as conn:
        if project_id:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM commands WHERE project_id = ? OR project_id IS NULL",
                (project_id,),
            )
        else:
            cursor = conn.execute("SELECT COUNT(*) FROM commands")
        return cursor.fetchone()[0]


def get_commands_by_project(project_id: str) -> List[dict]:
    """Get commands for a specific project only."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM commands WHERE project_id = ? ORDER BY name ASC",
            (project_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
