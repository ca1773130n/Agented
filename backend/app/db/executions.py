"""Execution-specific query functions with composite filtering.

Provides filtered and counted queries for execution logs, supporting:
- status filter (exact match)
- trigger_id filter (exact match)
- date_from / date_to range filters (ISO 8601 strings)
- q text search over stdout_log and stderr_log (LIKE pattern)

All filters compose with AND logic. All values use parameterized queries.
"""

from typing import List, Optional

from .connection import get_connection


def _build_where_clause(
    status: Optional[str] = None,
    trigger_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
) -> tuple:
    """Build composable WHERE clause and params for execution log queries.

    Returns (where_sql, params) where where_sql starts with ' WHERE 1=1 AND ...'
    """
    conditions = ["1=1"]
    params: list = []

    if status is not None:
        conditions.append("e.status = ?")
        params.append(status)
    if trigger_id is not None:
        conditions.append("e.trigger_id = ?")
        params.append(trigger_id)
    if date_from is not None:
        conditions.append("e.started_at >= ?")
        params.append(date_from)
    if date_to is not None:
        conditions.append("e.started_at <= ?")
        params.append(date_to)
    if q is not None and q.strip():
        conditions.append("(e.stdout_log LIKE ? OR e.stderr_log LIKE ?)")
        pattern = f"%{q}%"
        params.extend([pattern, pattern])

    where_sql = " WHERE " + " AND ".join(conditions)
    return where_sql, params


def get_filtered_executions(
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
    trigger_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
) -> List[dict]:
    """Query execution logs with composable filters and pagination.

    All filters compose with AND logic. Pagination uses SQL LIMIT/OFFSET.
    Returns rows ordered by started_at DESC with trigger_name from JOIN.
    """
    where_sql, params = _build_where_clause(
        status=status, trigger_id=trigger_id,
        date_from=date_from, date_to=date_to, q=q,
    )

    query = f"""
        SELECT e.*, t.name as trigger_name
        FROM execution_logs e
        LEFT JOIN triggers t ON e.trigger_id = t.id
        {where_sql}
        ORDER BY e.started_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    with get_connection() as conn:
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def count_filtered_executions(
    status: Optional[str] = None,
    trigger_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
) -> int:
    """Count execution logs matching composable filters.

    Uses the same WHERE clause as get_filtered_executions for consistency.
    """
    where_sql, params = _build_where_clause(
        status=status, trigger_id=trigger_id,
        date_from=date_from, date_to=date_to, q=q,
    )

    query = f"SELECT COUNT(*) FROM execution_logs e{where_sql}"

    with get_connection() as conn:
        cursor = conn.execute(query, params)
        return cursor.fetchone()[0]
