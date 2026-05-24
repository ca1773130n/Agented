"""Repository helpers for Life-Harness session annotations (session-scoped).

Thin SQL layer over ``session_layer_incidents`` + ``session_annotations``.
All identifiers are polymorphic ``(session_kind, session_id)`` so the
annotator works across every session producer (trigger executions,
workflow nodes, super-agent sessions, project sessions).
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from .connection import get_connection
from .ids import generate_id


LAYER_PRIORITY: dict[str, int] = {"h2": 2, "h3": 3, "h4": 4, "general": 5}


def replace_incidents(
    session_kind: str,
    session_id: str,
    incidents: Iterable[dict[str, Any]],
    *,
    project_id: Optional[str],
    detector_version: str,
    annotator_version: str,
    outcome: Optional[str],
) -> dict[str, int]:
    """Atomically replace all incidents for the session and refresh the
    summary row. Returns the counts written."""
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
                session_kind,
                session_id,
                project_id,
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
            "DELETE FROM session_layer_incidents WHERE session_kind = ? "
            "AND session_id = ?",
            (session_kind, session_id),
        )
        if rows:
            conn.executemany(
                """INSERT INTO session_layer_incidents
                   (id, session_kind, session_id, project_id, layer, priority,
                    kind, evidence_json, event_index, detector_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
        conn.execute(
            """INSERT INTO session_annotations
               (session_kind, session_id, project_id, annotator_version,
                primary_layer, incident_count, h2_count, h3_count, h4_count,
                general_count, outcome, annotated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(session_kind, session_id) DO UPDATE SET
                   project_id        = excluded.project_id,
                   annotator_version = excluded.annotator_version,
                   primary_layer     = excluded.primary_layer,
                   incident_count    = excluded.incident_count,
                   h2_count          = excluded.h2_count,
                   h3_count          = excluded.h3_count,
                   h4_count          = excluded.h4_count,
                   general_count     = excluded.general_count,
                   outcome           = excluded.outcome,
                   annotated_at      = datetime('now')""",
            (
                session_kind,
                session_id,
                project_id,
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


def get_annotation(session_kind: str, session_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM session_annotations "
            "WHERE session_kind = ? AND session_id = ?",
            (session_kind, session_id),
        ).fetchone()
    return dict(row) if row else None


def list_incidents(session_kind: str, session_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, layer, priority, kind, evidence_json, event_index,
                      detector_version, created_at
               FROM session_layer_incidents
               WHERE session_kind = ? AND session_id = ?
               ORDER BY priority ASC, event_index ASC NULLS LAST, id ASC""",
            (session_kind, session_id),
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


def summary_counts(
    *,
    since: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict[str, int]:
    """Aggregate counts across all sessions. Filter by ``project_id`` to
    scope to a single project's annotation surface."""
    where = []
    params: list[Any] = []
    if since:
        where.append("annotated_at >= ?")
        params.append(since)
    if project_id is not None:
        where.append("project_id = ?")
        params.append(project_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    with get_connection() as conn:
        row = conn.execute(
            f"""SELECT
                   COUNT(*) AS total,
                   SUM(h2_count > 0) AS h2,
                   SUM(h3_count > 0) AS h3,
                   SUM(h4_count > 0) AS h4,
                   SUM(general_count > 0) AS gen,
                   SUM(primary_layer IS NULL) AS none_count
                FROM session_annotations {where_sql}""",
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
    project_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """Recent annotations with at least one incident, newest first."""
    where = ["primary_layer IS NOT NULL"]
    params: list[Any] = []
    if since:
        where.append("annotated_at >= ?")
        params.append(since)
    if primary_layer:
        where.append("primary_layer = ?")
        params.append(primary_layer)
    if project_id is not None:
        where.append("project_id = ?")
        params.append(project_id)
    params.append(int(limit))
    with get_connection() as conn:
        rows = conn.execute(
            f"""SELECT session_kind, session_id, project_id, primary_layer,
                       incident_count, h2_count, h3_count, h4_count,
                       general_count, outcome, annotated_at
                FROM session_annotations
                WHERE {" AND ".join(where)}
                ORDER BY annotated_at DESC
                LIMIT ?""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def _pick_primary(counts: dict[str, int]) -> Optional[str]:
    for layer in ("h2", "h3", "h4", "general"):
        if counts.get(layer, 0) > 0:
            return layer
    return None
