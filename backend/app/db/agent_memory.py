"""Agent memory store — threads, messages, working memory, and semantic recall."""

import json
import logging

from .connection import get_connection, safe_set_clause
from .ids import generate_memory_message_id, generate_thread_id

logger = logging.getLogger(__name__)


# --- Thread CRUD ---


def create_thread(
    resource_id: str,
    resource_type: str = "agent",
    title: str | None = None,
    metadata: dict | None = None,
) -> dict:
    thread_id = generate_thread_id()
    meta_json = json.dumps(metadata) if metadata else None
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO memory_threads (id, resource_id, resource_type, title, metadata)
               VALUES (?, ?, ?, ?, ?)""",
            (thread_id, resource_id, resource_type, title, meta_json),
        )
        conn.commit()
        cursor = conn.execute(
            "SELECT * FROM memory_threads WHERE id = ?", (thread_id,)
        )
        row = cursor.fetchone()
        return _thread_row_to_dict(row)


def get_thread(thread_id: str) -> dict | None:
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM memory_threads WHERE id = ?", (thread_id,))
        row = cursor.fetchone()
        return _thread_row_to_dict(row) if row else None


def list_threads(
    resource_id: str,
    resource_type: str = "agent",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.execute(
            """SELECT * FROM memory_threads
               WHERE resource_id = ? AND resource_type = ?
               ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
            (resource_id, resource_type, limit, offset),
        )
        return [_thread_row_to_dict(row) for row in cursor.fetchall()]


def count_threads(resource_id: str, resource_type: str = "agent") -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM memory_threads WHERE resource_id = ? AND resource_type = ?",
            (resource_id, resource_type),
        )
        return cursor.fetchone()[0]


def update_thread(
    thread_id: str, title: str | None = None, metadata: dict | None = None
) -> dict | None:
    with get_connection() as conn:
        updates = ["updated_at = CURRENT_TIMESTAMP"]
        params: list = []
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(json.dumps(metadata))
        params.append(thread_id)
        conn.execute(
            f"UPDATE memory_threads SET {safe_set_clause(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        return get_thread(thread_id)


def delete_thread(thread_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM memory_threads WHERE id = ?", (thread_id,))
        conn.commit()
        return cursor.rowcount > 0


# --- Message CRUD ---


def save_messages(thread_id: str, messages: list[dict]) -> list[dict]:
    # Pre-generate IDs and build tuples for batch insert
    rows = []
    saved = []
    for msg in messages:
        msg_id = generate_memory_message_id()
        meta_json = json.dumps(msg.get("metadata")) if msg.get("metadata") else None
        rows.append((
            msg_id, thread_id, msg["role"], msg["content"],
            msg.get("type", "text"), meta_json,
        ))
        saved.append({"id": msg_id, **msg})
    with get_connection() as conn:
        conn.executemany(
            """INSERT INTO memory_messages (id, thread_id, role, content, type, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.execute(
            "UPDATE memory_threads SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (thread_id,),
        )
        conn.commit()
    return saved


def get_messages(
    thread_id: str,
    limit: int = 50,
    before_id: str | None = None,
) -> list[dict]:
    with get_connection() as conn:
        if before_id:
            cursor = conn.execute(
                """SELECT * FROM memory_messages
                   WHERE thread_id = ? AND created_at < (
                       SELECT created_at FROM memory_messages WHERE id = ?
                   )
                   ORDER BY created_at DESC LIMIT ?""",
                (thread_id, before_id, limit),
            )
        else:
            cursor = conn.execute(
                """SELECT * FROM memory_messages
                   WHERE thread_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (thread_id, limit),
            )
        rows = [_msg_row_to_dict(row) for row in cursor.fetchall()]
        rows.reverse()  # Return in chronological order
        return rows


def count_messages(thread_id: str) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM memory_messages WHERE thread_id = ?", (thread_id,)
        )
        return cursor.fetchone()[0]


def delete_messages(thread_id: str) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM memory_messages WHERE thread_id = ?", (thread_id,)
        )
        conn.commit()
        return cursor.rowcount


# --- Semantic Recall (FTS5) ---


