"""Conversation branch and message CRUD operations.

Tree-structured messages for conversation branching based on
ContextBranch paper (arXiv:2512.13914). Each message has a
parent_message_id forming a tree, with branches navigable independently.
"""

import logging
from typing import Optional

from .connection import get_connection
from .ids import _generate_short_id

logger = logging.getLogger(__name__)

BRANCH_ID_PREFIX = "branch-"
BRANCH_ID_LENGTH = 6

MSG_ID_PREFIX = "msg-"
MSG_ID_LENGTH = 8


def _generate_branch_id() -> str:
    """Generate a unique branch ID with branch- prefix."""
    return f"{BRANCH_ID_PREFIX}{_generate_short_id(BRANCH_ID_LENGTH)}"


def _generate_msg_id() -> str:
    """Generate a unique message ID with msg- prefix."""
    return f"{MSG_ID_PREFIX}{_generate_short_id(MSG_ID_LENGTH)}"


def create_branch(
    conversation_id: str,
    parent_branch_id: Optional[str] = None,
    fork_message_id: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[str]:
    """Create a conversation branch. Returns branch_id on success."""
    with get_connection() as conn:
        try:
            branch_id = _generate_branch_id()
            conn.execute(
                """INSERT INTO conversation_branches
                   (id, conversation_id, parent_branch_id, fork_message_id, name)
                   VALUES (?, ?, ?, ?, ?)""",
                (branch_id, conversation_id, parent_branch_id, fork_message_id, name),
            )
            conn.commit()
            return branch_id
        except Exception as e:
            logger.error("Failed to create branch: %s", e)
            return None


def get_branch(branch_id: str) -> Optional[dict]:
    """Get a single branch by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM conversation_branches WHERE id = ?", (branch_id,)
        ).fetchone()
        return dict(row) if row else None


def get_branches_for_conversation(conversation_id: str) -> list[dict]:
    """Get all branches for a conversation."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM conversation_branches
               WHERE conversation_id = ?
               ORDER BY created_at ASC""",
            (conversation_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def update_branch_status(branch_id: str, status: str) -> bool:
    """Update a branch's status. Returns True on success."""
    with get_connection() as conn:
        try:
            conn.execute(
                "UPDATE conversation_branches SET status = ? WHERE id = ?",
                (status, branch_id),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error("Failed to update branch status: %s", e)
            return False


def create_message(
    conversation_id: str,
    branch_id: str,
    role: str,
    content: str,
    parent_message_id: Optional[str] = None,
    message_index: int = 0,
) -> Optional[str]:
    """Create a message in a branch. Returns message_id on success."""
    with get_connection() as conn:
        try:
            message_id = _generate_msg_id()
            conn.execute(
                """INSERT INTO conversation_messages
                   (id, conversation_id, branch_id, parent_message_id,
                    message_index, role, content)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    message_id,
                    conversation_id,
                    branch_id,
                    parent_message_id,
                    message_index,
                    role,
                    content,
                ),
            )
            conn.commit()
            return message_id
        except Exception as e:
            logger.error("Failed to create message: %s", e)
            return None


def get_messages_for_branch(branch_id: str, conversation_id: str) -> list[dict]:
    """Get all messages for a branch, ordered by message_index."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM conversation_messages
               WHERE branch_id = ? AND conversation_id = ?
               ORDER BY message_index ASC""",
            (branch_id, conversation_id),
        ).fetchall()
        return [dict(row) for row in rows]


def get_message(message_id: str) -> Optional[dict]:
    """Get a single message by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM conversation_messages WHERE id = ?", (message_id,)
        ).fetchone()
        return dict(row) if row else None


def count_messages_for_branch(branch_id: str) -> int:
    """Count messages in a branch."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM conversation_messages WHERE branch_id = ?",
            (branch_id,),
        ).fetchone()
        return row[0] if row else 0
