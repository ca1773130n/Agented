"""DB layer for the goal-loop execution type (v0.7.74).

Two surfaces:

* ``project_sessions.goal_loop_config`` — JSON column read/written
  via the existing ``project_sessions`` row machinery. We provide
  thin helpers here so callers don't have to remember to ``json.dumps``
  and the column name is owned by one module.
* ``goal_loop_iterations`` — audit table; per-iteration verdict +
  reason + cost. Append-only from the runner, read-only for the UI.
"""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def set_goal_loop_config(session_id: str, config: dict) -> None:
    """Persist the goal-loop config blob onto a project_sessions row."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE project_sessions SET goal_loop_config = ? WHERE id = ?",
            (json.dumps(config, ensure_ascii=False), session_id),
        )
        conn.commit()


def get_goal_loop_config(session_id: str) -> Optional[dict]:
    """Read the goal-loop config blob (parsed) for a session, or
    ``None`` if the column is null / the row doesn't exist / the JSON
    is invalid (logged + returns None — invalid config shouldn't
    crash a session lookup).
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT goal_loop_config FROM project_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    if not row or not row[0]:
        return None
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "goal_loop: invalid config JSON on session %s; treating as missing",
            session_id,
        )
        return None


def record_iteration_start(session_id: str, iteration: int) -> int:
    """Insert a new pending iteration row. Returns the row id.

    Pending = ``ended_at`` is null and ``verdict`` is null.
    ``record_iteration_complete`` fills both in. The runner inserts
    the row at the start so the UI's "currently judging" banner has
    a row to look at.
    """
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO goal_loop_iterations
                (session_id, iteration, judge_source)
            VALUES (?, ?, ?)
            """,
            (session_id, iteration, "pending"),
        )
        conn.commit()
        return cur.lastrowid


def record_iteration_complete(
    row_id: int,
    *,
    verdict: str,
    judge_source: str,
    judge_reason: Optional[str] = None,
    judge_stdout: Optional[str] = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
) -> None:
    """Fill in the verdict + cost telemetry on a pending iteration row."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE goal_loop_iterations
            SET ended_at = CURRENT_TIMESTAMP,
                verdict = ?,
                judge_source = ?,
                judge_reason = ?,
                judge_stdout = ?,
                tokens_in = ?,
                tokens_out = ?,
                cost_usd = ?
            WHERE id = ?
            """,
            (
                verdict,
                judge_source,
                judge_reason,
                judge_stdout,
                tokens_in,
                tokens_out,
                cost_usd,
                row_id,
            ),
        )
        conn.commit()


def list_iterations(session_id: str) -> List[dict]:
    """Return all iteration rows for a session, oldest first."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT id, session_id, iteration, started_at, ended_at,
                   verdict, judge_source, judge_reason, judge_stdout,
                   tokens_in, tokens_out, cost_usd
            FROM goal_loop_iterations
            WHERE session_id = ?
            ORDER BY iteration ASC, id ASC
            """,
            (session_id,),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]


def _row_to_dict(row: Any) -> dict:
    return {
        "id": row[0],
        "session_id": row[1],
        "iteration": row[2],
        "started_at": row[3],
        "ended_at": row[4],
        "verdict": row[5],
        "judge_source": row[6],
        "judge_reason": row[7],
        "judge_stdout": row[8],
        "tokens_in": row[9],
        "tokens_out": row[10],
        "cost_usd": row[11],
    }
