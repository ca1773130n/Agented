"""Repository helpers for the durable harness run-state store.

See ``app.db.schema._harness_state`` for the DDL and
``docs/research/harness-1-integration.md`` for the design (Harness-1 state
externalization, P1). ``record_checkpoint`` is the core primitive: in one
transaction it bumps the per-run step cursor and appends a serialized
ledger snapshot, returning the new step number.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .connection import get_connection


def record_checkpoint(
    execution_id: str,
    *,
    ledger: Any,
    budget_used: Optional[float] = None,
    status: str = "running",
) -> int:
    """Upsert the run row (incrementing its step cursor) and append a
    checkpoint carrying ``ledger`` (JSON-serialized). Returns the new step.

    ``budget_used`` is a running total: set when provided, kept when omitted.
    """
    payload = json.dumps(ledger, default=str)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO harness_runs (execution_id, status, step_cursor, budget_used, updated_at)
                VALUES (?, ?, 1, COALESCE(?, 0), datetime('now'))
            ON CONFLICT(execution_id) DO UPDATE SET
                step_cursor = harness_runs.step_cursor + 1,
                status      = excluded.status,
                budget_used = COALESCE(?, harness_runs.budget_used),
                updated_at  = datetime('now')
            """,
            (execution_id, status, budget_used, budget_used),
        )
        step = conn.execute(
            "SELECT step_cursor FROM harness_runs WHERE execution_id = ?",
            (execution_id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO harness_checkpoints (execution_id, step, ledger_json) VALUES (?, ?, ?)",
            (execution_id, step, payload),
        )
        conn.commit()
    return int(step)


def mark_run_status(execution_id: str, status: str) -> bool:
    """Set the run's lifecycle status (e.g. 'finished'/'failed'). Returns
    True if a run row existed. No-op (False) for un-checkpointed runs."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE harness_runs SET status = ?, updated_at = datetime('now') "
            "WHERE execution_id = ?",
            (status, execution_id),
        )
        conn.commit()
        return cur.rowcount > 0


def get_run(execution_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM harness_runs WHERE execution_id = ?", (execution_id,)
        ).fetchone()
    return dict(row) if row else None


def get_latest_checkpoint(execution_id: str) -> Optional[dict]:
    """Most recent checkpoint for recovery, with ``ledger`` deserialized."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM harness_checkpoints WHERE execution_id = ? ORDER BY step DESC LIMIT 1",
            (execution_id,),
        ).fetchone()
    return _checkpoint_to_dict(row) if row else None


def list_checkpoints(execution_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM harness_checkpoints WHERE execution_id = ? ORDER BY step ASC",
            (execution_id,),
        ).fetchall()
    return [_checkpoint_to_dict(r) for r in rows]


def _checkpoint_to_dict(row) -> dict:
    d = dict(row)
    try:
        d["ledger"] = json.loads(d.pop("ledger_json") or "{}")
    except (TypeError, ValueError):
        d["ledger"] = {}
    return d
