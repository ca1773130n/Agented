"""Users table CRUD — multi-user foundation (track B, wave 19).

The table is provisioned by migration v101. No production code consumes
it yet; waves 20-21 wire the FK from user_roles and the per-request
ContextVar.
"""

from __future__ import annotations

import logging
from typing import Optional

import bcrypt

from .connection import get_connection
from .ids import _get_unique_user_id

logger = logging.getLogger(__name__)


def hash_password(plaintext: str) -> str:
    """Return a bcrypt hash for *plaintext* (UTF-8). Default cost 12."""
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plaintext: str, password_hash: Optional[str]) -> bool:
    """Constant-time check; returns False on null/empty hashes."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def set_password(user_id: str, plaintext: str) -> bool:
    """Hash and persist a password for *user_id*. Returns True on success."""
    if not plaintext:
        return False
    digest = hash_password(plaintext)
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (digest, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def authenticate(email: str, plaintext: str) -> Optional[dict]:
    """Look up the user by email and verify their password.

    Returns the user record (without password_hash) on success, None
    otherwise. Same response shape for "user not found" and "wrong
    password" — protects against email enumeration.
    """
    user = get_user_by_email(email)
    if user is None:
        return None
    if not user.get("is_active"):
        return None
    if not verify_password(plaintext, user.get("password_hash")):
        return None
    return {k: v for k, v in user.items() if k != "password_hash"}


def _row_to_dict(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def create_user(email: str, display_name: Optional[str] = None) -> Optional[str]:
    """Create a user. Returns the new user_id or None on conflict."""
    if not email or "@" not in email:
        logger.warning("create_user rejected invalid email %r", email)
        return None
    try:
        with get_connection() as conn:
            user_id = _get_unique_user_id(conn)
            conn.execute(
                """INSERT INTO users (id, email, display_name)
                   VALUES (?, ?, ?)""",
                (user_id, email.strip().lower(), display_name),
            )
            conn.commit()
            return user_id
    except Exception as e:
        logger.warning("create_user failed for %r: %s", email, e)
        return None


def get_user(user_id: str) -> Optional[dict]:
    with get_connection() as conn:
        conn.row_factory = _row_to_dict
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.row_factory = None
        return row


def get_user_by_email(email: str) -> Optional[dict]:
    with get_connection() as conn:
        conn.row_factory = _row_to_dict
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
        conn.row_factory = None
        return row


def list_users(active_only: bool = False) -> list[dict]:
    with get_connection() as conn:
        conn.row_factory = _row_to_dict
        query = "SELECT * FROM users"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query).fetchall()
        conn.row_factory = None
        return rows


def update_user(
    user_id: str,
    display_name: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> bool:
    """Update a user. Returns True if a row was updated."""
    updates = []
    params: list = []
    if display_name is not None:
        updates.append("display_name = ?")
        params.append(display_name)
    if is_active is not None:
        updates.append("is_active = ?")
        params.append(1 if is_active else 0)
    if not updates:
        return False
    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(user_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0


def deactivate_user(user_id: str) -> bool:
    """Soft-delete by setting is_active = 0."""
    return update_user(user_id, is_active=False)


def count_users(active_only: bool = False) -> int:
    with get_connection() as conn:
        query = "SELECT COUNT(*) FROM users"
        if active_only:
            query += " WHERE is_active = 1"
        row = conn.execute(query).fetchone()
        return row[0] if row else 0
