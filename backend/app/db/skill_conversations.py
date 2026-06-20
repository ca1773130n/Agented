"""CRUD for ``skill_conversations`` — durable storage for the
``/skills/new`` wizard's chat history (v0.7.78).

The ``SkillConversationService`` keeps a hot in-memory cache for
the live SSE stream, but every message append writes through here
so a backend restart or wizard refresh can resume the conversation
instead of starting fresh.

Schema:
* ``messages_json`` is the full ``[{role, content, timestamp}]``
  array as JSON. Same shape the service's in-memory dict held.
* ``status`` is ``active`` | ``finalized`` | ``abandoned``.
* ``user_id`` follows the pattern from other owned-entity tables
  (rules, hooks, etc.); falls back to the synthetic legacy user
  when auth isn't surfaced (most local-dev sessions).
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


def create_skill_conversation(
    conv_id: str,
    messages: list,
    user_id: Optional[str] = None,
) -> None:
    """Insert a brand-new conversation row.

    ``messages`` is the initial array (system prompt + kickoff
    user message); the service appends to it via
    ``upsert_skill_conversation`` as the chat progresses.
    """
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO skill_conversations
                (id, user_id, status, messages_json)
            VALUES (?, ?, 'active', ?)
            """,
            (conv_id, user_id, json.dumps(messages, ensure_ascii=False)),
        )
        conn.commit()


def upsert_skill_conversation(
    conv_id: str,
    messages: list,
    *,
    status: Optional[str] = None,
) -> None:
    """Write through the latest message list (and optionally a
    new status) for ``conv_id``. Idempotent — used after every
    ``send_message`` + at finalize / abandon time.
    """
    with get_connection() as conn:
        if status is not None:
            conn.execute(
                """
                UPDATE skill_conversations
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
                UPDATE skill_conversations
                SET messages_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (json.dumps(messages, ensure_ascii=False), conv_id),
            )
        conn.commit()


def get_skill_conversation(conv_id: str) -> Optional[dict]:
    """Fetch by id, or None if absent."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM skill_conversations WHERE id = ?",
            (conv_id,),
        )
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None


def list_active_skill_conversations(user_id: Optional[str] = None, limit: int = 10) -> List[dict]:
    """Most-recent ``active`` conversations.

    Filter semantics (v0.7.78 — codex BLOCK 1):

      * ``user_id`` set → only rows whose ``user_id`` matches.
      * ``user_id is None`` → only rows whose ``user_id IS NULL``
        (legacy / bootstrap-mode conversations). The previous
        "no filter → return everything" behaviour leaked every
        operator's active convs to anonymous callers.

    Callers that genuinely want every row (e.g. admin sweepers)
    must query the table directly.
    """
    with get_connection() as conn:
        if user_id:
            cursor = conn.execute(
                """
                SELECT * FROM skill_conversations
                WHERE status = 'active' AND user_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT * FROM skill_conversations
                WHERE status = 'active' AND user_id IS NULL
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        return [_row_to_dict(row) for row in cursor.fetchall()]


def delete_skill_conversation(conv_id: str) -> bool:
    """Delete a conversation by id. Returns True if a row was
    deleted, False if no such id existed.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM skill_conversations WHERE id = ?",
            (conv_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
