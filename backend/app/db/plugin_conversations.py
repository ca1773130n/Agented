"""CRUD for ``plugin_conversations`` — durable storage for the
``/plugins/new`` wizard's chat history (v0.7.83).

Schema and semantics mirror ``skill_conversations`` (v0.7.78) so
``PluginConversationService`` can adopt the same write-through
hot-cache pattern that gave ``/skills/new`` survival across page
refresh + backend restart.

Schema:
* ``messages_json`` is the full ``[{role, content, timestamp}]``
  array as JSON.
* ``status`` is ``active`` | ``finalized`` | ``abandoned``.
* ``user_id`` enables multi-tenant scoping for list + ownership
  checks. ``None`` means bootstrap mode (no auth configured).
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "status": row["status"],
        "messages": json.loads(row["messages_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_plugin_conversation(
    conv_id: str,
    messages: list,
    user_id: Optional[str] = None,
) -> None:
    """Insert a brand-new plugin conversation row."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO plugin_conversations
                (id, user_id, status, messages_json)
            VALUES (?, ?, 'active', ?)
            """,
            (conv_id, user_id, json.dumps(messages, ensure_ascii=False)),
        )
        conn.commit()


def upsert_plugin_conversation(
    conv_id: str,
    messages: list,
    *,
    status: Optional[str] = None,
) -> None:
    """Write through the latest messages (and optionally a new
    status). Idempotent — used after every ``send_message`` and
    at finalize / abandon time.
    """
    with get_connection() as conn:
        if status is not None:
            conn.execute(
                """
                UPDATE plugin_conversations
                SET messages_json = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (json.dumps(messages, ensure_ascii=False), status, conv_id),
            )
        else:
            conn.execute(
                """
                UPDATE plugin_conversations
                SET messages_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (json.dumps(messages, ensure_ascii=False), conv_id),
            )
        conn.commit()


def get_plugin_conversation(conv_id: str) -> Optional[dict]:
    """Fetch by id, or None if absent."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM plugin_conversations WHERE id = ?",
            (conv_id,),
        )
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None


def list_active_plugin_conversations(user_id: Optional[str] = None, limit: int = 10) -> List[dict]:
    """Most-recent ``active`` plugin conversations, scoped by user_id.

    Filter semantics mirror ``list_active_skill_conversations``:
    ``user_id`` None scopes to ``user_id IS NULL`` so a bootstrap
    caller doesn't see every operator's wizard sessions.
    """
    with get_connection() as conn:
        if user_id:
            cursor = conn.execute(
                """
                SELECT * FROM plugin_conversations
                WHERE status = 'active' AND user_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT * FROM plugin_conversations
                WHERE status = 'active' AND user_id IS NULL
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        return [_row_to_dict(row) for row in cursor.fetchall()]


def delete_plugin_conversation(conv_id: str) -> bool:
    """Delete a conversation by id. Returns True if a row was
    deleted, False if no such id existed.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM plugin_conversations WHERE id = ?",
            (conv_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
