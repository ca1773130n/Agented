"""RBAC (Role-Based Access Control) database operations.

Manages user_roles table: maps API keys to roles (viewer, operator, editor, admin).
"""

import hmac
import logging
import secrets
import threading
import time
from typing import Optional

from .connection import get_connection
from .ids import _get_unique_role_id

logger = logging.getLogger(__name__)

VALID_ROLES = ("viewer", "operator", "editor", "admin")


def generate_api_key() -> str:
    """Generate a cryptographically secure 64-character hex API key."""
    return secrets.token_hex(32)


# Cache for has_any_keys() — avoids a DB query on every request.
# TTL of 5 seconds: after a key is created, it takes at most 5s for auth to kick in.
_has_any_keys_cache: dict = {}  # {"result": bool, "ts": float}
_has_any_keys_lock = threading.Lock()
_HAS_ANY_KEYS_TTL = 5.0


def has_any_keys() -> bool:
    """Check if any API keys exist in the database. Cached with 5s TTL."""
    now = time.monotonic()
    with _has_any_keys_lock:
        cached = _has_any_keys_cache.get("result")
        ts = _has_any_keys_cache.get("ts", 0.0)
        if cached is not None and (now - ts) < _HAS_ANY_KEYS_TTL:
            return cached
    result = count_user_roles() > 0
    with _has_any_keys_lock:
        _has_any_keys_cache["result"] = result
        _has_any_keys_cache["ts"] = now
    return result


def invalidate_key_cache():
    """Clear the has_any_keys cache (call after creating/deleting keys)."""
    with _has_any_keys_lock:
        _has_any_keys_cache.clear()


def create_user_role(
    api_key: str,
    label: str,
    role: str = "viewer",
    user_id: Optional[str] = None,
) -> Optional[str]:
    """Create a new user role mapping for an API key.

    Args:
        api_key: The API key to associate with the role.
        label: Human-readable label for this key/role assignment.
        role: One of viewer, operator, editor, admin.
        user_id: Owning user's id. When omitted, falls back to the
            ``legacy@local`` user provisioned by migration v102 — this
            preserves single-user behaviour for existing call sites.

    Returns:
        The generated role ID, or None on failure.
    """
    if role not in VALID_ROLES:
        logger.warning("Invalid role %r, must be one of %s", role, VALID_ROLES)
        return None

    try:
        with get_connection() as conn:
            role_id = _get_unique_role_id(conn)
            owner_id = user_id
            if owner_id is None:
                row = conn.execute(
                    "SELECT id FROM users WHERE email = ?", ("legacy@local",)
                ).fetchone()
                owner_id = row[0] if row else None
            conn.execute(
                """INSERT INTO user_roles (id, api_key, label, role, user_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (role_id, api_key, label, role, owner_id),
            )
            conn.commit()
            invalidate_key_cache()
            return role_id
    except Exception as e:
        logger.error("Failed to create user role: %s", e)
        return None


def get_role_for_api_key(api_key: str) -> Optional[str]:
    """Look up the role string for a given API key using constant-time comparison.

    Returns:
        The role string (e.g. 'admin'), or None if not found.
    """
    result = get_role_and_user_for_api_key(api_key)
    return result[0] if result else None


def get_role_and_user_for_api_key(api_key: str) -> Optional[tuple[str, Optional[str]]]:
    """Look up (role, user_id) for an API key using constant-time comparison.

    Returns:
        A (role, user_id) tuple, or None if the key isn't recognized.
        ``user_id`` is None on legacy rows that haven't been backfilled
        (shouldn't happen in practice — migration v102 backfills them).
    """
    with get_connection() as conn:
        rows = conn.execute("SELECT api_key, role, user_id FROM user_roles").fetchall()
        for row_key, role, user_id in rows:
            if hmac.compare_digest(api_key, row_key):
                return (role, user_id)
        return None


def get_user_role(role_id: str) -> Optional[dict]:
    """Get a single user role record by ID.

    Returns:
        Dict with role fields, or None if not found.
    """
    with get_connection() as conn:
        conn.row_factory = _dict_factory
        row = conn.execute("SELECT * FROM user_roles WHERE id = ?", (role_id,)).fetchone()
        conn.row_factory = None
        return row


def list_user_roles() -> list:
    """List all user role records.

    Returns:
        List of dicts with role fields.
    """
    with get_connection() as conn:
        conn.row_factory = _dict_factory
        rows = conn.execute("SELECT * FROM user_roles ORDER BY created_at DESC").fetchall()
        conn.row_factory = None
        return rows


def update_user_role(role_id: str, label: Optional[str] = None, role: Optional[str] = None) -> bool:
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


def rotate_user_role(role_id: str) -> Optional[dict]:
    """Atomically rotate the API key for an existing role record.

    Generates a fresh ``secrets.token_hex(32)`` key and inserts a new
    user_roles row with the same label and role, then deletes the old row.
    Both writes happen inside a single transaction so a partial-rotate
    can never leave the caller holding two valid keys (or none).

    Returns the new role record dict, or ``None`` if ``role_id`` doesn't
    exist.
    """
    with get_connection() as conn:
        conn.row_factory = _dict_factory
        existing = conn.execute(
            "SELECT id, label, role, user_id FROM user_roles WHERE id = ?", (role_id,)
        ).fetchone()
        if not existing:
            conn.row_factory = None
            return None

        new_id = _get_unique_role_id(conn)
        new_key = generate_api_key()
        conn.execute(
            """INSERT INTO user_roles (id, api_key, label, role, user_id)
               VALUES (?, ?, ?, ?, ?)""",
            (new_id, new_key, existing["label"], existing["role"], existing.get("user_id")),
        )
        conn.execute("DELETE FROM user_roles WHERE id = ?", (role_id,))
        conn.commit()

        new_row = conn.execute(
            "SELECT * FROM user_roles WHERE id = ?", (new_id,)
        ).fetchone()
        conn.row_factory = None

    invalidate_key_cache()
    return new_row


def delete_user_role(role_id: str) -> bool:
    """Delete a user role record.

    Returns:
        True if a row was deleted, False otherwise.
    """
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM user_roles WHERE id = ?", (role_id,))
        conn.commit()
        invalidate_key_cache()
        return cursor.rowcount > 0


def count_user_roles() -> int:
    """Return the total number of user roles in the database."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM user_roles").fetchone()
        return row[0] if row else 0


def _dict_factory(cursor, row):
    """Convert sqlite3 row to dict."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
