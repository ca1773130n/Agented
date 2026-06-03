"""CRUD for the team_executions table — the durable mirror of
``TeamExecutionTracker``'s in-memory state.

Lives in ``app.db`` (not ``app.services``) so it can be imported from
both the team-execution service and the session-fetcher map without
pulling in subprocess / threading machinery.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def resolve_project_id_for_team(team_id: str) -> Optional[str]:
    """Pick a project for the team via the ``project_teams`` junction.

    Teams can technically belong to multiple projects; we return the
    first binding (deterministic insertion order). Returns ``None``
    when the team isn't bound to any project — the caller can backfill
    later from a component execution's project_paths row.
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT project_id FROM project_teams WHERE team_id = ? ORDER BY id ASC LIMIT 1",
                (team_id,),
            ).fetchone()
        return row["project_id"] if row else None
    except Exception:
        logger.warning(
            "team_executions: project_id resolution failed for team %s",
            team_id,
            exc_info=True,
        )
        return None


def insert_team_execution(
    team_exec_id: str,
    team_id: str,
    topology: str,
    trigger_type: str,
    *,
    project_id: Optional[str] = None,
    message: Optional[str] = None,
) -> None:
    """Insert a row for a freshly-registered team execution.

    Idempotent: a second insert with the same id is a no-op (relies on
    ``INSERT OR IGNORE``). The caller is expected to follow up with
    ``update_team_execution_status`` on terminal transitions.
    """
    with get_connection() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO team_executions
                   (id, team_id, topology, trigger_type, project_id,
                    message, status)
               VALUES (?, ?, ?, ?, ?, ?, 'running')""",
            (team_exec_id, team_id, topology, trigger_type, project_id, message),
        )
        conn.commit()


def update_team_execution_status(
    team_exec_id: str,
    status: str,
    *,
    error: Optional[str] = None,
    execution_ids: Optional[list[str]] = None,
    project_id: Optional[str] = None,
) -> None:
    """Update a team execution's terminal status.

    Only sets ``completed_at`` for terminal statuses (anything other
    than ``'running'``). ``project_id`` is only written when not
    already set, so a later backfill from a component execution
    doesn't clobber a value we resolved up-front.
    """
    sets = ["status = ?"]
    params: list = [status]
    if error is not None:
        sets.append("error = ?")
        params.append(error)
    if execution_ids is not None:
        sets.append("execution_ids = ?")
        params.append(json.dumps(execution_ids))
    if project_id is not None:
        # COALESCE: keep existing project_id if already set.
        sets.append("project_id = COALESCE(project_id, ?)")
        params.append(project_id)
    if status != "running":
        sets.append("completed_at = CURRENT_TIMESTAMP")
    params.append(team_exec_id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE team_executions SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        conn.commit()


def get_team_execution(team_exec_id: str) -> Optional[dict]:
    """Return the team execution row (or ``None``). ``execution_ids``
    is decoded from JSON for convenience."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM team_executions WHERE id = ?",
            (team_exec_id,),
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    if out.get("execution_ids"):
        try:
            out["execution_ids"] = json.loads(out["execution_ids"])
        except (TypeError, ValueError):
            out["execution_ids"] = []
    else:
        out["execution_ids"] = []
    return out


def count_running_for_team(team_id: str) -> int:
    """Number of team executions currently 'running' for ``team_id``.

    Lets the scheduler overlap guard (06 L2) cover team-mode triggers, whose
    work surfaces here rather than as a 'running' execution_logs row for the
    trigger_id. Best-effort: returns 0 on any query error."""
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM team_executions WHERE team_id = ? AND status = 'running'",
                (team_id,),
            ).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def backfill_project_id_from_components(team_exec_id: str) -> Optional[str]:
    """If the team_executions row has no project_id but at least one
    component execution does, copy it onto the team row. Returns the
    resolved project_id (or ``None`` if no component had one)."""
    row = get_team_execution(team_exec_id)
    if not row:
        return None
    if row.get("project_id"):
        return row["project_id"]
    execution_ids = row.get("execution_ids") or []
    if not execution_ids:
        return None
    placeholders = ",".join("?" * len(execution_ids))
    with get_connection() as conn:
        comp = conn.execute(
            f"""SELECT pp.project_id
                FROM execution_logs e
                JOIN project_paths pp ON pp.trigger_id = e.trigger_id
                WHERE e.execution_id IN ({placeholders})
                  AND pp.project_id IS NOT NULL
                ORDER BY pp.id ASC LIMIT 1""",
            execution_ids,
        ).fetchone()
    if not comp:
        return None
    resolved = comp["project_id"]
    with get_connection() as conn:
        conn.execute(
            "UPDATE team_executions SET project_id = ? WHERE id = ? AND project_id IS NULL",
            (resolved, team_exec_id),
        )
        conn.commit()
    return resolved
