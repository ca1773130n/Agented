"""Persistent history of observability / memory queries.

Every memory query (research, doctor, lint, graph query, sessions, activity
summary, decisions, ...) runs as a background job whose lifecycle + result are
persisted here, so the operator can leave the page while it runs and read the
result (and every past result) later. Backs the in-memory ``_op_jobs`` fast-read
cache, which is lost on restart.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def create_job(
    job_id: str,
    kind: str,
    *,
    label: Optional[str] = None,
    params: Optional[dict] = None,
    project_id: Optional[str] = None,
) -> None:
    """Insert a new running job row."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO memory_query_jobs
                (id, kind, label, params_json, project_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'running', ?)
            """,
            (
                job_id,
                kind,
                label,
                json.dumps(params) if params is not None else None,
                project_id,
                _now(),
            ),
        )
        conn.commit()


def finish_job(
    job_id: str,
    *,
    status: str,
    result: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    """Mark a job completed/failed with its result. ``status`` in {completed, failed}."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE memory_query_jobs
               SET status = ?, result_json = ?, error = ?, finished_at = ?
             WHERE id = ?
            """,
            (
                status,
                json.dumps(result) if result is not None else None,
                (error or None) if error else None,
                _now(),
                job_id,
            ),
        )
        conn.commit()


def _row_to_job(row: Any, *, include_result: bool) -> dict:
    d = dict(row)
    job = {
        "job_id": d["id"],
        "kind": d["kind"],
        "label": d.get("label"),
        "project_id": d.get("project_id"),
        "status": d["status"],
        "created_at": d["created_at"],
        "finished_at": d.get("finished_at"),
        "error": d.get("error"),
    }
    try:
        job["params"] = json.loads(d["params_json"]) if d.get("params_json") else None
    except (ValueError, TypeError):
        job["params"] = None
    if include_result:
        try:
            job["result"] = json.loads(d["result_json"]) if d.get("result_json") else None
        except (ValueError, TypeError):
            job["result"] = None
    return job


def get_job(job_id: str) -> Optional[dict]:
    """One job WITH its full result (for polling / reading a past query)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM memory_query_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    return _row_to_job(row, include_result=True) if row else None


def list_jobs(*, kind: Optional[str] = None, limit: int = 50) -> list[dict]:
    """Recent jobs (newest first), WITHOUT the (potentially large) result blob —
    the history list. Fetch one job via :func:`get_job` to read its result."""
    limit = max(1, min(int(limit), 500))
    with get_connection() as conn:
        if kind:
            rows = conn.execute(
                "SELECT * FROM memory_query_jobs WHERE kind = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memory_query_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_to_job(r, include_result=False) for r in rows]
