"""Prompt snippet CRUD operations.

Manages reusable prompt fragments that can be referenced in trigger
prompt templates using {{snippet_name}} syntax.
"""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_snippet_id

logger = logging.getLogger(__name__)


def create_snippet(
    name: str,
    content: str,
    description: str = "",
    is_global: bool = True,
) -> Optional[str]:
    """Add a new prompt snippet. Returns snippet_id on success, None on failure."""
    with get_connection() as conn:
        try:
            snippet_id = _get_unique_snippet_id(conn)
            conn.execute(
                """
                INSERT INTO prompt_snippets (id, name, content, description, is_global)
                VALUES (?, ?, ?, ?, ?)
                """,
                (snippet_id, name, content, description, 1 if is_global else 0),
            )
            conn.commit()
            return snippet_id
        except sqlite3.IntegrityError:
            return None


def get_snippet(snippet_id: str) -> Optional[dict]:
    """Get a single snippet by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM prompt_snippets WHERE id = ?", (snippet_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_snippet_by_name(name: str) -> Optional[dict]:
    """Get a snippet by its exact name."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM prompt_snippets WHERE name = ?", (name,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_snippets() -> List[dict]:
    """Get all prompt snippets."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM prompt_snippets ORDER BY created_at ASC")
        return [dict(row) for row in cursor.fetchall()]


def update_snippet(
    snippet_id: str,
    name: str = None,
    content: str = None,
    description: str = None,
) -> bool:
    """Update a prompt snippet. Returns True on success."""
    updates = []
    values = []

    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if content is not None:
        updates.append("content = ?")
        values.append(content)
    if description is not None:
        updates.append("description = ?")
        values.append(description)

    if not updates:
        return False

    updates.append("updated_at = datetime('now')")
    values.append(snippet_id)

    with get_connection() as conn:
        try:
            cursor = conn.execute(
                f"UPDATE prompt_snippets SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.IntegrityError:
            return False


def delete_snippet(snippet_id: str) -> bool:
    """Delete a prompt snippet. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM prompt_snippets WHERE id = ?", (snippet_id,))
        conn.commit()
        return cursor.rowcount > 0
