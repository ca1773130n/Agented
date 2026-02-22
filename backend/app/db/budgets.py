"""Token usage, budget limits, and execution token data CRUD operations.

Separated from monitoring.py to stay within the 500-line module size constraint.
This module was added per research recommendation and is not in the original
phase description's list of 13 domain modules.
"""

import datetime
import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


# =============================================================================
# Token Usage CRUD operations
# =============================================================================


def create_token_usage_record(
    execution_id: str,
    entity_type: str,
    entity_id: str,
    backend_type: str,
    account_id: Optional[int] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    total_cost_usd: float = 0.0,
    num_turns: int = 0,
    duration_api_ms: int = 0,
    session_id: Optional[str] = None,
    recorded_at: Optional[str] = None,
) -> Optional[int]:
    """Insert a token usage record. Returns the record ID on success.

    If recorded_at is provided (ISO timestamp), it is used as the record timestamp.
    Otherwise defaults to CURRENT_TIMESTAMP (now).
    """
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO token_usage (
                    execution_id, entity_type, entity_id, backend_type, account_id,
                    input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
                    total_cost_usd, num_turns, duration_api_ms, session_id, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
            """,
                (
                    execution_id,
                    entity_type,
                    entity_id,
                    backend_type,
                    account_id,
                    input_tokens,
                    output_tokens,
                    cache_read_tokens,
                    cache_creation_tokens,
                    total_cost_usd,
                    num_turns,
                    duration_api_ms,
                    session_id,
                    recorded_at,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Database error in create_token_usage_record: {e}")
            return None


def get_token_usage_for_execution(execution_id: str) -> Optional[dict]:
    """Get token usage record for a specific execution."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM token_usage WHERE execution_id = ?", (execution_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_current_period_spend(entity_type: str, entity_id: str, period: str) -> float:
    """Get total spend for an entity within the current period.

    Period calculation:
    - daily: from today midnight
    - weekly: from Monday midnight
    - monthly: from 1st of month midnight

    Joins with execution_logs.started_at to attribute costs to when execution started.
    """
    now = datetime.datetime.now()

    if period == "daily":
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "weekly":
        # Monday of this week
        days_since_monday = now.weekday()
        period_start = (now - datetime.timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:  # monthly
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    period_start_str = period_start.isoformat()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT COALESCE(SUM(tu.total_cost_usd), 0) as total_spend
            FROM token_usage tu
            JOIN execution_logs el ON tu.execution_id = el.execution_id
            WHERE tu.entity_type = ? AND tu.entity_id = ?
              AND el.started_at >= ?
        """,
            (entity_type, entity_id, period_start_str),
        )
        row = cursor.fetchone()
        return float(row["total_spend"]) if row else 0.0


def get_window_token_usage(since: str) -> int:
    """Get total tokens (input + output) recorded since the given ISO timestamp.

    Returns the sum of (input_tokens + output_tokens) for all records
    where recorded_at >= since.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens
            FROM token_usage
            WHERE recorded_at >= ?
        """,
            (since,),
        )
        row = cursor.fetchone()
        return int(row["total_tokens"]) if row else 0


def get_token_usage_summary(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    period: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[dict]:
    """Get token usage records with optional filtering.

    Returns list of usage record dicts.
    """
    query = "SELECT * FROM token_usage WHERE 1=1"
    params: list = []

    if entity_type:
        query += " AND entity_type = ?"
        params.append(entity_type)
    if entity_id:
        query += " AND entity_id = ?"
        params.append(entity_id)
    if start_date:
        query += " AND date(recorded_at) >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date(recorded_at) <= ?"
        params.append(end_date)

    query += " ORDER BY recorded_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_connection() as conn:
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_token_usage_count(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> int:
    """Get count of token usage records with optional filtering."""
    query = "SELECT COUNT(*) as cnt FROM token_usage WHERE 1=1"
    params: list = []

    if entity_type:
        query += " AND entity_type = ?"
        params.append(entity_type)
    if entity_id:
        query += " AND entity_id = ?"
        params.append(entity_id)
    if start_date:
        query += " AND date(recorded_at) >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date(recorded_at) <= ?"
        params.append(end_date)

    with get_connection() as conn:
        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        return int(row["cnt"]) if row else 0


def get_token_usage_total_cost(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> float:
    """Get total cost of token usage with optional filtering."""
    query = "SELECT COALESCE(SUM(total_cost_usd), 0) as total FROM token_usage WHERE 1=1"
    params: list = []

    if entity_type:
        query += " AND entity_type = ?"
        params.append(entity_type)
    if entity_id:
        query += " AND entity_id = ?"
        params.append(entity_id)
    if start_date:
        query += " AND date(recorded_at) >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date(recorded_at) <= ?"
        params.append(end_date)

    with get_connection() as conn:
        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        return float(row["total"]) if row else 0.0


def get_usage_aggregated_summary(
    group_by: str = "day",
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[dict]:
    """Get aggregated usage summary grouped by time period.

    group_by: 'day', 'week', or 'month'.
    Returns list of dicts with period_start, total_cost_usd, total_input_tokens,
    total_output_tokens, execution_count.
    """
    if group_by == "day":
        date_fmt = "%Y-%m-%d"
    elif group_by == "week":
        date_fmt = "%Y-W%W"
    else:  # month
        date_fmt = "%Y-%m"

    query = f"""
        SELECT
            strftime('{date_fmt}', tu.recorded_at) as period_start,
            COALESCE(SUM(tu.total_cost_usd), 0) as total_cost_usd,
            COALESCE(SUM(tu.input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(tu.output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(tu.cache_read_tokens), 0) as total_cache_read_tokens,
            COALESCE(SUM(tu.cache_creation_tokens), 0) as total_cache_creation_tokens,
            COUNT(*) as execution_count,
            COUNT(DISTINCT tu.session_id) as session_count,
            COALESCE(SUM(tu.num_turns), 0) as total_turns
        FROM token_usage tu
        WHERE 1=1
    """
    params: list = []

    if entity_type:
        query += " AND tu.entity_type = ?"
        params.append(entity_type)
    if entity_id:
        query += " AND tu.entity_id = ?"
        params.append(entity_id)
    if start_date:
        query += " AND date(tu.recorded_at) >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date(tu.recorded_at) <= ?"
        params.append(end_date)

    query += f" GROUP BY strftime('{date_fmt}', tu.recorded_at) ORDER BY period_start DESC"

    with get_connection() as conn:
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_usage_by_entity(
    entity_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[dict]:
    """Get usage breakdown by entity.

    Returns list of dicts with entity_type, entity_id, total_cost_usd, execution_count.
    """
    query = """
        SELECT
            tu.entity_type,
            tu.entity_id,
            COALESCE(SUM(tu.total_cost_usd), 0) as total_cost_usd,
            COALESCE(SUM(tu.input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(tu.output_tokens), 0) as total_output_tokens,
            COUNT(*) as execution_count
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

    query += " GROUP BY tu.entity_type, tu.entity_id ORDER BY total_cost_usd DESC"

    with get_connection() as conn:
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# Budget Limit CRUD operations
# =============================================================================


def get_budget_limit(entity_type: str, entity_id: str) -> Optional[dict]:
    """Get budget limit for a specific entity."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM budget_limits WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def set_budget_limit(
    entity_type: str,
    entity_id: str,
    period: str = "monthly",
    soft_limit_usd: Optional[float] = None,
    hard_limit_usd: Optional[float] = None,
) -> bool:
    """Set or update a budget limit (upsert). Returns True on success.

    Validates: at least one limit must be set. If both set, hard >= soft.
    """
    if soft_limit_usd is None and hard_limit_usd is None:
        return False
    if soft_limit_usd is not None and hard_limit_usd is not None:
        if hard_limit_usd < soft_limit_usd:
            return False

    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO budget_limits (entity_type, entity_id, period, soft_limit_usd, hard_limit_usd)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                    period = excluded.period,
                    soft_limit_usd = excluded.soft_limit_usd,
                    hard_limit_usd = excluded.hard_limit_usd,
                    updated_at = CURRENT_TIMESTAMP
            """,
                (entity_type, entity_id, period, soft_limit_usd, hard_limit_usd),
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Database error in set_budget_limit: {e}")
            return False


def delete_budget_limit(entity_type: str, entity_id: str) -> bool:
    """Delete a budget limit. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM budget_limits WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_all_budget_limits() -> List[dict]:
    """Get all budget limits."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM budget_limits ORDER BY entity_type, entity_id")
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# Execution Token Data operations
# =============================================================================


def update_execution_token_data(
    execution_id: str,
    input_tokens: int,
    output_tokens: int,
    total_cost_usd: float,
) -> bool:
    """Update execution_logs to cache token data for quick access."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE execution_logs
            SET input_tokens = ?, output_tokens = ?, total_cost_usd = ?
            WHERE execution_id = ?
        """,
            (input_tokens, output_tokens, total_cost_usd, execution_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_average_output_tokens(entity_type: str, entity_id: str) -> Optional[float]:
    """Get average output tokens for an entity from historical data."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT AVG(output_tokens) as avg_output
            FROM token_usage
            WHERE entity_type = ? AND entity_id = ? AND output_tokens > 0
        """,
            (entity_type, entity_id),
        )
        row = cursor.fetchone()
        if row and row["avg_output"] is not None:
            return float(row["avg_output"])
        return None
