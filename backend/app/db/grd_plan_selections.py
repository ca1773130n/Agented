"""CRUD for ``grd_plan_selections`` — mirror of GRD 0.4.5 ``gd select-candidate``.

One row per ``(project_id, phase)`` holding the latest deterministic selection:
the ranked candidates (with axis breakdowns), the winner, and the audit. Full
replace on re-selection. Mirrors the ``grd_harness_rounds`` CRUD shape.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_plan_selection_id

logger = logging.getLogger(__name__)


def upsert_plan_selection(
    *,
    project_id: str,
    phase: str,
    milestone: Optional[str] = None,
    winner_rel: Optional[str] = None,
    promoted_to: Optional[str] = None,
    candidates_json: Optional[str] = None,
    audit_json: Optional[str] = None,
) -> str:
    """Insert or fully-replace the selection row for ``(project_id, phase)``.
    Returns the stable ``psel-`` mirror id (preserved across upserts)."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM grd_plan_selections WHERE project_id = ? AND phase = ?",
            (project_id, phase),
        ).fetchone()
        if existing:
            pid = existing["id"]
            conn.execute(
                """
                UPDATE grd_plan_selections
                SET milestone = ?, winner_rel = ?, promoted_to = ?,
                    candidates_json = ?, audit_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (milestone, winner_rel, promoted_to, candidates_json, audit_json, pid),
            )
        else:
            pid = _get_unique_plan_selection_id(conn)
            conn.execute(
                """
                INSERT INTO grd_plan_selections
                    (id, project_id, phase, milestone, winner_rel, promoted_to,
                     candidates_json, audit_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (pid, project_id, phase, milestone, winner_rel, promoted_to,
                 candidates_json, audit_json),
            )
        conn.commit()
        return pid


def get_plan_selection(project_id: str, phase: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM grd_plan_selections WHERE project_id = ? AND phase = ?",
            (project_id, phase),
        ).fetchone()
        return _row_to_dict(row) if row else None


def list_plan_selections(project_id: str, *, limit: int = 50) -> List[dict]:
    """Project plan selections, newest first."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT * FROM grd_plan_selections
            WHERE project_id = ?
            ORDER BY created_at DESC, phase DESC
            LIMIT ?
            """,
            (project_id, limit),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]


def _row_to_dict(row) -> dict:
    d = {k: row[k] for k in row.keys()}
    for json_col, parsed_key in (("candidates_json", "candidates"), ("audit_json", "audit")):
        if d.get(json_col):
            try:
                d[parsed_key] = json.loads(d[json_col])
            except (json.JSONDecodeError, TypeError):
                d[parsed_key] = None
    return d
