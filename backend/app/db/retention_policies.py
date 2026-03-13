"""Retention policies CRUD operations."""

import logging
import sqlite3

from .connection import get_connection
from .ids import generate_id

logger = logging.getLogger(__name__)

RETENTION_POLICY_ID_PREFIX = "rp-"
RETENTION_POLICY_ID_LENGTH = 6


def _generate_policy_id() -> str:
    return generate_id(RETENTION_POLICY_ID_PREFIX, RETENTION_POLICY_ID_LENGTH)


def list_policies() -> list[dict]:
    """Return all retention policies ordered by created_at desc."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM retention_policies ORDER BY created_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]


def create_policy(
    category: str,
    scope: str = "global",
    scope_name: str = "All Teams",
    retention_days: int = 90,
    delete_on_expiry: bool = True,
    archive_on_expiry: bool = False,
    estimated_size_gb: float = 0.0,
) -> str:
    """Insert a new retention policy. Returns the generated policy ID."""
    policy_id = _generate_policy_id()
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO retention_policies
                    (id, category, scope, scope_name, retention_days,
                     delete_on_expiry, archive_on_expiry, estimated_size_gb, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    policy_id,
                    category,
                    scope,
                    scope_name,
                    retention_days,
                    int(delete_on_expiry),
                    int(archive_on_expiry),
                    estimated_size_gb,
                ),
            )
            conn.commit()
            return policy_id
        except sqlite3.Error as e:
            logger.error("Database error in create_policy: %s", e)
            raise


def update_policy_enabled(policy_id: str, enabled: bool) -> bool:
    """Toggle the enabled flag for a policy. Returns True if updated."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE retention_policies SET enabled = ? WHERE id = ?",
            (int(enabled), policy_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_policy(policy_id: str) -> bool:
    """Delete a retention policy. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM retention_policies WHERE id = ?",
            (policy_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
