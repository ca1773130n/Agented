"""Repository helpers for per-execution harness snapshots (T2 integration)."""

from __future__ import annotations

import json
from typing import Any, Optional

from .connection import get_connection


def upsert_snapshot(
    *,
    execution_id: str,
    bot_id: str,
    harness_kind: str,
    layer_versions: dict[str, int],
    artifact: dict[str, Any],
    applied: bool = False,
) -> None:
    """Record (or replace) the harness snapshot for this execution."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO execution_harness_snapshots
                   (execution_id, bot_id, harness_kind, layer_versions_json,
                    artifact_json, applied)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(execution_id) DO UPDATE SET
                   bot_id              = excluded.bot_id,
                   harness_kind        = excluded.harness_kind,
                   layer_versions_json = excluded.layer_versions_json,
                   artifact_json       = excluded.artifact_json,
                   applied             = excluded.applied""",
            (
                execution_id,
                bot_id,
                harness_kind,
                json.dumps(layer_versions, default=str),
                json.dumps(artifact, default=str),
                1 if applied else 0,
            ),
        )
        conn.commit()


def get_snapshot(execution_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM execution_harness_snapshots WHERE execution_id = ?",
            (execution_id,),
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    try:
        d["layer_versions"] = json.loads(d.pop("layer_versions_json") or "{}")
    except (TypeError, ValueError):
        d["layer_versions"] = {}
    try:
        d["artifact"] = json.loads(d.pop("artifact_json") or "{}")
    except (TypeError, ValueError):
        d["artifact"] = {}
    d["applied"] = bool(d["applied"])
    return d


def list_for_bot(
    bot_id: str, *, layer: Optional[str] = None, version: Optional[int] = None
) -> list[dict]:
    """List snapshots for a bot, newest first. Optionally filter by a single
    layer + version (used by T3 to gather "all trajectories from H3 v2")."""
    sql = [
        "SELECT execution_id, bot_id, harness_kind, layer_versions_json,",
        "       applied, created_at",
        "FROM execution_harness_snapshots",
        "WHERE bot_id = ?",
    ]
    params: list[Any] = [bot_id]
    if layer is not None and version is not None:
        # SQLite JSON1 — extract the layer's version key and compare.
        sql.append("AND CAST(json_extract(layer_versions_json, ?) AS INTEGER) = ?")
        params.extend([f"$.{layer}", int(version)])
    sql.append("ORDER BY created_at DESC")

    with get_connection() as conn:
        rows = conn.execute("\n".join(sql), params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["layer_versions"] = json.loads(d.pop("layer_versions_json") or "{}")
        except (TypeError, ValueError):
            d["layer_versions"] = {}
        d["applied"] = bool(d["applied"])
        out.append(d)
    return out
