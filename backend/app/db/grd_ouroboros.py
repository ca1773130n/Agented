"""CRUD for the v0.7.85 GRD Ouroboros artifact mirror.

Three tables, all populated by ``GrdSyncService`` after every GRD
session completes:

* ``phase_reflections`` — per-phase ``REFLECTION.md`` mirror
  (hypothesis → predicted → actual → verdict + evidence). One row
  per REFLECTION.md found on disk; rows are upserted by
  ``source_path`` so a phase rewriting its reflection doesn't
  accumulate stale duplicates.
* ``project_dead_ends`` — per-project ``DEAD-ENDS.md`` entries.
  ``source`` distinguishes manual entries (``manual``) from those
  promoted from a phase reflection (``promoted-from-phase``).
* ``project_genome_snapshots`` — append-only ``GENOME.md`` history.
  Each snapshot keeps its full markdown body so the UI can show a
  per-cycle diff without round-tripping to disk.

All write helpers are idempotent — they use ``content_hash`` as a
duplicate guard so re-running the sync after a no-op edit doesn't
multiply rows.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from .connection import get_connection, safe_set_clause
from .ids import (
    _get_unique_dead_end_id,
    _get_unique_genome_snapshot_id,
    _get_unique_reflection_id,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# phase_reflections
# ---------------------------------------------------------------------


def upsert_phase_reflection(
    *,
    phase_id: str,
    hypothesis: Optional[str] = None,
    predicted_outcome: Optional[str] = None,
    actual_outcome: Optional[str] = None,
    verdict: Optional[str] = None,
    evidence: Optional[str] = None,
    source_path: Optional[str] = None,
    content_hash: Optional[str] = None,
    recorded_at: Optional[str] = None,
) -> str:
    """Insert or update a reflection row keyed by ``(phase_id, source_path)``.

    Idempotency rule: if a row already exists for the same
    ``source_path`` (typical case — one ``REFLECTION.md`` per phase),
    update it in place; otherwise allocate a new id and insert. Returns
    the row id either way.
    """
    with get_connection() as conn:
        existing = None
        if source_path:
            cursor = conn.execute(
                "SELECT id FROM phase_reflections "
                "WHERE phase_id = ? AND source_path = ?",
                (phase_id, source_path),
            )
            row = cursor.fetchone()
            if row:
                existing = row[0]
        if existing:
            conn.execute(
                """
                UPDATE phase_reflections
                SET hypothesis = ?,
                    predicted_outcome = ?,
                    actual_outcome = ?,
                    verdict = ?,
                    evidence = ?,
                    content_hash = ?,
                    recorded_at = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    hypothesis,
                    predicted_outcome,
                    actual_outcome,
                    verdict,
                    evidence,
                    content_hash,
                    recorded_at,
                    existing,
                ),
            )
            conn.commit()
            return existing
        rid = _get_unique_reflection_id(conn)
        conn.execute(
            """
            INSERT INTO phase_reflections
                (id, phase_id, hypothesis, predicted_outcome, actual_outcome,
                 verdict, evidence, source_path, content_hash, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                phase_id,
                hypothesis,
                predicted_outcome,
                actual_outcome,
                verdict,
                evidence,
                source_path,
                content_hash,
                recorded_at,
            ),
        )
        conn.commit()
        return rid


def get_phase_reflections(phase_id: str) -> List[dict]:
    """Return all reflections for a phase, newest first."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, phase_id, hypothesis, predicted_outcome, actual_outcome,
                   verdict, evidence, source_path, content_hash, recorded_at,
                   created_at, updated_at
            FROM phase_reflections
            WHERE phase_id = ?
            ORDER BY COALESCE(recorded_at, created_at) DESC
            """,
            (phase_id,),
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def count_reflections_by_verdict(project_id: str) -> dict:
    """Return ``{verdict: count}`` aggregated across a project's phases.

    Useful for the project overview card — `gd think` exposes the same
    aggregation but Agented avoids a CLI hop for the common UI read.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT pr.verdict, COUNT(*) AS n
            FROM phase_reflections pr
            JOIN project_phases pp ON pp.id = pr.phase_id
            JOIN milestones m ON m.id = pp.milestone_id
            WHERE m.project_id = ?
            GROUP BY pr.verdict
            """,
            (project_id,),
        )
        out = {"confirmed": 0, "partial": 0, "falsified": 0, "unknown": 0}
        for verdict, n in cursor.fetchall():
            key = (verdict or "unknown").lower()
            if key in out:
                out[key] = n
        return out


# ---------------------------------------------------------------------
# project_dead_ends
# ---------------------------------------------------------------------


def add_dead_end(
    *,
    project_id: str,
    approach: str,
    reason: str,
    phase_label: Optional[str] = None,
    source: str = "manual",
    recorded_at: Optional[str] = None,
) -> str:
    """Insert a dead-end row. Caller-side dedup (sync layer hashes the
    full DEAD-ENDS.md file) is what prevents repeated inserts during
    no-op syncs; this helper just appends.
    """
    if source not in {"manual", "promoted-from-phase"}:
        raise ValueError(f"invalid source: {source}")
    with get_connection() as conn:
        did = _get_unique_dead_end_id(conn)
        conn.execute(
            """
            INSERT INTO project_dead_ends
                (id, project_id, approach, reason, phase_label, source, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (did, project_id, approach, reason, phase_label, source, recorded_at),
        )
        conn.commit()
        return did


def list_dead_ends(project_id: str, limit: int = 200) -> List[dict]:
    """Return dead-ends for a project, newest first."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, project_id, approach, reason, phase_label, source,
                   recorded_at, created_at
            FROM project_dead_ends
            WHERE project_id = ?
            ORDER BY COALESCE(recorded_at, created_at) DESC
            LIMIT ?
            """,
            (project_id, limit),
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def delete_dead_ends_for_project(project_id: str) -> int:
    """Delete every dead-end for a project. Used by the sync layer when
    the on-disk file is the source of truth and we re-import it
    wholesale (the file format doesn't carry a stable id-per-entry).
    Returns the row count removed.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM project_dead_ends WHERE project_id = ?",
            (project_id,),
        )
        conn.commit()
        return cursor.rowcount


# ---------------------------------------------------------------------
# project_genome_snapshots
# ---------------------------------------------------------------------


def add_genome_snapshot(
    *,
    project_id: str,
    sequence_number: int,
    content: str,
    content_hash: Optional[str] = None,
    captured_at: Optional[str] = None,
) -> str:
    """Append a genome snapshot. The CLI handles versioning; we just
    record what arrives.
    """
    with get_connection() as conn:
        gid = _get_unique_genome_snapshot_id(conn)
        conn.execute(
            """
            INSERT INTO project_genome_snapshots
                (id, project_id, sequence_number, content, content_hash, captured_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (gid, project_id, sequence_number, content, content_hash, captured_at),
        )
        conn.commit()
        return gid


def get_latest_genome_snapshot(project_id: str) -> Optional[dict]:
    """Return the most recent snapshot or None."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, project_id, sequence_number, content, content_hash,
                   captured_at, created_at
            FROM project_genome_snapshots
            WHERE project_id = ?
            ORDER BY sequence_number DESC, COALESCE(captured_at, created_at) DESC
            LIMIT 1
            """,
            (project_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cursor.description]
        return dict(zip(cols, row))


def list_genome_snapshots(project_id: str, limit: int = 50) -> List[dict]:
    """Return snapshots for a project, newest first."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, project_id, sequence_number, content, content_hash,
                   captured_at, created_at
            FROM project_genome_snapshots
            WHERE project_id = ?
            ORDER BY sequence_number DESC, COALESCE(captured_at, created_at) DESC
            LIMIT ?
            """,
            (project_id, limit),
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def max_genome_sequence(project_id: str) -> int:
    """Return the highest ``sequence_number`` stored for the project,
    or 0 if none. Sync uses this to know what offset to start
    appending new snapshots from.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT COALESCE(MAX(sequence_number), 0) FROM project_genome_snapshots "
            "WHERE project_id = ?",
            (project_id,),
        )
        return cursor.fetchone()[0]


# ---------------------------------------------------------------------
# project_plans v0.3.24 frontmatter columns
# ---------------------------------------------------------------------


def update_plan_ouroboros_fields(
    plan_id: str,
    *,
    hypothesis: Optional[str] = None,
    predicted_outcome: Optional[str] = None,
    verdict: Optional[str] = None,
) -> bool:
    """Patch the v0.3.24 frontmatter scalars on ``project_plans``.

    Only writes fields that are not None — callers can use a single
    helper for partial updates (e.g. the verifier writes ``verdict``
    only). Returns True iff a write actually happened.
    """
    updates = []
    values = []
    for col, val in (
        ("hypothesis", hypothesis),
        ("predicted_outcome", predicted_outcome),
        ("verdict", verdict),
    ):
        if val is not None:
            updates.append(f"{col} = ?")
            values.append(val)
    if not updates:
        return False
    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(plan_id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE project_plans SET {safe_set_clause(updates)} WHERE id = ?",
            values,
        )
        conn.commit()
        return True
