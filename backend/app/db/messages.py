"""Agent message CRUD operations for inter-agent messaging."""

import datetime
import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_message_id

logger = logging.getLogger(__name__)


def add_agent_message(
    from_agent_id: str,
    to_agent_id: str = None,
    message_type: str = "message",
    priority: str = "normal",
    subject: str = None,
    content: str = "",
    ttl_seconds: int = None,
    expires_at: str = None,
) -> Optional[str]:
    """Add a new agent message. Returns msg-* ID on success, None on failure."""
    with get_connection() as conn:
        try:
            msg_id = _get_unique_message_id(conn)

            # Calculate expires_at from ttl_seconds if provided and expires_at not set
            if ttl_seconds and not expires_at:
                expires_at = (
                    datetime.datetime.now(datetime.timezone.utc)
                    + datetime.timedelta(seconds=ttl_seconds)
                ).strftime("%Y-%m-%d %H:%M:%S")

            conn.execute(
                """
                INSERT INTO agent_messages
                (id, from_agent_id, to_agent_id, message_type, priority,
                 subject, content, status, ttl_seconds, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
                (
                    msg_id,
                    from_agent_id,
                    to_agent_id,
                    message_type,
                    priority,
                    subject,
                    content,
                    ttl_seconds,
                    expires_at,
                ),
            )
            conn.commit()
            return msg_id
        except sqlite3.IntegrityError:
            return None


def get_inbox_messages(agent_id: str, status: str = None) -> List[dict]:
    """Get inbox messages for an agent (to_agent_id matches).

    Excludes expired messages. Optionally filter by status.
    Returns messages ordered by created_at DESC.
    """
    with get_connection() as conn:
        query = (
            "SELECT * FROM agent_messages WHERE to_agent_id = ? "
            "AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)"
        )
        params: list = [agent_id]

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC"
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_outbox_messages(agent_id: str) -> List[dict]:
    """Get outbox messages for an agent (from_agent_id matches).

    Returns messages ordered by created_at DESC.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM agent_messages WHERE from_agent_id = ? ORDER BY created_at DESC",
            (agent_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_pending_messages(agent_id: str) -> List[dict]:
    """Get pending messages for an agent, ordered by priority then created_at.

    Excludes expired messages. Priority ordering: high(0), normal(1), low(2).
    Used by prompt injection to deliver messages to sleeping agents.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM agent_messages
            WHERE to_agent_id = ? AND status = 'pending'
            AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            ORDER BY
                CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 WHEN 'low' THEN 2 END ASC,
                created_at ASC
        """,
            (agent_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_message_status(message_id: str, status: str) -> bool:
    """Update a message's status. Sets delivered_at or read_at timestamp as appropriate.

    Returns True if the message was updated, False if not found.
    """
    with get_connection() as conn:
        if status == "delivered":
            cursor = conn.execute(
                "UPDATE agent_messages SET status = ?, delivered_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, message_id),
            )
        elif status == "read":
            cursor = conn.execute(
                "UPDATE agent_messages SET status = ?, read_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, message_id),
            )
        else:
            cursor = conn.execute(
                "UPDATE agent_messages SET status = ? WHERE id = ?",
                (status, message_id),
            )
        conn.commit()
        return cursor.rowcount > 0


def expire_stale_messages() -> int:
    """Mark messages past their expires_at as expired.

    Only affects pending and delivered messages.
    Returns the number of messages expired.
    """
    with get_connection() as conn:
        cursor = conn.execute("""
            UPDATE agent_messages SET status = 'expired'
            WHERE status IN ('pending', 'delivered')
            AND expires_at IS NOT NULL
            AND expires_at < CURRENT_TIMESTAMP
        """)
        conn.commit()
        return cursor.rowcount


def batch_add_broadcast_messages(
    from_agent_id: str,
    recipients: List[str],
    message_type: str = "broadcast",
    priority: str = "normal",
    subject: str = None,
    content: str = "",
    ttl_seconds: int = None,
    expires_at: str = None,
) -> List[str]:
    """Create individual messages for each recipient in a single transaction.

    Used for broadcast messages. Returns list of message IDs.
    """
    # Calculate expires_at from ttl_seconds if provided and expires_at not set
    if ttl_seconds and not expires_at:
        expires_at = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=ttl_seconds)
        ).strftime("%Y-%m-%d %H:%M:%S")

    msg_ids = []
    with get_connection() as conn:
        for recipient_id in recipients:
            msg_id = _get_unique_message_id(conn)
            conn.execute(
                """
                INSERT INTO agent_messages
                (id, from_agent_id, to_agent_id, message_type, priority,
                 subject, content, status, ttl_seconds, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
                (
                    msg_id,
                    from_agent_id,
                    recipient_id,
                    message_type,
                    priority,
                    subject,
                    content,
                    ttl_seconds,
                    expires_at,
                ),
            )
            msg_ids.append(msg_id)
        conn.commit()
    return msg_ids
