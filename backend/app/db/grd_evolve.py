"""CRUD for ``grd_evolve_runs`` (v0.7.88).

One row per ``gd evolve`` invocation. The row is the durable
hook the UI uses to render progress + the stop button across
page reloads. The companion ``GrdEvolveRunner`` polls
``.planning/EVOLVE-STATE.json`` while the underlying session is
live and writes new snapshots through ``upsert_evolve_state``.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_evolve_run_id

logger = logging.getLogger(__name__)


def create_evolve_run(
    *,
    project_id: str,
    session_id: str,
    config: dict,
    total_iterations: Optional[int] = None,
    pick_pct: Optional[int] = None,
) -> str:
    """Insert an active evolve-run row. Returns the ``evol-`` id."""
    with get_connection() as conn:
        eid = _get_unique_evolve_run_id(conn)
        conn.execute(
            """
            INSERT INTO grd_evolve_runs
                (id, project_id, session_id, status, config_json,
                 total_iterations, pick_pct)
            VALUES (?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                eid,
                project_id,
                session_id,
                json.dumps(config, ensure_ascii=False),
                total_iterations,
                pick_pct,
            ),
        )
        conn.commit()
        return eid


def get_evolve_run(run_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM grd_evolve_runs WHERE id = ?", (run_id,)).fetchone()
        return _row_to_dict(row) if row else None


def get_evolve_run_by_session(session_id: str) -> Optional[dict]:
    """The companion runner thread looks up by session_id (it's the
    only handle it owns); the UI looks up by run id.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM grd_evolve_runs WHERE session_id = ?", (session_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None


def list_evolve_runs_for_project(
    project_id: str, *, status: Optional[str] = None, limit: int = 20
) -> List[dict]:
    """Project evolve runs, newest first. Optional status filter
    (``active`` / ``completed`` / ``failed`` / ``stopped``).
    """
    with get_connection() as conn:
        if status:
            cur = conn.execute(
                """
                SELECT * FROM grd_evolve_runs
                WHERE project_id = ? AND status = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (project_id, status, limit),
            )
        else:
            cur = conn.execute(
                """
                SELECT * FROM grd_evolve_runs
                WHERE project_id = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (project_id, limit),
            )
        return [_row_to_dict(row) for row in cur.fetchall()]


def upsert_evolve_state(
    *,
    session_id: str,
    iteration: int,
    state_json: str,
) -> bool:
    """Write the latest EVOLVE-STATE snapshot for an active run.
    Returns True iff a row was updated (False when no matching
    session_id exists — caller should treat as a no-op).
    """
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE grd_evolve_runs
            SET iteration = ?,
                last_state_json = ?,
                last_state_synced_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE session_id = ?
            """,
            (iteration, state_json, session_id),
        )
        conn.commit()
        return cur.rowcount > 0


def finalize_evolve_run(
    *,
    session_id: str,
    status: str,
    error_message: Optional[str] = None,
) -> bool:
    """Mark a run terminal — ``completed`` / ``failed`` / ``stopped``.
    Idempotent: a no-op when the row is already non-active so
    the post-session hook can call this without checking first.
    """
    if status not in {"completed", "failed", "stopped"}:
        raise ValueError(f"invalid terminal status: {status}")
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE grd_evolve_runs
            SET status = ?,
                error_message = ?,
                ended_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE session_id = ? AND status = 'active'
            """,
            (status, error_message, session_id),
        )
        conn.commit()
        return cur.rowcount > 0


def _row_to_dict(row) -> dict:
    cols = (
        row.keys()
        if hasattr(row, "keys")
        else [
            "id",
            "project_id",
            "session_id",
            "status",
            "config_json",
            "iteration",
            "total_iterations",
            "pick_pct",
            "last_state_json",
            "last_state_synced_at",
            "started_at",
            "ended_at",
            "error_message",
            "created_at",
            "updated_at",
        ]
    )
    d = {k: row[k] for k in cols}
    # Parse JSON columns for caller convenience.
    if d.get("config_json"):
        try:
            d["config"] = json.loads(d["config_json"])
        except (json.JSONDecodeError, TypeError):
            d["config"] = None
    if d.get("last_state_json"):
        try:
            d["last_state"] = json.loads(d["last_state_json"])
        except (json.JSONDecodeError, TypeError):
            d["last_state"] = None
    return d
