"""Repository for Skill-Sleep runs (SkillOpt integration, migration 160).

A run is one gated skill-optimization attempt. ``create_run`` opens it in
``running``; ``finalize_run`` records the verdict + scores. Verdicts:
``accepted`` (candidate strictly beat current), ``rejected`` (did not),
``abstained`` (corpus too thin to judge), ``failed`` (infra error — fail closed).
"""

from __future__ import annotations

from typing import Optional

from .connection import get_connection


def create_run(
    project_id: str,
    skill_name: str,
    *,
    skill_id: Optional[int] = None,
    partition_seed: int = 0,
    judge_backend: Optional[str] = None,
) -> int:
    """Open a Skill-Sleep run in 'running' state. Returns the new run id."""
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO skill_sleep_runs
                   (project_id, skill_name, skill_id, partition_seed, judge_backend)
               VALUES (?, ?, ?, ?, ?)""",
            (project_id, skill_name, skill_id, int(partition_seed), judge_backend),
        )
        conn.commit()
        return cur.lastrowid


def finalize_run(
    run_id: int,
    *,
    status: str,
    current_score: Optional[float] = None,
    candidate_score: Optional[float] = None,
    question_count: int = 0,
    candidate_body: Optional[str] = None,
    reason: Optional[str] = None,
) -> bool:
    """Record the verdict + scores and stamp finished_at. Returns True if updated.

    ``delta`` is computed as candidate - current when both are present.
    """
    delta = None
    if current_score is not None and candidate_score is not None:
        delta = candidate_score - current_score
    with get_connection() as conn:
        cur = conn.execute(
            """UPDATE skill_sleep_runs SET
                   status          = ?,
                   current_score   = ?,
                   candidate_score = ?,
                   delta           = ?,
                   question_count  = ?,
                   candidate_body  = ?,
                   reason          = ?,
                   finished_at     = datetime('now')
               WHERE id = ?""",
            (
                status,
                current_score,
                candidate_score,
                delta,
                int(question_count),
                candidate_body,
                reason,
                run_id,
            ),
        )
        conn.commit()
    return cur.rowcount > 0


def get_run(run_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM skill_sleep_runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_runs(project_id: Optional[str] = None, *, limit: int = 50) -> list[dict]:
    if project_id is not None:
        sql = "SELECT * FROM skill_sleep_runs WHERE project_id = ? ORDER BY created_at DESC LIMIT ?"
        params: tuple = (project_id, int(limit))
    else:
        sql = "SELECT * FROM skill_sleep_runs ORDER BY created_at DESC LIMIT ?"
        params = (int(limit),)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
