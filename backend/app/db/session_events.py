"""Session-event audit log helpers (v0.5.12).

Best-effort: errors during logging are swallowed (logged at WARNING)
so a session-lifecycle event never fails because the audit write
fails.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def _insert_event_row(
    session_id: str,
    user_id: Optional[str],
    event_type: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
    metadata_json: Optional[str],
) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO session_events
               (session_id, user_id, event_type, ip_address, user_agent, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, user_id, event_type, ip_address, user_agent, metadata_json),
        )
        conn.commit()


def log_session_event(
    session_id: str,
    user_id: Optional[str],
    event_type: str,
    *,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Append a session lifecycle event. Best-effort — never raises.

    Event types: created, refreshed, rotated, revoked, expired,
    idle_expired, used_after_revocation, used_after_expiry.
    """
    metadata_json = json.dumps(metadata) if metadata else None
    try:
        _insert_event_row(
            session_id,
            user_id,
            event_type,
            ip_address,
            user_agent,
            metadata_json,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort audit write
        logger.warning(
            "log_session_event failed for session=%s event=%s: %s",
            session_id,
            event_type,
            exc,
        )


def list_session_events(
    *,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Read session events, newest first. Returns plain dicts; metadata
    is parsed back from JSON on read."""
    where = []
    params: list[Any] = []
    if user_id:
        where.append("user_id = ?")
        params.append(user_id)
    if session_id:
        where.append("session_id = ?")
        params.append(session_id)
    if event_type:
        where.append("event_type = ?")
        params.append(event_type)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    params.extend([limit, offset])

    with get_connection() as conn:
        cursor = conn.execute(
            f"""SELECT id, session_id, user_id, event_type, occurred_at,
                       ip_address, user_agent, metadata
                FROM session_events
                {where_sql}
                ORDER BY occurred_at DESC, id DESC
                LIMIT ? OFFSET ?""",
            params,
        )
        rows = cursor.fetchall()

    out: list[dict] = []
    for row in rows:
        d = {
            "id": row[0],
            "session_id": row[1],
            "user_id": row[2],
            "event_type": row[3],
            "occurred_at": row[4],
            "ip_address": row[5],
            "user_agent": row[6],
            "metadata": None,
        }
        if row[7]:
            try:
                d["metadata"] = json.loads(row[7])
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "session_events: corrupt metadata JSON on row %s; raw=%r",
                    row[0],
                    row[7][:200],
                )
                d["metadata"] = None
        out.append(d)
    return out
