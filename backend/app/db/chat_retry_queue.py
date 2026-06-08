"""DB helpers for the chat retry queue (rate-limit rotation Phase 2).

One pending row per chat session (UNIQUE session_id). A turn lands here when
every eligible account is rate-limited; the ``chat_retry_queue`` scheduler
job re-dispatches it once an account frees up. Survives restarts.
"""

from __future__ import annotations

from typing import List, Optional

from .connection import get_connection


def enqueue_chat_retry(
    *,
    session_id: str,
    super_agent_id: str,
    backend: Optional[str],
    account_id: Optional[str],
    model: Optional[str],
    cwd: Optional[str],
    chat_mode: Optional[str],
    instance_id: Optional[str],
    use_cli_agent: Optional[bool],
    reason: Optional[str],
) -> None:
    """Upsert a pending retry for a session. On conflict (already queued)
    bump ``attempts`` and refresh the reason — a session never accrues
    duplicate rows."""
    uca = None if use_cli_agent is None else (1 if use_cli_agent else 0)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO chat_retry_queue
                (session_id, super_agent_id, backend, account_id, model, cwd,
                 chat_mode, instance_id, use_cli_agent, reason, attempts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(session_id) DO UPDATE SET
                attempts = attempts + 1,
                reason = excluded.reason,
                super_agent_id = excluded.super_agent_id,
                backend = excluded.backend,
                account_id = excluded.account_id,
                model = excluded.model,
                cwd = excluded.cwd,
                chat_mode = excluded.chat_mode,
                instance_id = excluded.instance_id,
                use_cli_agent = excluded.use_cli_agent
            """,
            (
                session_id,
                super_agent_id,
                backend,
                account_id,
                model,
                cwd,
                chat_mode,
                instance_id,
                uca,
                reason,
            ),
        )
        conn.commit()


def list_pending_chat_retries() -> List[dict]:
    """All queued retries, oldest first. ``use_cli_agent`` is decoded back to
    a tri-state bool (None / True / False)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_retry_queue ORDER BY created_at ASC, id ASC"
        ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        uca = d.get("use_cli_agent")
        d["use_cli_agent"] = None if uca is None else bool(uca)
        out.append(d)
    return out


def mark_chat_retry_attempted(session_id: str) -> None:
    """Stamp last_attempt_at + increment attempts when a retry is dispatched."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE chat_retry_queue SET attempts = attempts + 1, "
            "last_attempt_at = datetime('now') WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()


def delete_chat_retry(session_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM chat_retry_queue WHERE session_id = ?", (session_id,))
        conn.commit()


def count_pending_chat_retries() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM chat_retry_queue").fetchone()
    return int(row[0]) if row else 0
