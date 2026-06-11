"""Repository helpers for answer eval stores.

``answer_eval_runs`` tracks one baseline-vs-pipeline evaluation batch.
``answer_eval_results`` holds per-question per-arm scores.
"""

from __future__ import annotations

from typing import Optional

from .connection import get_connection


def create_run(project_id: str, judge_backend: Optional[str] = None) -> int:
    """Create a new eval run in 'running' state. Returns the new run id."""
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO answer_eval_runs (project_id, judge_backend)
               VALUES (?, ?)""",
            (project_id, judge_backend),
        )
        conn.commit()
        return cur.lastrowid


def record_result(
    run_id: int,
    question: str,
    arm: str,
    answer_text: Optional[str],
    scores: dict,
    judge_reason: Optional[str],
    tokens: Optional[int],
    cost_usd: Optional[float],
) -> int:
    """Append one per-question per-arm result row. Returns the new row id."""
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO answer_eval_results
                   (run_id, question, arm, answer_text, groundedness,
                    sufficiency, quality, judge_reason, tokens, cost_usd)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                question,
                arm,
                answer_text,
                scores.get("groundedness"),
                scores.get("sufficiency"),
                scores.get("quality"),
                judge_reason,
                tokens,
                cost_usd,
            ),
        )
        conn.commit()
        return cur.lastrowid


def finalize_run(run_id: int, aggregates: dict) -> bool:
    """Set per-arm means + deltas, mark status='complete', set finished_at.

    ``aggregates`` keys mirror the column names:
    baseline_groundedness, baseline_sufficiency, baseline_quality,
    pipeline_groundedness, pipeline_sufficiency, pipeline_quality,
    delta_groundedness, delta_sufficiency, delta_quality.

    Returns True if a row was updated.
    """
    with get_connection() as conn:
        cur = conn.execute(
            """UPDATE answer_eval_runs SET
                   baseline_groundedness = ?,
                   baseline_sufficiency  = ?,
                   baseline_quality      = ?,
                   pipeline_groundedness = ?,
                   pipeline_sufficiency  = ?,
                   pipeline_quality      = ?,
                   delta_groundedness    = ?,
                   delta_sufficiency     = ?,
                   delta_quality         = ?,
                   status                = 'complete',
                   finished_at           = datetime('now')
               WHERE id = ?""",
            (
                aggregates.get("baseline_groundedness"),
                aggregates.get("baseline_sufficiency"),
                aggregates.get("baseline_quality"),
                aggregates.get("pipeline_groundedness"),
                aggregates.get("pipeline_sufficiency"),
                aggregates.get("pipeline_quality"),
                aggregates.get("delta_groundedness"),
                aggregates.get("delta_sufficiency"),
                aggregates.get("delta_quality"),
                run_id,
            ),
        )
        conn.commit()
    return cur.rowcount > 0


def get_run(run_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM answer_eval_runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_runs(project_id: Optional[str] = None, *, limit: int = 20) -> list[dict]:
    if project_id is not None:
        sql = "SELECT * FROM answer_eval_runs WHERE project_id = ? ORDER BY created_at DESC LIMIT ?"
        params = (project_id, int(limit))
    else:
        sql = "SELECT * FROM answer_eval_runs ORDER BY created_at DESC LIMIT ?"
        params = (int(limit),)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_results(run_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM answer_eval_results WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
    return [dict(r) for r in rows]
