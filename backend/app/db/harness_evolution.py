"""Repository helpers for ``harness_evolution_rounds`` (project-scoped)."""

from __future__ import annotations

import json
from typing import Any, Optional

from .connection import get_connection
from .ids import generate_id


def start_round(
    *,
    project_id: str,
    input_window_since: Optional[str],
    input_window_until: Optional[str],
    input_execution_count: int,
    input_forge: dict[str, Any],
    scratch_dir: Optional[str] = None,
    input_kg_signals: Optional[list] = None,
) -> str:
    """Insert a fresh round in ``pending`` status. Returns the round id."""
    round_id = generate_id("her")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO harness_evolution_rounds
                   (id, project_id, status, input_window_since, input_window_until,
                    input_execution_count, input_forge_json, input_kg_signals_json,
                    scratch_dir)
               VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?)""",
            (
                round_id,
                project_id,
                input_window_since,
                input_window_until,
                int(input_execution_count),
                json.dumps(input_forge, default=str),
                json.dumps(input_kg_signals or [], default=str),
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


_ROUND_COLUMNS_IN_ORDER = (
    "id",
    "project_id",
    "started_at",
    "finished_at",
    "status",
    "input_window_since",
    "input_window_until",
    "input_execution_count",
    "input_forge_json",
    "input_kg_signals_json",
    "output_patch_json",
    "applied_asset_ids_json",
    "error_message",
    "notes",
    "scratch_dir",
    "materialization_result_json",
    "git_commit_sha",
    "eval_verdict_json",
    "apply_journal_json",
    "reverted_at",
    "revert_error",
    "auto_applied",
    "auto_apply_reason",
    "auto_apply_blocked_reason",
)


def _ensure_materialization_columns(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")}
    if "materialization_result_json" not in cols:
        conn.execute(
            "ALTER TABLE harness_evolution_rounds ADD COLUMN materialization_result_json TEXT"
        )
    if "git_commit_sha" not in cols:
        conn.execute("ALTER TABLE harness_evolution_rounds ADD COLUMN git_commit_sha TEXT")


def _check_allows_evaluating(conn) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='harness_evolution_rounds'"
    ).fetchone()
    return bool(row) and "evaluating" in (row["sql"] or "")


def _ensure_eval_columns(conn) -> None:
    _ensure_materialization_columns(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")}
    if "eval_verdict_json" not in cols:
        conn.execute("ALTER TABLE harness_evolution_rounds ADD COLUMN eval_verdict_json TEXT")
    if _check_allows_evaluating(conn):
        return
    from app.db.schema._harness_evolution import create_harness_evolution_tables

    cols_now = [r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")]
    shared = [c for c in _ROUND_COLUMNS_IN_ORDER if c in cols_now]
    collist = ", ".join(shared)
    conn.execute("DROP TABLE IF EXISTS _her_old")  # clear any crash-orphan first
    conn.execute("ALTER TABLE harness_evolution_rounds RENAME TO _her_old")
    # indexes follow the table on RENAME — free their names so create can rebuild them
    conn.execute("DROP INDEX IF EXISTS idx_her_project")
    conn.execute("DROP INDEX IF EXISTS idx_her_status")
    create_harness_evolution_tables(conn)
    conn.execute(f"INSERT INTO harness_evolution_rounds ({collist}) SELECT {collist} FROM _her_old")
    conn.execute("DROP TABLE _her_old")


def _ensure_revert_columns(conn) -> None:
    _ensure_eval_columns(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")}
    for col in ("apply_journal_json", "reverted_at", "revert_error"):
        if col not in cols:
            conn.execute(f"ALTER TABLE harness_evolution_rounds ADD COLUMN {col} TEXT")


def _ensure_autonomy_columns(conn) -> None:
    _ensure_revert_columns(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")}
    if "auto_applied" not in cols:
        conn.execute(
            "ALTER TABLE harness_evolution_rounds ADD COLUMN auto_applied INTEGER NOT NULL DEFAULT 0"
        )
    for col in ("auto_apply_reason", "auto_apply_blocked_reason"):
        if col not in cols:
            conn.execute(f"ALTER TABLE harness_evolution_rounds ADD COLUMN {col} TEXT")


def _ensure_kg_signals_column(conn) -> None:
    _ensure_autonomy_columns(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")}
    if "input_kg_signals_json" not in cols:
        conn.execute(
            "ALTER TABLE harness_evolution_rounds "
            "ADD COLUMN input_kg_signals_json TEXT NOT NULL DEFAULT '[]'"
        )


def mark_applied(
    round_id: str,
    *,
    output_patch: dict[str, Any],
    applied_asset_ids: list[Any],
    notes: Optional[str] = None,
    materialization_result_json: Optional[str] = None,
    git_commit_sha: Optional[str] = None,
    apply_journal_json: Optional[str] = None,
    auto_applied: bool = False,
    auto_apply_reason: Optional[dict] = None,
) -> bool:
    """Transition a round to ``applied``.

    [04.H2] The transition is now CONDITIONAL on the round not already
    being ``applied`` / ``reverted`` — guards against a double-apply where
    two concurrent callers both reach this point. Returns ``True`` iff this
    call performed the transition (rowcount == 1).
    """
    with get_connection() as conn:
        _ensure_kg_signals_column(conn)
        cur = conn.execute(
            """UPDATE harness_evolution_rounds SET
                   status                      = 'applied',
                   finished_at                 = datetime('now'),
                   output_patch_json           = ?,
                   applied_asset_ids_json      = ?,
                   notes                       = ?,
                   materialization_result_json = ?,
                   git_commit_sha              = ?,
                   apply_journal_json          = ?,
                   auto_applied                = ?,
                   auto_apply_reason           = ?
               WHERE id = ?
                 AND status NOT IN ('applied', 'reverted')""",
            (
                json.dumps(output_patch, default=str),
                json.dumps(applied_asset_ids, default=str),
                notes,
                materialization_result_json,
                git_commit_sha,
                apply_journal_json,
                1 if auto_applied else 0,
                json.dumps(auto_apply_reason) if auto_apply_reason else None,
                round_id,
            ),
        )
        conn.commit()
        return cur.rowcount == 1


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


def mark_failed(
    round_id: str,
    *,
    error_message: str,
    output_patch: Optional[dict[str, Any]] = None,
    apply_journal_json: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE harness_evolution_rounds SET
                   status            = 'failed',
                   finished_at       = datetime('now'),
                   error_message     = ?,
                   output_patch_json = COALESCE(?, output_patch_json),
                   apply_journal_json = COALESCE(?, apply_journal_json)
               WHERE id = ?""",
            (
                (error_message or "")[:4000],
                json.dumps(output_patch, default=str) if output_patch else None,
                apply_journal_json,
                round_id,
            ),
        )
        conn.commit()


