"""Bookmark database CRUD operations.

Bookmarks pin execution results with notes, tags, and deep-links
for display on bot profile pages.
"""

import logging
import sqlite3
from typing import Optional

from .connection import get_connection
from .ids import _get_unique_bookmark_id

logger = logging.getLogger(__name__)


def create_bookmark(
    execution_id: str,
    trigger_id: str,
    title: str,
    notes: str = "",
    tags: str = "",
    line_number: Optional[int] = None,
    deep_link: str = "",
    created_by: str = "system",
) -> Optional[str]:
    """Create a new bookmark. Returns bookmark_id on success, None on failure.

    Args:
        execution_id: The execution ID to bookmark.
        trigger_id: The trigger ID associated with the execution.
        title: Bookmark title.
        notes: Optional notes.
        tags: Comma-separated tag string.
        line_number: Optional line number for deep-link anchor.
        deep_link: Pre-computed deep-link URL.
        created_by: Who created this bookmark.

    Returns:
        The new bookmark ID, or None on failure.
    """
    with get_connection() as conn:
        try:
            bookmark_id = _get_unique_bookmark_id(conn)
            conn.execute(
                """INSERT INTO bookmarks
                   (id, execution_id, trigger_id, title, notes, tags,
                    line_number, deep_link, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    bookmark_id,
                    execution_id,
                    trigger_id,
                    title,
                    notes,
                    tags,
                    line_number,
                    deep_link,
                    created_by,
                ),
            )
            conn.commit()
            return bookmark_id
        except sqlite3.IntegrityError:
            logger.exception("Failed to create bookmark")
            return None


def get_bookmark(bookmark_id: str) -> Optional[dict]:
    """Get a single bookmark by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM bookmarks WHERE id = ?", (bookmark_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_bookmarks_for_trigger(trigger_id: str) -> list[dict]:
    """List all bookmarks for a given trigger (for bot profile page)."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM bookmarks WHERE trigger_id = ? ORDER BY created_at DESC",
            (trigger_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def list_bookmarks_for_execution(execution_id: str) -> list[dict]:
    """List all bookmarks for a given execution."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM bookmarks WHERE execution_id = ? ORDER BY created_at DESC",
            (execution_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def search_bookmarks(query: Optional[str] = None, tags: Optional[str] = None) -> list[dict]:
    """Search bookmarks by text query and/or tags.

    Args:
        query: Text search on title and notes (LIKE match).
        tags: Comma-separated tag string; matches bookmarks containing any of the tags.

    Returns:
        List of matching bookmarks.
    """
    conditions = []
    params = []

    if query:
        conditions.append("(title LIKE ? OR notes LIKE ?)")
        like_q = f"%{query}%"
        params.extend([like_q, like_q])

    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        tag_conditions = []
        for tag in tag_list:
            tag_conditions.append("tags LIKE ?")
            params.append(f"%{tag}%")
        if tag_conditions:
            conditions.append(f"({' OR '.join(tag_conditions)})")

    sql = "SELECT * FROM bookmarks"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC"

    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def update_bookmark(
    bookmark_id: str,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    tags: Optional[str] = None,
) -> bool:
    """Update a bookmark's title, notes, or tags. Returns True if updated."""
    fields = []
    params = []

    if title is not None:
        fields.append("title = ?")
        params.append(title)
    if notes is not None:
        fields.append("notes = ?")
        params.append(notes)
    if tags is not None:
        fields.append("tags = ?")
        params.append(tags)

    if not fields:
        return False

    params.append(bookmark_id)
    sql = f"UPDATE bookmarks SET {', '.join(fields)} WHERE id = ?"

    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.rowcount > 0


def delete_bookmark(bookmark_id: str) -> bool:
    """Delete a bookmark by ID. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))
        conn.commit()
        return cursor.rowcount > 0
