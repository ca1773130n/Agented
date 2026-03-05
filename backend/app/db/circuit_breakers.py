"""Circuit breaker state persistence CRUD operations.

Provides create/read/update for the circuit_breakers table used by
CircuitBreakerService to persist per-backend circuit breaker state
across server restarts.
"""

import logging
from typing import List, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def get_breaker_state(backend_type: str) -> Optional[dict]:
    """Get the persisted circuit breaker state for a backend type.

    Returns dict with state, fail_count, success_count, last_failure_time, updated_at
    or None if no record exists.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM circuit_breakers WHERE backend_type = ?",
            (backend_type,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def upsert_breaker_state(
    backend_type: str,
    state: str,
    fail_count: int,
    success_count: int,
    last_failure_time: Optional[float] = None,
) -> bool:
    """Insert or update circuit breaker state for a backend type.

    Returns True if the row was inserted/updated.
    """
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO circuit_breakers
                (backend_type, state, fail_count, success_count, last_failure_time, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(backend_type) DO UPDATE SET
                state = excluded.state,
                fail_count = excluded.fail_count,
                success_count = excluded.success_count,
                last_failure_time = excluded.last_failure_time,
                updated_at = datetime('now')
            """,
            (backend_type, state, fail_count, success_count, last_failure_time),
        )
        conn.commit()
        return True


def get_all_breaker_states() -> List[dict]:
    """Get all persisted circuit breaker states.

    Returns list of dicts with backend_type, state, fail_count, etc.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM circuit_breakers ORDER BY backend_type"
        )
        return [dict(row) for row in cursor.fetchall()]


def reset_all_breakers() -> int:
    """Reset all circuit breakers to closed state with zero counts.

    Used on server startup to clear stale state.
    Returns count of rows updated.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE circuit_breakers
            SET state = 'closed', fail_count = 0, success_count = 0, updated_at = datetime('now')
            """
        )
        conn.commit()
        return cursor.rowcount
