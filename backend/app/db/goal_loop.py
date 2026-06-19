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
    hypothesis: Optional[str] = None,
    predicted_outcome: Optional[str] = None,
    ouroboros_verdict: Optional[str] = None,
    body_kind: str = "eval_refine",
    confidence: Optional[float] = None,
    judge_version: Optional[str] = None,
) -> None:
    """Fill in the verdict + cost telemetry on a pending iteration row.

    v0.7.86 — adds three Ouroboros fields (hypothesis,
    predicted_outcome, ouroboros_verdict). All optional so the
    pre-Ouroboros call shape still works for callers that don't
    opt in.

    v0.6.0 unified loops — adds ``body_kind`` (so Ralph's
    agent_task iterations share the table) and persists a
    convenience ``tokens_total`` for the token-budget breaker.

    v0.6.0 sub-project #2 — adds ``confidence`` (the judge's 0–1
    confidence in the verdict, used for dynamic early-termination)
    and ``judge_version`` (rubric/judge version stamp for drift
    auditing). Both optional so pre-existing callers still work.
    """
    tokens_total = (tokens_in or 0) + (tokens_out or 0)
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
                cost_usd = ?,
                hypothesis = ?,
                predicted_outcome = ?,
                ouroboros_verdict = ?,
                body_kind = ?,
                tokens_total = ?,
                confidence = ?,
                judge_version = ?
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
                hypothesis,
                predicted_outcome,
                ouroboros_verdict,
                body_kind,
                tokens_total,
                confidence,
                judge_version,
                row_id,
            ),
        )
        conn.commit()


# ---------------------------------------------------------------------
# v0.7.86 — goal_loop_dead_ends (session-scoped Ouroboros registry)
# ---------------------------------------------------------------------


def add_goal_loop_dead_end(
    *,
    session_id: str,
    iteration: int,
    approach: str,
    reason: str,
    evidence: Optional[str] = None,
    approach_hash: str,
) -> Optional[int]:
    """Record a falsified approach for this session. Idempotent —
    duplicate ``(session_id, approach_hash)`` is silently dropped
    via the schema's UNIQUE constraint so the runner doesn't have
    to dedupe before calling.

    Returns the row id on insert, or ``None`` when the row already
    existed (duplicate hash).
    """
    with get_connection() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO goal_loop_dead_ends
                    (session_id, iteration, approach, reason, evidence, approach_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, iteration, approach, reason, evidence, approach_hash),
            )
            conn.commit()
            return cur.lastrowid
        except Exception as exc:
            # IntegrityError on the UNIQUE constraint is the expected
            # case — log and swallow so the caller doesn't have to.
            logger.debug(
                "goal_loop: duplicate dead-end for session %s (%s)",
                session_id,
                exc,
            )
            return None


def list_goal_loop_dead_ends(session_id: str) -> List[dict]:
    """Return all dead-ends for a session, newest first. Used by the
    runner to inject prior dead-ends into subsequent prompts.
    """
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT id, session_id, iteration, approach, reason, evidence,
                   approach_hash, recorded_at
            FROM goal_loop_dead_ends
            WHERE session_id = ?
            ORDER BY recorded_at DESC
            """,
            (session_id,),
        )
        return [
            {
                "id": r[0],
                "session_id": r[1],
                "iteration": r[2],
                "approach": r[3],
                "reason": r[4],
                "evidence": r[5],
                "approach_hash": r[6],
                "recorded_at": r[7],
            }
            for r in cur.fetchall()
        ]


def recent_iteration_verdicts(session_id: str, limit: int = 3) -> List[str]:
    """Return the last N completed iterations' ``ouroboros_verdict``
    values, oldest first within the window. Used by the runner to
    detect convergence (e.g., 3 consecutive ``falsified`` →
    ontology-convergence termination).
    """
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT ouroboros_verdict
            FROM goal_loop_iterations
            WHERE session_id = ? AND ouroboros_verdict IS NOT NULL
            ORDER BY iteration DESC
            LIMIT ?
            """,
            (session_id, limit),
        )
        rows = [r[0] for r in cur.fetchall()]
        return list(reversed(rows))


def list_iterations(session_id: str) -> List[dict]:
    """Return all iteration rows for a session, oldest first."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT id, session_id, iteration, started_at, ended_at,
                   verdict, judge_source, judge_reason, judge_stdout,
                   tokens_in, tokens_out, cost_usd, body_kind, tokens_total,
                   confidence, judge_version
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
        "body_kind": row[12],
        "tokens_total": row[13],
        "confidence": row[14],
        "judge_version": row[15],
    }
