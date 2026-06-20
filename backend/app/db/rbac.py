"""RBAC (Role-Based Access Control) database operations.

Manages user_roles table: maps API keys to roles (viewer, operator, editor, admin).
"""

import hmac
import logging
import os
import secrets
import threading
import time
from typing import Optional

from . import sessions as _sessions
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


def user_bound_admin_exists() -> bool:
    """True if any real user (non-empty user_id) holds the admin role.

    The bootstrap API-key admin seeded with an empty/NULL user_id does NOT
    count: it can't be resolved from a session login, so a console operator
    authenticating via the SPA would still be locked out of /admin/* despite
    that row existing. "Is the install bootstrapped for human admins?" must
    therefore ignore orphan API-key admin rows.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM user_roles "
            "WHERE role = 'admin' AND user_id IS NOT NULL AND user_id != '' "
            "LIMIT 1"
        ).fetchone()
    return row is not None


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def registration_open() -> bool:
    """Whether open self-registration (`POST /api/auth/signup`) is permitted.

    Open by default (preserving existing single-operator onboarding). Set
    ``AGENTED_DISABLE_SIGNUP=1`` to close it — recommended once the operator has
    registered, and required if the instance is reachable from an untrusted
    network (the first signup becomes admin, so open signup on an exposed,
    not-yet-bootstrapped instance is an escalation vector).
    """
    return not _env_flag("AGENTED_DISABLE_SIGNUP")


def ensure_user_admin(user_id: str) -> bool:
    """Grant ``user_id`` the admin role iff no user currently holds admin
    (first-operator bootstrap). Returns True when a grant was made.

    The check + insert run in a single connection so concurrent first-time
    signups converge on a single admin rather than silently multiplying.
    """
    if not user_id:
        return False
    with get_connection() as conn:
        role_id = _get_unique_role_id(conn)
        # Single atomic statement: the row is inserted only when no user-bound
        # admin exists, so two concurrent first-signups can't both win the grant
        # (SQLite serializes the write; the loser's NOT EXISTS sees the winner's
        # committed row). rowcount tells us whether we were the one to grant it.
        cur = conn.execute(
            "INSERT INTO user_roles (id, api_key, label, role, user_id) "
            "SELECT ?, ?, ?, 'admin', ? "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM user_roles "
            "  WHERE role = 'admin' AND user_id IS NOT NULL AND user_id != ''"
            ")",
            (role_id, generate_api_key(), "bootstrap admin", user_id),
        )
        conn.commit()
        granted = cur.rowcount > 0
    if granted:
        invalidate_key_cache()
        logger.info("Bootstrap: granted admin to first operator user_id=%s", user_id)
    return granted


def backfill_bootstrap_admin() -> Optional[str]:
    """Self-heal a locked-out install: if no user holds admin, promote the
    earliest real login account (a user with a password) to admin. Skips
    synthetic/passwordless accounts like the migration's ``legacy@local``.

    Returns the promoted user_id, or None if no action was taken (an admin
    user already exists, or there is no real login account to promote).
    Idempotent — safe to call on every startup.
    """
    with get_connection() as conn:
        admin = conn.execute(
            "SELECT 1 FROM user_roles "
            "WHERE role = 'admin' AND user_id IS NOT NULL AND user_id != '' "
            "LIMIT 1"
        ).fetchone()
        if admin:
            return None
        row = conn.execute(
            "SELECT id FROM users "
            "WHERE password_hash IS NOT NULL AND length(password_hash) > 0 "
            "  AND is_active = 1 "
            "ORDER BY created_at ASC, id ASC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    user_id = row[0]
    if ensure_user_admin(user_id):
        logger.warning(
            "Bootstrap recovery: no user held admin; promoted earliest login "
            "account user_id=%s to admin. Review in RBAC settings if unexpected.",
            user_id,
        )
        return user_id
    return None


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


_ROLE_RANK = {"viewer": 0, "operator": 1, "editor": 2, "admin": 3}


def get_highest_role_for_user(user_id: str) -> Optional[str]:
    """Return the strongest role the user holds across any of their api_keys.

    If the user owns multiple user_roles rows with different roles
    (e.g. admin + editor), the strongest one wins under the standard
    ordering: admin > editor > operator > viewer. Returns None when
    the user has no role rows.
    """
    if not user_id:
        return None
    with get_connection() as conn:
        rows = conn.execute("SELECT role FROM user_roles WHERE user_id = ?", (user_id,)).fetchall()
    if not rows:
        return None
    best = max(rows, key=lambda r: _ROLE_RANK.get(r[0], -1))
    return best[0] if _ROLE_RANK.get(best[0], -1) >= 0 else None


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
        changed = cursor.rowcount > 0
        # v0.5.12: invalidate the user's bearer sessions on role change.
        if changed:
            row = conn.execute("SELECT user_id FROM user_roles WHERE id = ?", (role_id,)).fetchone()
            user_id = row[0] if row else None
        else:
            user_id = None
    if user_id:
        _sessions.revoke_user_sessions(user_id, reason="role_change")
    return changed


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

        new_row = conn.execute("SELECT * FROM user_roles WHERE id = ?", (new_id,)).fetchone()
        conn.row_factory = None

    invalidate_key_cache()
    if new_row and new_row.get("user_id"):
        _sessions.revoke_user_sessions(new_row["user_id"], reason="key_rotation")
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
