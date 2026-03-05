"""Analytics aggregation queries for cost, execution, and effectiveness analytics.

Provides SQL GROUP BY aggregation functions using strftime() on indexed columns
(recorded_at, started_at, created_at) for time-series analytics data.
"""

import logging
import sqlite3
from typing import Dict, List, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)

# strftime format strings for period grouping
PERIOD_FORMATS = {
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

    Groups by strftime period on recorded_at (indexed via idx_token_usage_recorded).
    Returns list of dicts with: entity_id, period, total_cost_usd, total_tokens.
    """
    date_fmt = PERIOD_FORMATS.get(group_by, PERIOD_FORMATS["day"])

    query = f"""
        SELECT
            entity_id,
            strftime('{date_fmt}', recorded_at) as period,
            COALESCE(SUM(total_cost_usd), 0) as total_cost_usd,
            COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens
        FROM token_usage
        WHERE 1=1
    """
    params: list = []

    if entity_type:
        query += " AND entity_type = ?"
        params.append(entity_type)
    if start_date:
        query += " AND date(recorded_at) >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date(recorded_at) <= ?"
        params.append(end_date)

    query += f" GROUP BY entity_id, strftime('{date_fmt}', recorded_at)"
    query += " ORDER BY period DESC, total_cost_usd DESC"

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
    """Aggregate execution_logs by time period.

    Groups by strftime period on started_at (indexed via idx_execution_logs_started_at).
    Returns list of dicts with: period, total_executions, success_count, failed_count,
    cancelled_count, avg_duration_ms, backend_type.
    """
    date_fmt = PERIOD_FORMATS.get(group_by, PERIOD_FORMATS["day"])

    query = f"""
        SELECT
            strftime('{date_fmt}', started_at) as period,
            backend_type,
            COUNT(*) as total_executions,
            COALESCE(SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END), 0) as success_count,
            COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) as failed_count,
            COALESCE(SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END), 0) as cancelled_count,
            COALESCE(
                AVG(
                    CASE WHEN finished_at IS NOT NULL AND started_at IS NOT NULL
                    THEN CAST((julianday(finished_at) - julianday(started_at)) * 86400000 AS INTEGER)
                    END
                ), 0
            ) as avg_duration_ms
        FROM execution_logs
        WHERE 1=1
    """
    params: list = []

    if trigger_id:
        query += " AND trigger_id = ?"
        params.append(trigger_id)
    if start_date:
        query += " AND date(started_at) >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date(started_at) <= ?"
        params.append(end_date)

    query += f" GROUP BY strftime('{date_fmt}', started_at), backend_type"
    query += " ORDER BY period DESC"

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
) -> Dict:
    """Aggregate pr_reviews for effectiveness summary.

    Returns dict with: total_reviews, accepted (approved + fixed),
    ignored (changes_requested with fixes_applied=0), pending, acceptance_rate.
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
            if row:
                result = dict(row)
                total = result["total_reviews"]
                accepted = result["accepted"]
                result["acceptance_rate"] = (
                    round((accepted / total) * 100, 1) if total > 0 else 0.0
                )
                return result
            return {
                "total_reviews": 0,
                "accepted": 0,
                "ignored": 0,
                "pending": 0,
                "acceptance_rate": 0.0,
            }
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
    """Time-series effectiveness aggregation grouped by period on created_at.

    Returns list of dicts with: period, total_reviews, accepted, acceptance_rate.
    """
    date_fmt = PERIOD_FORMATS.get(group_by, PERIOD_FORMATS["day"])

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

    query += f" GROUP BY strftime('{date_fmt}', created_at)"
    query += " ORDER BY period DESC"

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
