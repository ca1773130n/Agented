"""RBAC (Role-Based Access Control) database operations.

Manages user_roles table: maps API keys to roles (viewer, operator, editor, admin).
"""

import logging
from typing import Optional

from .connection import get_connection
from .ids import _get_unique_role_id

logger = logging.getLogger(__name__)

VALID_ROLES = ("viewer", "operator", "editor", "admin")


def create_user_role(api_key: str, label: str, role: str = "viewer") -> Optional[str]:
    """Create a new user role mapping for an API key.

    Args:
        api_key: The API key to associate with the role.
        label: Human-readable label for this key/role assignment.
        role: One of viewer, operator, editor, admin.

    Returns:
        The generated role ID, or None on failure.
    """
    if role not in VALID_ROLES:
        logger.warning("Invalid role %r, must be one of %s", role, VALID_ROLES)
        return None

    try:
        with get_connection() as conn:
            role_id = _get_unique_role_id(conn)
            conn.execute(
                """INSERT INTO user_roles (id, api_key, label, role)
                   VALUES (?, ?, ?, ?)""",
                (role_id, api_key, label, role),
            )
            conn.commit()
            return role_id
    except Exception as e:
        logger.error("Failed to create user role: %s", e)
        return None


def get_role_for_api_key(api_key: str) -> Optional[str]:
    """Look up the role string for a given API key.

    Returns:
        The role string (e.g. 'admin'), or None if not found.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT role FROM user_roles WHERE api_key = ?", (api_key,)
        ).fetchone()
        return row[0] if row else None


def get_user_role(role_id: str) -> Optional[dict]:
    """Get a single user role record by ID.

    Returns:
        Dict with role fields, or None if not found.
    """
    with get_connection() as conn:
        conn.row_factory = _dict_factory
        row = conn.execute(
            "SELECT * FROM user_roles WHERE id = ?", (role_id,)
        ).fetchone()
        conn.row_factory = None
        return row


def list_user_roles() -> list:
    """List all user role records.

    Returns:
        List of dicts with role fields.
    """
    with get_connection() as conn:
        conn.row_factory = _dict_factory
        rows = conn.execute(
            "SELECT * FROM user_roles ORDER BY created_at DESC"
        ).fetchall()
        conn.row_factory = None
        return rows


def update_user_role(
    role_id: str, label: Optional[str] = None, role: Optional[str] = None
) -> bool:
    """Update a user role record.

    Args:
        role_id: The role record ID to update.
        label: New label (optional).
        role: New role value (optional).

    Returns:
        True if a row was updated, False otherwise.
    """
    if role is not None and role not in VALID_ROLES:
        logger.warning("Invalid role %r, must be one of %s", role, VALID_ROLES)
        return False

    updates = []
    params = []
    if label is not None:
        updates.append("label = ?")
        params.append(label)
    if role is not None:
        updates.append("role = ?")
        params.append(role)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(role_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE user_roles SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_user_role(role_id: str) -> bool:
    """Delete a user role record.

    Returns:
        True if a row was deleted, False otherwise.
    """
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM user_roles WHERE id = ?", (role_id,))
        conn.commit()
        return cursor.rowcount > 0


def count_user_roles() -> int:
    """Return the total number of user roles in the database."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM user_roles").fetchone()
        return row[0] if row else 0


def _dict_factory(cursor, row):
    """Convert sqlite3 row to dict."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
