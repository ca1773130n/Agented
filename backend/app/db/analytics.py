"""Analytics aggregation queries for cost, execution, and effectiveness data.

Provides SQL GROUP BY aggregation functions that power the /admin/analytics/* endpoints.
Follows the pattern established in budgets.py get_usage_aggregated_summary().
"""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)

# strftime format strings for period grouping
_PERIOD_FORMATS = {
    "day": "%Y-%m-%d",
    "week": "%Y-W%W",
    "month": "%Y-%m",
}


def get_cost_analytics(
    entity_type: Optional[str] = None,
    group_by: str = "day",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[dict]:
    """Aggregate token_usage by entity and time period.

    Returns list of dicts with: entity_id, entity_type, period,
    total_cost_usd, total_tokens (input + output).
    Uses strftime() GROUP BY on indexed recorded_at column.
    """
    date_fmt = _PERIOD_FORMATS.get(group_by, _PERIOD_FORMATS["day"])

    query = f"""
        SELECT
            tu.entity_type,
            tu.entity_id,
            strftime('{date_fmt}', tu.recorded_at) as period,
            COALESCE(SUM(tu.total_cost_usd), 0) as total_cost_usd,
            COALESCE(SUM(tu.input_tokens + tu.output_tokens), 0) as total_tokens,
            COALESCE(SUM(tu.input_tokens), 0) as input_tokens,
            COALESCE(SUM(tu.output_tokens), 0) as output_tokens
        FROM token_usage tu
        WHERE 1=1
    """
    params: list = []

    if entity_type:
        query += " AND tu.entity_type = ?"
        params.append(entity_type)
    if start_date:
        query += " AND date(tu.recorded_at) >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date(tu.recorded_at) <= ?"
        params.append(end_date)

    query += f"""
        GROUP BY tu.entity_type, tu.entity_id, strftime('{date_fmt}', tu.recorded_at)
        ORDER BY period DESC, total_cost_usd DESC
    """

    with get_connection() as conn:
        try:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Database error in get_cost_analytics: {e}")
            return []


def get_execution_analytics(
    group_by: str = "day",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    trigger_id: Optional[str] = None,
    team_id: Optional[str] = None,
) -> List[dict]:
    """Aggregate execution_logs by time period and backend_type.

    Returns list of dicts with: period, total_executions, success_count,
    failed_count, cancelled_count, avg_duration_ms, backend_type.
    Uses strftime() on indexed started_at column.
    """
    date_fmt = _PERIOD_FORMATS.get(group_by, _PERIOD_FORMATS["day"])

    query = f"""
        SELECT
            strftime('{date_fmt}', el.started_at) as period,
            el.backend_type,
            COUNT(*) as total_executions,
            COALESCE(SUM(CASE WHEN el.status = 'success' THEN 1 ELSE 0 END), 0) as success_count,
            COALESCE(SUM(CASE WHEN el.status = 'failed' THEN 1 ELSE 0 END), 0) as failed_count,
            COALESCE(SUM(CASE WHEN el.status = 'cancelled' THEN 1 ELSE 0 END), 0) as cancelled_count,
            AVG(
                CASE WHEN el.finished_at IS NOT NULL
                THEN CAST((julianday(el.finished_at) - julianday(el.started_at)) * 86400000 AS INTEGER)
                ELSE NULL END
            ) as avg_duration_ms
        FROM execution_logs el
        WHERE 1=1
    """
    params: list = []

    if trigger_id:
        query += " AND el.trigger_id = ?"
        params.append(trigger_id)
    if team_id:
        query += " AND el.trigger_id IN (SELECT id FROM triggers WHERE team_id = ?)"
        params.append(team_id)
    if start_date:
        query += " AND date(el.started_at) >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date(el.started_at) <= ?"
        params.append(end_date)

    query += f"""
        GROUP BY strftime('{date_fmt}', el.started_at), el.backend_type
        ORDER BY period DESC
    """

    with get_connection() as conn:
        try:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Database error in get_execution_analytics: {e}")
            return []


def get_effectiveness_analytics(
    trigger_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """Aggregate pr_reviews for acceptance rate summary.

    Returns dict with: total_reviews, accepted (approved + fixed),
    ignored (changes_requested with fixes_applied=0), pending,
    acceptance_rate (percentage rounded to 1 decimal).
    """
    query = """
        SELECT
            COUNT(*) as total_reviews,
            COALESCE(SUM(CASE WHEN review_status IN ('approved', 'fixed') THEN 1 ELSE 0 END), 0) as accepted,
            COALESCE(SUM(CASE WHEN review_status = 'changes_requested' AND fixes_applied = 0 THEN 1 ELSE 0 END), 0) as ignored,
            COALESCE(SUM(CASE WHEN review_status = 'pending' THEN 1 ELSE 0 END), 0) as pending
        FROM pr_reviews
        WHERE 1=1
    """
    params: list = []

    if trigger_id:
        query += " AND trigger_id = ?"
        params.append(trigger_id)
    if start_date:
        query += " AND date(created_at) >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date(created_at) <= ?"
        params.append(end_date)

    with get_connection() as conn:
        try:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            if not row:
                return {
                    "total_reviews": 0,
                    "accepted": 0,
                    "ignored": 0,
                    "pending": 0,
                    "acceptance_rate": 0.0,
                }
            result = dict(row)
            total = result["total_reviews"]
            accepted = result["accepted"]
            result["acceptance_rate"] = round((accepted / total) * 100, 1) if total > 0 else 0.0
            return result
        except sqlite3.Error as e:
            logger.error(f"Database error in get_effectiveness_analytics: {e}")
            return {
                "total_reviews": 0,
                "accepted": 0,
                "ignored": 0,
                "pending": 0,
                "acceptance_rate": 0.0,
            }


def get_effectiveness_over_time(
    trigger_id: Optional[str] = None,
    group_by: str = "day",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[dict]:
    """Time-series effectiveness data grouped by period.

    Returns list of dicts with: period, total_reviews, accepted, acceptance_rate.
    Groups by strftime period on created_at.
    """
    date_fmt = _PERIOD_FORMATS.get(group_by, _PERIOD_FORMATS["day"])

    query = f"""
        SELECT
            strftime('{date_fmt}', created_at) as period,
            COUNT(*) as total_reviews,
            COALESCE(SUM(CASE WHEN review_status IN ('approved', 'fixed') THEN 1 ELSE 0 END), 0) as accepted
        FROM pr_reviews
        WHERE 1=1
    """
    params: list = []

    if trigger_id:
        query += " AND trigger_id = ?"
        params.append(trigger_id)
    if start_date:
        query += " AND date(created_at) >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date(created_at) <= ?"
        params.append(end_date)

    query += f"""
        GROUP BY strftime('{date_fmt}', created_at)
        ORDER BY period DESC
    """

    with get_connection() as conn:
        try:
            cursor = conn.execute(query, params)
            results = []
            for row in cursor.fetchall():
                entry = dict(row)
                total = entry["total_reviews"]
                accepted = entry["accepted"]
                entry["acceptance_rate"] = (
                    round((accepted / total) * 100, 1) if total > 0 else 0.0
                )
                results.append(entry)
            return results
        except sqlite3.Error as e:
            logger.error(f"Database error in get_effectiveness_over_time: {e}")
            return []