def mark_aborted(round_id: str, *, reason: Optional[str] = None) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE harness_evolution_rounds SET
                   status        = 'aborted',
                   finished_at   = datetime('now'),
                   error_message = ?
               WHERE id = ?""",
            ((reason or "")[:4000] if reason else None, round_id),
        )
        conn.commit()


def mark_evaluating(round_id: str) -> None:
    with get_connection() as conn:
        _ensure_eval_columns(conn)
        conn.execute(
            "UPDATE harness_evolution_rounds SET status = 'evaluating' "
            "WHERE id = ? AND status = 'running'",
            (round_id,),
        )
        conn.commit()


def store_eval_verdict(round_id: str, verdict) -> None:
    with get_connection() as conn:
        _ensure_eval_columns(conn)
        conn.execute(
            "UPDATE harness_evolution_rounds SET eval_verdict_json = ? WHERE id = ?",
            (verdict.model_dump_json(), round_id),
        )
        conn.commit()


def mark_eval_failed(round_id: str, *, verdict) -> None:
    with get_connection() as conn:
        _ensure_eval_columns(conn)
        conn.execute(
            """UPDATE harness_evolution_rounds SET
                   status = 'eval_failed', finished_at = datetime('now'),
                   eval_verdict_json = ?
               WHERE id = ?""",
            (verdict.model_dump_json(), round_id),
        )
        conn.commit()


def mark_reverted(round_id: str) -> None:
    with get_connection() as conn:
        _ensure_revert_columns(conn)
        conn.execute(
            "UPDATE harness_evolution_rounds SET status='reverted', reverted_at=datetime('now') "
            "WHERE id=? AND status='applied'",
            (round_id,),
        )
        conn.commit()


def set_revert_error(round_id: str, error: str) -> None:
    with get_connection() as conn:
        _ensure_revert_columns(conn)
        conn.execute(
            "UPDATE harness_evolution_rounds SET revert_error=? "
            "WHERE id=? AND status IN ('applied', 'reverted')",
            ((error or "")[:2000], round_id),
        )
        conn.commit()


def mark_auto_apply_blocked(round_id: str, reason: dict) -> None:
    with get_connection() as conn:
        _ensure_kg_signals_column(conn)
        conn.execute(
            "UPDATE harness_evolution_rounds SET auto_apply_blocked_reason = ? "
            "WHERE id = ? AND status = 'awaiting_approval'",
            (json.dumps(reason), round_id),
        )
        conn.commit()


def count_recent_auto_applies(project_id: str, *, since: str) -> int:
    with get_connection() as conn:
        _ensure_kg_signals_column(conn)
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM harness_evolution_rounds "
            "WHERE project_id = ? AND auto_applied = 1 AND finished_at >= ?",
            (project_id, since),
        ).fetchone()
    return int(row["c"]) if row else 0


def get_round(round_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM harness_evolution_rounds WHERE id = ?",
            (round_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def list_for_project(project_id: str, *, limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM harness_evolution_rounds WHERE project_id = ? "
            "ORDER BY started_at DESC LIMIT ?",
            (project_id, int(limit)),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_all(*, limit: int = 50, status: Optional[str] = None) -> list[dict]:
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
        ("input_forge_json", "{}"),
        ("output_patch_json", "null"),
        ("applied_asset_ids_json", "[]"),
        ("eval_verdict_json", "null"),
        ("apply_journal_json", "null"),
    ):
        out_key = key.replace("_json", "")
        try:
            d[out_key] = json.loads(d.pop(key) or default)
        except (TypeError, ValueError):
            d[out_key] = None
    for key in ("auto_apply_reason", "auto_apply_blocked_reason"):
        try:
            d[key] = json.loads(d[key] or "null")
        except (TypeError, ValueError):
            d[key] = None
    return d
