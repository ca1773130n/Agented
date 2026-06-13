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
    current_body_hash: Optional[str] = None,
    reason: Optional[str] = None,
) -> bool:
    """Record the verdict + scores and stamp finished_at. Returns True if updated.

    ``delta`` is computed as candidate - current when both are present.
    ``current_body_hash`` pins the current body the candidate beat, so adoption
    can detect that the skill changed since gating (stale-adoption guard).
    """
    delta = None
    if current_score is not None and candidate_score is not None:
        delta = candidate_score - current_score
    with get_connection() as conn:
        cur = conn.execute(
            """UPDATE skill_sleep_runs SET
                   status            = ?,
                   current_score     = ?,
                   candidate_score   = ?,
                   delta             = ?,
                   question_count    = ?,
                   candidate_body    = ?,
                   current_body_hash = ?,
                   reason            = ?,
                   finished_at       = datetime('now')
               WHERE id = ?""",
            (
                status,
                current_score,
                candidate_score,
                delta,
                int(question_count),
                candidate_body,
                current_body_hash,
                reason,
                run_id,
            ),
        )
        conn.commit()
    return cur.rowcount > 0


def record_outcome(
    run_id: int,
    *,
    before_score: Optional[float],
    after_score: Optional[float],
    question_count: int = 0,
) -> bool:
    """Record the disjoint-split outcome measurement on a run (Phase 6).

    ``outcome_delta`` = after - before when both present. This is measured on a
    partition DISJOINT from the gate's, so it is the honest "did optimizing
    actually help" signal. Returns True if a row was updated.
    """
    delta = None
    if before_score is not None and after_score is not None:
        delta = after_score - before_score
    with get_connection() as conn:
        cur = conn.execute(
            """UPDATE skill_sleep_runs SET
                   outcome_before_score   = ?,
                   outcome_after_score    = ?,
                   outcome_delta          = ?,
                   outcome_question_count = ?
               WHERE id = ?""",
            (before_score, after_score, delta, int(question_count), run_id),
        )
        conn.commit()
    return cur.rowcount > 0


def mark_adopted(run_id: int) -> bool:
    """Stamp adopted_at on an accepted run (the candidate body was written to
    disk). Idempotent: only sets it when currently NULL. Returns True if newly
    stamped."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE skill_sleep_runs SET adopted_at = datetime('now') "
            "WHERE id = ? AND status = 'accepted' AND adopted_at IS NULL",
            (run_id,),
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
