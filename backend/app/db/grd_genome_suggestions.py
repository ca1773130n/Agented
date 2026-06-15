"""CRUD for ``grd_genome_suggestions`` — mirror of GRD 0.4.1 ``gd patterns``.

One row per project holding the LATEST pattern-mining run (full replace). The
miner is deterministic + cheap to re-run; this mirror just lets the operator
surface (and promote from) the last result without re-running. Mirrors the
``grd_harness_rounds`` CRUD shape.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_genome_suggestions_id

logger = logging.getLogger(__name__)


def upsert_genome_suggestions(
    *,
    project_id: str,
    reflections_scanned: Optional[int] = None,
    baseline_confirmed_rate: Optional[float] = None,
    tokens_tested: Optional[int] = None,
    suggestions_json: Optional[str] = None,
    applied: bool = False,
    suggestions_path: Optional[str] = None,
) -> str:
    """Insert or fully-replace the latest patterns run for ``project_id``.
    Returns the stable ``gsug-`` mirror id (preserved across upserts)."""
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM grd_genome_suggestions WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        if existing:
            gid = existing["id"]
            conn.execute(
                """
                UPDATE grd_genome_suggestions
                SET reflections_scanned = ?, baseline_confirmed_rate = ?,
                    tokens_tested = ?, suggestions_json = ?, applied = ?,
                    suggestions_path = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (reflections_scanned, baseline_confirmed_rate, tokens_tested,
                 suggestions_json, 1 if applied else 0, suggestions_path, gid),
            )
        else:
            gid = _get_unique_genome_suggestions_id(conn)
            conn.execute(
                """
                INSERT INTO grd_genome_suggestions
                    (id, project_id, reflections_scanned, baseline_confirmed_rate,
                     tokens_tested, suggestions_json, applied, suggestions_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (gid, project_id, reflections_scanned, baseline_confirmed_rate,
                 tokens_tested, suggestions_json, 1 if applied else 0, suggestions_path),
            )
        conn.commit()
        return gid


def get_genome_suggestions(project_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM grd_genome_suggestions WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None


def list_genome_suggestions(project_id: str, *, limit: int = 50) -> List[dict]:
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM grd_genome_suggestions WHERE project_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (project_id, limit),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]


def _row_to_dict(row) -> dict:
    d = {k: row[k] for k in row.keys()}
    d["applied"] = bool(d.get("applied"))
    if d.get("suggestions_json"):
        try:
            d["suggestions"] = json.loads(d["suggestions_json"])
        except (json.JSONDecodeError, TypeError):
            d["suggestions"] = None
    return d