def recall_messages(
    thread_id: str | None,
    query: str,
    resource_id: str | None = None,
    resource_type: str = "agent",
    top_k: int = 5,
    message_range: int = 1,
) -> list[dict]:
    """Search memory messages using FTS5 full-text search with BM25 ranking.

    Returns the top_k most relevant messages plus surrounding context
    (message_range messages before and after each match).
    """
    with get_connection() as conn:
        # Build FTS5 query: split into alphanumeric words, join with OR
        import re
        words = re.findall(r'\w+', query)
        if not words:
            return []
        # Quote each word for safe FTS5 matching
        fts_query = " OR ".join(f'"{w}"' for w in words)

        try:
            return _execute_recall(conn, fts_query, thread_id, resource_id, resource_type,
                                   top_k, message_range)
        except Exception:
            logger.warning("FTS5 recall query failed for: %s", query[:100])
            return []


def _execute_recall(
    conn, fts_query: str, thread_id, resource_id, resource_type, top_k, message_range
) -> list[dict]:
    """Execute the FTS5 recall query and expand context."""
    if thread_id:
        cursor = conn.execute(
            """SELECT m.id, m.thread_id, m.role, m.content, m.type, m.metadata, m.created_at
               FROM memory_messages_fts fts
               JOIN memory_messages m ON m.rowid = fts.rowid
               WHERE memory_messages_fts MATCH ?
                 AND m.thread_id = ?
               ORDER BY rank
               LIMIT ?""",
            (fts_query, thread_id, top_k),
        )
    elif resource_id:
        cursor = conn.execute(
            """SELECT m.id, m.thread_id, m.role, m.content, m.type, m.metadata, m.created_at
               FROM memory_messages_fts fts
               JOIN memory_messages m ON m.rowid = fts.rowid
               JOIN memory_threads t ON t.id = m.thread_id
               WHERE memory_messages_fts MATCH ?
                 AND t.resource_id = ? AND t.resource_type = ?
               ORDER BY rank
               LIMIT ?""",
            (fts_query, resource_id, resource_type, top_k),
        )
    else:
        return []

    matches = [_msg_row_to_dict(row) for row in cursor.fetchall()]

    if message_range <= 0:
        return matches

    # Expand with surrounding context
    expanded: list[dict] = []
    seen_ids: set = set()
    for match in matches:
        cursor = conn.execute(
            """SELECT * FROM memory_messages
               WHERE thread_id = ? AND created_at <= ?
               ORDER BY created_at DESC LIMIT ?""",
            (match["thread_id"], match["created_at"], message_range + 1),
        )
        before = [_msg_row_to_dict(r) for r in cursor.fetchall()]

        cursor = conn.execute(
            """SELECT * FROM memory_messages
               WHERE thread_id = ? AND created_at > ?
               ORDER BY created_at ASC LIMIT ?""",
            (match["thread_id"], match["created_at"], message_range),
        )
        after = [_msg_row_to_dict(r) for r in cursor.fetchall()]

        for m in list(reversed(before)) + after:
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                expanded.append(m)

        return expanded


# --- Working Memory ---


def get_working_memory(entity_id: str, entity_type: str = "agent") -> dict | None:
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM agent_working_memory WHERE entity_id = ? AND entity_type = ?",
            (entity_id, entity_type),
        )
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        # Try parsing content as JSON
        try:
            d["content_parsed"] = json.loads(d["content"])
        except (json.JSONDecodeError, TypeError):
            d["content_parsed"] = None
        return d


def upsert_working_memory(
    entity_id: str,
    entity_type: str = "agent",
    content: str = "",
    template: str | None = None,
) -> dict:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO agent_working_memory (entity_id, entity_type, content, template)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(entity_id, entity_type) DO UPDATE SET
                   content = excluded.content,
                   template = COALESCE(excluded.template, agent_working_memory.template),
                   updated_at = CURRENT_TIMESTAMP""",
            (entity_id, entity_type, content, template),
        )
        conn.commit()
    return get_working_memory(entity_id, entity_type)


def delete_working_memory(entity_id: str, entity_type: str = "agent") -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM agent_working_memory WHERE entity_id = ? AND entity_type = ?",
            (entity_id, entity_type),
        )
        conn.commit()
        return cursor.rowcount > 0


# --- Helpers ---


def _row_with_json_metadata(row) -> dict:
    if not row:
        return {}
    d = dict(row)
    if d.get("metadata"):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse metadata JSON: %s", str(d["metadata"])[:100])
            d["metadata"] = None
    return d


# Aliases for backward compat within this module
_thread_row_to_dict = _row_with_json_metadata
_msg_row_to_dict = _row_with_json_metadata
