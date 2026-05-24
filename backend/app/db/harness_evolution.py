"""Repository helpers for ``harness_evolution_rounds`` (T3)."""

from __future__ import annotations

import json
from typing import Any, Optional

from .connection import get_connection
from .ids import generate_id


def start_round(
    *,
    bot_id: str,
    input_window_since: Optional[str],
    input_window_until: Optional[str],
    input_execution_count: int,
    input_layers: dict[str, Any],
    scratch_dir: Optional[str] = None,
) -> str:
    """Insert a fresh round row in ``pending`` status. Returns the round id."""
    round_id = generate_id("her")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO harness_evolution_rounds
                   (id, bot_id, status, input_window_since, input_window_until,
                    input_execution_count, input_layers_json, scratch_dir)
               VALUES (?, ?, 'pending', ?, ?, ?, ?, ?)""",
            (
                round_id,
                bot_id,
                input_window_since,
                input_window_until,
                int(input_execution_count),
                json.dumps(input_layers, default=str),
                scratch_dir,
            ),
        )
        conn.commit()
    return round_id


def mark_running(round_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE harness_evolution_rounds SET status = 'running' "
            "WHERE id = ? AND status = 'pending'",
            (round_id,),
        )
        conn.commit()


def mark_applied(
    round_id: str,
    *,
    output_patch: dict[str, Any],
    applied_layer_ids: list[str],
    notes: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE harness_evolution_rounds SET
                   status                 = 'applied',
                   finished_at            = datetime('now'),
                   output_patch_json      = ?,
                   applied_layer_ids_json = ?,
                   notes                  = ?
               WHERE id = ?""",
            (
                json.dumps(output_patch, default=str),
                json.dumps(applied_layer_ids),
                notes,
                round_id,
            ),
        )
        conn.commit()


def mark_awaiting_approval(
    round_id: str,
    *,
    output_patch: dict[str, Any],
    notes: Optional[str] = None,
) -> None:
    """Dry-run completed Codex + validation; patch is held for human approval."""
    with get_connection() as conn:
        conn.execute(
            """UPDATE harness_evolution_rounds SET
                   status            = 'awaiting_approval',
                   finished_at       = datetime('now'),
                   output_patch_json = ?,
                   notes             = ?
               WHERE id = ?""",
            (
                json.dumps(output_patch, default=str),
                notes,
                round_id,
            ),
        )
        conn.commit()


def mark_aborted(round_id: str, *, reason: Optional[str] = None) -> None:
    """Operator rejected a dry-run patch (or aborted some other in-flight round)."""
    with get_connection() as conn:
        conn.execute(
            """UPDATE harness_evolution_rounds SET
                   status        = 'aborted',
                   finished_at   = datetime('now'),
                   error_message = ?
               WHERE id = ?""",
            (reason[:4000] if reason else None, round_id),
        )
        conn.commit()


def mark_failed(round_id: str, *, error_message: str,
                output_patch: Optional[dict[str, Any]] = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE harness_evolution_rounds SET
                   status            = 'failed',
                   finished_at       = datetime('now'),
                   error_message     = ?,
                   output_patch_json = COALESCE(?, output_patch_json)
               WHERE id = ?""",
            (
                error_message[:4000],
                json.dumps(output_patch, default=str) if output_patch else None,
                round_id,
            ),
        )
        conn.commit()


def get_round(round_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM harness_evolution_rounds WHERE id = ?",
            (round_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def list_for_bot(bot_id: str, *, limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM harness_evolution_rounds WHERE bot_id = ? "
            "ORDER BY started_at DESC LIMIT ?",
            (bot_id, int(limit)),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_all(*, limit: int = 50, status: Optional[str] = None) -> list[dict]:
    """Cross-bot listing — newest rounds first. Optional ``status`` filter."""
    sql = ["SELECT * FROM harness_evolution_rounds"]
    params: list[Any] = []
    if status:
        sql.append("WHERE status = ?")
        params.append(status)
    sql.append("ORDER BY started_at DESC LIMIT ?")
    params.append(int(limit))
    with get_connection() as conn:
        rows = conn.execute("\n".join(sql), params).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row) -> dict:
    d = dict(row)
    for key, default in (
        ("input_layers_json", "{}"),
        ("output_patch_json", "null"),
        ("applied_layer_ids_json", "[]"),
    ):
        out_key = key.replace("_json", "")
        try:
            d[out_key] = json.loads(d.pop(key) or default)
        except (TypeError, ValueError):
            d[out_key] = None
    return d
