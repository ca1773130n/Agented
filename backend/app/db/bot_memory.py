"""Bot memory store CRUD operations.

Each bot maintains a key-value memory store that persists across executions.
Entries have a source (bot or manual), optional expiry, and a per-bot byte quota.
"""

import logging

from .connection import get_connection

logger = logging.getLogger(__name__)

MAX_BYTES = 65536


def get_bot_memory(bot_id: str) -> list[dict]:
    """Return all memory entries for a bot, with computed byte usage.

    Each returned entry includes ``used_bytes`` (total for the bot) and
    ``max_bytes`` (65536) so the frontend can render a usage bar.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT bot_id, key, value, source, expires_at, updated_at "
            "FROM bot_memory WHERE bot_id = ? ORDER BY updated_at DESC",
            (bot_id,),
        )
        rows = [dict(row) for row in cursor.fetchall()]

    used_bytes = sum(len(r["value"].encode("utf-8")) for r in rows)
    for row in rows:
        row["used_bytes"] = used_bytes
        row["max_bytes"] = MAX_BYTES

    return rows


def upsert_memory_entry(
    bot_id: str,
    key: str,
    value: str,
    source: str = "manual",
    expires_at: str | None = None,
) -> dict:
    """Insert or replace a memory entry. Returns the saved entry as a dict."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO bot_memory (bot_id, key, value, source, expires_at, updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(bot_id, key) DO UPDATE SET
                   value = excluded.value,
                   source = excluded.source,
                   expires_at = excluded.expires_at,
                   updated_at = datetime('now')""",
            (bot_id, key, value, source, expires_at),
        )
        conn.commit()
        cursor = conn.execute(
            "SELECT bot_id, key, value, source, expires_at, updated_at "
            "FROM bot_memory WHERE bot_id = ? AND key = ?",
            (bot_id, key),
        )
        row = cursor.fetchone()
        return dict(row) if row else {}


def delete_memory_entry(bot_id: str, key: str) -> bool:
    """Delete a single memory entry. Returns True if a row was deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM bot_memory WHERE bot_id = ? AND key = ?",
            (bot_id, key),
        )
        conn.commit()
        return cursor.rowcount > 0


def clear_bot_memory(bot_id: str) -> bool:
    """Delete all memory entries for a bot. Returns True if any rows were deleted."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM bot_memory WHERE bot_id = ?", (bot_id,))
        conn.commit()
        return cursor.rowcount > 0
