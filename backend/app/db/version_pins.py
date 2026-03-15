"""Version pin CRUD operations."""

import logging
from typing import Optional

from .connection import get_connection
from .ids import generate_id

logger = logging.getLogger(__name__)


def _generate_vpin_id() -> str:
    return generate_id("vpin-", 6)


def get_all_version_pins() -> list[dict]:
    """Return all version pin records."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM version_pins ORDER BY component_name ASC")
        return [dict(row) for row in cursor.fetchall()]


def get_version_pin(pin_id: str) -> Optional[dict]:
    """Return a single version pin by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM version_pins WHERE id = ?", (pin_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_pin_status(
    pin_id: str,
    pinned_version: str,
    status: str,
    pinned_at: str,
) -> bool:
    """Update the pinned version, status, and pinned_at timestamp.

    Returns True if the row was updated.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """UPDATE version_pins
               SET pinned_version = ?, status = ?, pinned_at = ?
               WHERE id = ?""",
            (pinned_version, status, pinned_at, pin_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def set_pin_unpinned(pin_id: str) -> bool:
    """Set a pin's status to 'unpinned' and clear the pinned fields.

    Returns True if the row was updated.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """UPDATE version_pins
               SET status = 'unpinned', pinned_version = NULL, pinned_at = NULL
               WHERE id = ?""",
            (pin_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_version_history(component_id: str) -> list[dict]:
    """Return version history entries for a component, newest first."""
    with get_connection() as conn:
        cursor = conn.execute(
            """SELECT * FROM component_version_history
               WHERE component_id = ?
               ORDER BY released_at DESC""",
            (component_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
