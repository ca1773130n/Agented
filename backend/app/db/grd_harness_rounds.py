"""CRUD for ``grd_harness_rounds`` — mirror of GRD 0.4.x ``gd harness round``.

One row per ``(project_id, round_id)``. ``upsert_harness_round`` is a full
replace of the round record: the runner inserts a minimal ``running`` row when
it triggers a round, then upserts the complete record (status / patch / eval /
confidence) once the round finishes. Mirrors the ``grd_evolve`` CRUD shape.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_harness_round_id

logger = logging.getLogger(__name__)


def upsert_harness_round(
    *,
    project_id: str,
    round_id: str,
    status: str,
    detail: Optional[str] = None,
    evidence_count: Optional[int] = None,
    patch_hash: Optional[str] = None,
    confidence: Optional[float] = None,
    summary: Optional[str] = None,
    applied_sha: Optional[str] = None,
    eval_json: Optional[str] = None,
    patch_json: Optional[str] = None,
) -> str:
    """Insert or fully-replace a round row keyed on ``(project_id, round_id)``.
    Returns the stable ``hround-`` mirror id (preserved across upserts).
    """
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM grd_harness_rounds WHERE project_id = ? AND round_id = ?",
            (project_id, round_id),
        ).fetchone()
        if existing:
            hid = existing["id"]
            conn.execute(
                """
                UPDATE grd_harness_rounds
                SET status = ?, detail = ?, evidence_count = ?, patch_hash = ?,
                    confidence = ?, summary = ?, applied_sha = ?, eval_json = ?,
                    patch_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, detail, evidence_count, patch_hash, confidence, summary,
                 applied_sha, eval_json, patch_json, hid),
            )
        else:
            hid = _get_unique_harness_round_id(conn)
            conn.execute(
                """
                INSERT INTO grd_harness_rounds
                    (id, project_id, round_id, status, detail, evidence_count,
                     patch_hash, confidence, summary, applied_sha, eval_json, patch_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (hid, project_id, round_id, status, detail, evidence_count, patch_hash,
                 confidence, summary, applied_sha, eval_json, patch_json),
            )
        conn.commit()
        return hid


def get_harness_round(project_id: str, round_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM grd_harness_rounds WHERE project_id = ? AND round_id = ?",
            (project_id, round_id),
        ).fetchone()
        return _row_to_dict(row) if row else None


def list_harness_rounds(project_id: str, *, limit: int = 50) -> List[dict]:
    """Project harness rounds, newest first."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT * FROM grd_harness_rounds
            WHERE project_id = ?
            ORDER BY created_at DESC, round_id DESC
            LIMIT ?
            """,
            (project_id, limit),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]


def _row_to_dict(row) -> dict:
    d = {k: row[k] for k in row.keys()}
    for json_col, parsed_key in (("eval_json", "eval"), ("patch_json", "patch")):
        if d.get(json_col):
            try:
                d[parsed_key] = json.loads(d[json_col])
            except (json.JSONDecodeError, TypeError):
                d[parsed_key] = None
    return d
