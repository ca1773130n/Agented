"""v0.7.1: capture, list, replay, and purge trigger payload events."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.database import get_connection


def record(
    *,
    trigger_id: str | None,
    payload: str,
    signature_header: str | None,
    dispatch_status: str,
    matched: bool,
    dispatch_error: str | None = None,
) -> int:
    """Insert a new event row. Returns event id."""
    received_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO trigger_events
               (trigger_id, received_at, payload, signature_header,
                matched, dispatch_status, dispatch_error)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                trigger_id,
                received_at,
                payload,
                signature_header,
                1 if matched else 0,
                dispatch_status,
                dispatch_error,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_for_trigger(trigger_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, trigger_id, received_at, payload, signature_header,
                      matched, dispatch_status, dispatch_error
               FROM trigger_events
               WHERE trigger_id = ?
               ORDER BY received_at DESC, id DESC
               LIMIT ?""",
            (trigger_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get(event_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT id, trigger_id, received_at, payload, signature_header,
                      matched, dispatch_status, dispatch_error
               FROM trigger_events WHERE id = ?""",
            (event_id,),
        ).fetchone()
    return dict(row) if row else None


def replay(event_id: int) -> bool:
    """Re-dispatch a stored event. Returns True if a trigger fired.

    The original raw request bytes are not preserved — only the parsed JSON
    payload — so any HMAC signature recorded on the event will not match a
    re-encoding of that JSON. The replay path therefore bypasses signature
    validation; the admin-only endpoint that calls this function provides the
    necessary auth gate.
    """
    e = get(event_id)
    if e is None:
        raise LookupError(f"trigger_event {event_id} not found")
    # Delayed import: ExecutionService is large; avoid circular at module load.
    from app.services.execution_service import ExecutionService

    payload_dict = json.loads(e["payload"])
    raw = e["payload"].encode("utf-8")
    return ExecutionService.dispatch_webhook_event(
        payload_dict,
        raw_payload=raw,
        signature_header=e["signature_header"],
        skip_signature_validation=True,
    )


def purge_older_than(days: int) -> int:
    """Delete events older than `days`. Returns count deleted."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM trigger_events WHERE received_at < ?",
            (cutoff,),
        )
        conn.commit()
        return cur.rowcount or 0
