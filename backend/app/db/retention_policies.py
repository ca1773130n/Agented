"""Retention policies CRUD operations.

PR-R (wave 83): data-retention is a real feature. Persistence ships here;
destructive enforcement of expired rows is intentionally deferred to a
follow-up PR — ``enqueue_cleanup`` in :mod:`app.services.retention_service`
returns a "queued" message but does NOT delete from other tables.

The ``retention_policies`` table is created by
:func:`app.db.schema._monitoring.create_monitoring_tables` on a fresh DB
and by migration v81 on existing databases. :func:`ensure_schema` here is
an idempotent safety-net used by tests and any code path that wants to
guarantee the table exists without booting the full migration pipeline.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .connection import get_connection
from .ids import generate_id

logger = logging.getLogger(__name__)

RETENTION_POLICY_ID_PREFIX = "ret-"
RETENTION_POLICY_ID_LENGTH = 6


def _generate_policy_id() -> str:
    return generate_id(RETENTION_POLICY_ID_PREFIX, RETENTION_POLICY_ID_LENGTH)


def ensure_schema() -> None:
    """Idempotent CREATE TABLE for ``retention_policies``.

    Safety-net for code paths that don't go through the full migration
    pipeline (e.g. ad-hoc test harnesses). The canonical DDL still lives
    in ``app.db.schema._monitoring``.
    """
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS retention_policies (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'global',
                scope_name TEXT NOT NULL DEFAULT 'All',
                retention_days INTEGER NOT NULL DEFAULT 90,
                delete_on_expiry INTEGER NOT NULL DEFAULT 1,
                archive_on_expiry INTEGER NOT NULL DEFAULT 0,
                estimated_size_gb REAL NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT
            )
            """
        )
        conn.commit()


def list_policies() -> list[dict]:
    """Return all retention policies ordered by created_at desc."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM retention_policies ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]


def get_policy(policy_id: str) -> Optional[dict]:
    """Return a single retention policy by id, or None."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM retention_policies WHERE id = ?", (policy_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_policy(
    category: str,
    scope: str = "global",
    scope_name: str = "All",
    retention_days: int = 90,
    delete_on_expiry: bool = True,
    archive_on_expiry: bool = False,
    estimated_size_gb: float = 0.0,
) -> str:
    """Insert a new retention policy. Returns the generated policy ID."""
    policy_id = _generate_policy_id()
    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO retention_policies
                    (id, category, scope, scope_name, retention_days,
                     delete_on_expiry, archive_on_expiry, estimated_size_gb,
                     enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
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
                    created_at,
                ),
            )
            conn.commit()
            return policy_id
        except sqlite3.Error as e:
            logger.error("Database error in create_policy: %s", e)
            raise


def set_enabled(policy_id: str, enabled: bool) -> bool:
    """Toggle the enabled flag for a policy. Returns True if a row was updated."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE retention_policies SET enabled = ? WHERE id = ?",
            (int(enabled), policy_id),
        )
        conn.commit()
        return cursor.rowcount > 0


# Back-compat alias — older callers (admin_tooling import surface) used this name.
update_policy_enabled = set_enabled


def delete_policy(policy_id: str) -> bool:
    """Delete a retention policy. Returns True if a row was deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM retention_policies WHERE id = ?",
            (policy_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def count_policies(enabled_only: bool = False) -> int:
    """Return the total number of retention policies (optionally enabled-only)."""
    with get_connection() as conn:
        if enabled_only:
            cursor = conn.execute("SELECT COUNT(*) FROM retention_policies WHERE enabled = 1")
        else:
            cursor = conn.execute("SELECT COUNT(*) FROM retention_policies")
        return cursor.fetchone()[0]
