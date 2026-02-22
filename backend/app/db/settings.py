"""Settings CRUD operations."""

import logging
from typing import Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def get_setting(key: str) -> Optional[str]:
    """Get a setting value by key."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else None


def set_setting(key: str, value: str) -> bool:
    """Set a setting value. Creates or updates the setting."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_setting(key: str) -> bool:
    """Delete a setting."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        conn.commit()
        return cursor.rowcount > 0


def get_all_settings() -> dict:
    """Get all settings as a dictionary."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in cursor.fetchall()}
