"""Bot pipe CRUD operations."""

import logging

from .connection import get_connection
from .ids import generate_id

logger = logging.getLogger(__name__)

PIPE_ID_PREFIX = "pipe-"
PIPE_ID_LENGTH = 6

PIPE_EXEC_ID_PREFIX = "pexec-"
PIPE_EXEC_ID_LENGTH = 6


def _generate_pipe_id() -> str:
    return generate_id(PIPE_ID_PREFIX, PIPE_ID_LENGTH)


def _generate_pipe_exec_id() -> str:
    return generate_id(PIPE_EXEC_ID_PREFIX, PIPE_EXEC_ID_LENGTH)


# =============================================================================
# Bot Pipe CRUD
# =============================================================================


def get_all_pipes() -> list[dict]:
    """Return all configured bot pipes ordered by created_at descending."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM bot_pipes ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]


def create_pipe(data: dict) -> dict:
    """Create a new bot pipe. Returns the created pipe as a dict."""
    pipe_id = generate_id(PIPE_ID_PREFIX, PIPE_ID_LENGTH)
    name = data["name"]
    source_bot_id = data["source_bot_id"]
    dest_bot_id = data["dest_bot_id"]
    transform = data.get("transform", "passthrough")
    enabled = int(data.get("enabled", 1))

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO bot_pipes (id, name, source_bot_id, dest_bot_id, transform, enabled)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (pipe_id, name, source_bot_id, dest_bot_id, transform, enabled),
        )
        conn.commit()
        cursor = conn.execute("SELECT * FROM bot_pipes WHERE id = ?", (pipe_id,))
        row = cursor.fetchone()
        return dict(row)


def update_pipe(pipe_id: str, data: dict) -> dict | None:
    """Update a bot pipe. Returns the updated pipe dict or None if not found."""
    allowed_fields = {"name", "source_bot_id", "dest_bot_id", "transform", "enabled"}
    updates = []
    values = []

    for field in allowed_fields:
        if field in data:
            updates.append(f"{field} = ?")
            val = data[field]
            if field == "enabled":
                val = int(val)
            values.append(val)

    if not updates:
        with get_connection() as conn:
            cursor = conn.execute("SELECT * FROM bot_pipes WHERE id = ?", (pipe_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    values.append(pipe_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE bot_pipes SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        cursor = conn.execute("SELECT * FROM bot_pipes WHERE id = ?", (pipe_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_pipe_executions(limit: int = 50) -> list[dict]:
    """Return recent bot pipe executions ordered by triggered_at descending."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM bot_pipe_executions ORDER BY triggered_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
