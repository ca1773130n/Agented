"""Viewer comments database CRUD operations.

Inline comments on execution log lines, anchored to stdout line numbers.
Persisted to SQLite for durability beyond SSE sessions.
"""

import logging
import random
import string
import sqlite3
from typing import Optional

from .connection import get_connection

logger = logging.getLogger(__name__)

COMMENT_ID_PREFIX = "cmt-"
COMMENT_ID_LENGTH = 6


def _generate_comment_id() -> str:
    """Generate a comment ID with cmt- prefix and 6-char random suffix."""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=COMMENT_ID_LENGTH))
    return f"{COMMENT_ID_PREFIX}{suffix}"


def create_viewer_comment(
    execution_id: str,
    viewer_id: str,
    viewer_name: str,
    line_number: int,
    content: str,
) -> Optional[str]:
    """Create a new inline comment. Returns comment_id on success, None on failure.

    Args:
        execution_id: The execution to comment on.
        viewer_id: Who is posting the comment.
        viewer_name: Display name of the commenter.
        line_number: Stdout line number to anchor the comment.
        content: Comment text.

    Returns:
        The new comment ID, or None on failure.
    """
    with get_connection() as conn:
        try:
            comment_id = _generate_comment_id()
            conn.execute(
                """INSERT INTO viewer_comments
                   (id, execution_id, viewer_id, viewer_name, line_number, content)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (comment_id, execution_id, viewer_id, viewer_name, line_number, content),
            )
            conn.commit()
            return comment_id
        except sqlite3.IntegrityError:
            logger.exception("Failed to create viewer comment")
            return None


def get_comments_for_execution(execution_id: str) -> list[dict]:
    """Get all comments for an execution, ordered by line_number then created_at."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM viewer_comments WHERE execution_id = ? "
            "ORDER BY line_number ASC, created_at ASC",
            (execution_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_comment(comment_id: str) -> Optional[dict]:
    """Get a single comment by ID."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM viewer_comments WHERE id = ?", (comment_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def delete_comment(comment_id: str) -> bool:
    """Delete a comment by ID. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM viewer_comments WHERE id = ?", (comment_id,)
        )
        conn.commit()
        return cursor.rowcount > 0


def get_comments_for_line(execution_id: str, line_number: int) -> list[dict]:
    """Get all comments for a specific line in an execution."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM viewer_comments WHERE execution_id = ? AND line_number = ? "
            "ORDER BY created_at ASC",
            (execution_id, line_number),
        )
        return [dict(row) for row in cursor.fetchall()]
