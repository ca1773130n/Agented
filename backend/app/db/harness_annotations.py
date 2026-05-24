"""Repository helpers for Life-Harness failure annotations (T1).

Thin SQL layer over ``execution_layer_incidents`` + ``execution_annotations``.
No business logic — see ``app.services.harness_failure_annotator``.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from .connection import get_connection
from .ids import generate_id


# Layer → priority (lower wins for the per-execution primary_layer).
LAYER_PRIORITY: dict[str, int] = {"h2": 2, "h3": 3, "h4": 4, "general": 5}


def replace_incidents(
    execution_id: str,
    incidents: Iterable[dict[str, Any]],
    *,
    detector_version: str,
    annotator_version: str,
    outcome: Optional[str],
) -> dict[str, int]:
    """Atomically replace all incidents for ``execution_id`` and refresh the
    roll-up row. Returns the counts written.

    Each incident dict must carry: ``layer``, ``kind``, ``evidence`` (any
    JSON-serializable), and optionally ``event_index``.
    """
    rows: list[tuple] = []
    counts = {"h2": 0, "h3": 0, "h4": 0, "general": 0}

    for inc in incidents:
        layer = inc["layer"]
        if layer not in LAYER_PRIORITY:
            raise ValueError(f"unknown harness layer: {layer!r}")
        counts[layer] += 1
        rows.append(
            (
                generate_id("inc"),
                execution_id,
                layer,
                LAYER_PRIORITY[layer],
                inc["kind"],
                json.dumps(inc.get("evidence", {}), default=str),
                inc.get("event_index"),
                detector_version,
            )
        )

    total = sum(counts.values())
    primary = _pick_primary(counts)

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM execution_layer_incidents WHERE execution_id = ?",
            (execution_id,),
        )
        if rows:
            conn.executemany(
                """INSERT INTO execution_layer_incidents
                   (id, execution_id, layer, priority, kind,
                    evidence_json, event_index, detector_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
        conn.execute(
            """INSERT INTO execution_annotations
               (execution_id, annotator_version, primary_layer, incident_count,
                h2_count, h3_count, h4_count, general_count, outcome,
                annotated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(execution_id) DO UPDATE SET
                   annotator_version=excluded.annotator_version,
                   primary_layer=excluded.primary_layer,
                   incident_count=excluded.incident_count,
                   h2_count=excluded.h2_count,
                   h3_count=excluded.h3_count,
                   h4_count=excluded.h4_count,
                   general_count=excluded.general_count,
                   outcome=excluded.outcome,
                   annotated_at=datetime('now')""",
            (
                execution_id,
                annotator_version,
                primary,
                total,
                counts["h2"],
                counts["h3"],
                counts["h4"],
                counts["general"],
                outcome,
            ),
        )
        conn.commit()

    return {"primary_layer": primary, "total": total, **counts}


def get_annotation(execution_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM execution_annotations WHERE execution_id = ?",
            (execution_id,),
        ).fetchone()
    return dict(row) if row else None


def list_incidents(execution_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, layer, priority, kind, evidence_json, event_index,
                      detector_version, created_at
               FROM execution_layer_incidents
               WHERE execution_id = ?
               ORDER BY priority ASC, event_index ASC NULLS LAST, id ASC""",
            (execution_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["evidence"] = json.loads(d.pop("evidence_json"))
        except (TypeError, ValueError):
            d["evidence"] = {}
        out.append(d)
    return out


def _pick_primary(counts: dict[str, int]) -> Optional[str]:
    """Lowest-priority layer with any incident, matching the paper's
    priority-based annotation protocol (H2 wins over H3 wins over H4)."""
    for layer in ("h2", "h3", "h4", "general"):
        if counts.get(layer, 0) > 0:
            return layer
    return None


# ---------------------------------------------------------------------------
# Aggregate / lookup queries — fed to the Activity-lane summary card
# ---------------------------------------------------------------------------

def summary_counts(*, since: Optional[str] = None) -> dict[str, int]:
    """Return ``{"h2": N, "h3": N, "h4": N, "general": N, "none": N, "total": N}``.

    ``since`` is compared against ``annotated_at``; an ISO-8601 string. ``none``
    counts annotated rows with no incidents (typically successful runs).
    """
    where = ""
    params: list = []
    if since:
        where = "WHERE annotated_at >= ?"
        params.append(since)
    with get_connection() as conn:
        row = conn.execute(
            f"""SELECT
                   COUNT(*) AS total,
                   SUM(h2_count > 0) AS h2,
                   SUM(h3_count > 0) AS h3,
                   SUM(h4_count > 0) AS h4,
                   SUM(general_count > 0) AS gen,
                   SUM(primary_layer IS NULL) AS none_count
                FROM execution_annotations {where}""",
            params,
        ).fetchone()
    return {
        "h2": int(row["h2"] or 0),
        "h3": int(row["h3"] or 0),
        "h4": int(row["h4"] or 0),
        "general": int(row["gen"] or 0),
        "none": int(row["none_count"] or 0),
        "total": int(row["total"] or 0),
    }


def recent_with_layer(
    *,
    since: Optional[str] = None,
    primary_layer: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """Recent annotations with at least one incident, newest first.

    Pass ``primary_layer="h2"`` etc. to scope to a single layer.
    """
    where = ["primary_layer IS NOT NULL"]
    params: list = []
    if since:
        where.append("annotated_at >= ?")
        params.append(since)
    if primary_layer:
        where.append("primary_layer = ?")
        params.append(primary_layer)
    params.append(int(limit))
    with get_connection() as conn:
        rows = conn.execute(
            f"""SELECT execution_id, primary_layer, incident_count,
                       h2_count, h3_count, h4_count, general_count,
                       outcome, annotated_at
                FROM execution_annotations
                WHERE {" AND ".join(where)}
                ORDER BY annotated_at DESC
                LIMIT ?""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]
