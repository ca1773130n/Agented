"""Repository helpers for per-execution harness snapshots.

Records which Forge primitives were active for an execution: a hash of the
rendered ``ContextBundle`` plus the ``(kind, asset_id)`` pairs that fed
into it. T3's evolution loop joins on ``project_id`` + this table +
``execution_annotations`` to compute pre/post-evolution impact deltas.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .connection import get_connection


def upsert_snapshot(
    *,
    execution_id: str,
    project_id: Optional[str],
    bot_id: Optional[str],
    harness_kind: str,
    bundle_hash: Optional[str],
    resolved_bindings: list[dict[str, Any]],
) -> None:
    """Record (or replace) the Forge snapshot for this execution."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO execution_harness_snapshots
                   (execution_id, project_id, bot_id, harness_kind,
                    bundle_hash, resolved_bindings_json)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(execution_id) DO UPDATE SET
                   project_id              = excluded.project_id,
                   bot_id                  = excluded.bot_id,
                   harness_kind            = excluded.harness_kind,
                   bundle_hash             = excluded.bundle_hash,
                   resolved_bindings_json  = excluded.resolved_bindings_json""",
            (
                execution_id,
                project_id,
                bot_id,
                harness_kind,
                bundle_hash,
                json.dumps(resolved_bindings, default=str),
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
    return _row_to_dict(row)


def list_for_project(
    project_id: str,
    *,
    bundle_hash: Optional[str] = None,
    before_ts: Optional[str] = None,
    after_ts: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Project-scoped snapshot listing, newest first. Used by T3's impact
    eval to gather windows before / after an evolution round."""
    sql = [
        "SELECT * FROM execution_harness_snapshots WHERE project_id = ?",
    ]
    params: list[Any] = [project_id]
    if bundle_hash is not None:
        sql.append("AND bundle_hash = ?")
        params.append(bundle_hash)
    if before_ts is not None:
        sql.append("AND created_at < ?")
        params.append(before_ts)
    if after_ts is not None:
        sql.append("AND created_at > ?")
        params.append(after_ts)
    sql.append("ORDER BY created_at DESC LIMIT ?")
    params.append(int(limit))
    with get_connection() as conn:
        rows = conn.execute("\n".join(sql), params).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row) -> dict:
    d = dict(row)
    try:
        d["resolved_bindings"] = json.loads(
            d.pop("resolved_bindings_json") or "[]"
        )
    except (TypeError, ValueError):
        d["resolved_bindings"] = []
    return d
