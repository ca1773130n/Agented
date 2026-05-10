"""Per-super-agent activity timeline + rollup + TTL purge.

v0.7.7 introduces a single observability surface for super-agent
autonomous runs. ``record(...)`` is invoked from existing super-agent
execution paths (orchestration, sessions, model invokes); the inspector
page reads ``list_for_super_agent`` and ``rollup``. ``purge_older_than``
is wired into the daily scheduler.

Mirrors the v0.7.0 (``bot_health_service``) and v0.7.1
(``trigger_event_service``) patterns intentionally — no new orchestration
logic is introduced here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from app.db.connection import get_connection

ACTIVE_WINDOW_MINUTES = 5
IDLE_WINDOW_HOURS = 24
ERROR_RATE_DEGRADED = 0.10
ERROR_LOOKBACK_EVENTS = 10

StatusPill = Literal["active", "errored", "idle", "healthy"]


@dataclass(frozen=True)
class SuperAgentRollup:
    super_agent_id: str
    event_count: int
    error_count: int
    total_cost_usd: float
    last_active_at: str | None
    status_pill: StatusPill
    cost_per_event_avg: float | None
    error_rate: float | None


def record(
    *,
    super_agent_id: str,
    event_type: str,
    payload: dict | str,
    session_id: str | None = None,
    cost_tokens_in: int | None = None,
    cost_tokens_out: int | None = None,
    cost_usd: float | None = None,
    status: str = "ok",
    error_message: str | None = None,
    duration_ms: int | None = None,
) -> int:
    payload_str = (
        payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    )
    recorded_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO super_agent_activity
               (super_agent_id, session_id, event_type, recorded_at, payload,
                cost_tokens_in, cost_tokens_out, cost_usd, status,
                error_message, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                super_agent_id,
                session_id,
                event_type,
                recorded_at,
                payload_str,
                cost_tokens_in,
                cost_tokens_out,
                cost_usd,
                status,
                error_message,
                duration_ms,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_for_super_agent(
    super_agent_id: str,
    *,
    limit: int = 200,
    since: str | None = None,
    types: list[str] | None = None,
) -> list[dict[str, Any]]:
    sql = ["SELECT * FROM super_agent_activity WHERE super_agent_id = ?"]
    params: list[Any] = [super_agent_id]
    if since:
        sql.append("AND recorded_at >= ?")
        params.append(since)
    if types:
        sql.append("AND event_type IN (" + ",".join("?" * len(types)) + ")")
        params.extend(types)
    sql.append("ORDER BY recorded_at DESC, id DESC LIMIT ?")
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(" ".join(sql), tuple(params)).fetchall()
    return [dict(r) for r in rows]


def list_for_session(session_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM super_agent_activity WHERE session_id = ?
               ORDER BY recorded_at DESC, id DESC LIMIT ?""",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get(activity_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM super_agent_activity WHERE id = ?",
            (activity_id,),
        ).fetchone()
    return dict(row) if row else None


def rollup(super_agent_id: str, *, window_days: int = 7) -> SuperAgentRollup:
    if not (1 <= window_days <= 90):
        raise ValueError(f"window_days must be 1..90, got {window_days}")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT status, cost_usd, recorded_at
               FROM super_agent_activity
               WHERE super_agent_id = ? AND recorded_at >= ?
               ORDER BY recorded_at DESC""",
            (super_agent_id, cutoff),
        ).fetchall()
    total = len(rows)
    errors = sum(1 for r in rows if r["status"] == "error")
    total_cost = sum((r["cost_usd"] or 0.0) for r in rows)
    last_active = rows[0]["recorded_at"] if rows else None
    error_rate = (errors / total) if total else None
    cost_per_event = (total_cost / total) if total else None
    return SuperAgentRollup(
        super_agent_id=super_agent_id,
        event_count=total,
        error_count=errors,
        total_cost_usd=total_cost,
        last_active_at=last_active,
        status_pill=_classify(rows),
        cost_per_event_avg=cost_per_event,
        error_rate=error_rate,
    )


def _classify(rows: list[Any]) -> StatusPill:
    if not rows:
        return "idle"
    last_ts = datetime.fromisoformat(rows[0]["recorded_at"])
    now = datetime.now(timezone.utc)
    minutes_since = (now - last_ts).total_seconds() / 60
    hours_since = minutes_since / 60
    if hours_since >= IDLE_WINDOW_HOURS:
        return "idle"
    if rows[0]["status"] == "error":
        return "errored"
    if minutes_since <= ACTIVE_WINDOW_MINUTES:
        return "active"
    recent = rows[:ERROR_LOOKBACK_EVENTS]
    err_rate = sum(1 for r in recent if r["status"] == "error") / len(recent)
    if err_rate >= ERROR_RATE_DEGRADED:
        return "errored"
    return "healthy"


def purge_older_than(days: int) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM super_agent_activity WHERE recorded_at < ?",
            (cutoff,),
        )
        conn.commit()
        return cur.rowcount or 0
