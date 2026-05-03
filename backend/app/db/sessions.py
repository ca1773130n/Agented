"""Session token storage (track B, wave 32).

Tokens are 256-bit URL-safe random strings. Verification is constant-time
(hmac.compare_digest) and rotates ``last_used_at`` so a future grooming
job can prune idle sessions.

v0.5.12: idle-expiry, token rotation with grace window, revoke-by-user,
soft-delete revocation, and audit logging via session_events.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import secrets
from typing import Optional

from . import session_events
from .connection import get_connection
from .ids import _get_unique_session_id

logger = logging.getLogger(__name__)

DEFAULT_LIFETIME = dt.timedelta(days=14)
DEFAULT_IDLE_LIFETIME = dt.timedelta(minutes=30)
ROTATION_GRACE_WINDOW = dt.timedelta(seconds=5)


def _row_to_dict(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def _generate_token() -> str:
    """256-bit URL-safe random token (43 chars)."""
    return secrets.token_urlsafe(32)


def _hash_token(token: str) -> str:
    """SHA-256 hash of a token, hex-encoded, for audit metadata only."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def create_session(user_id: str, lifetime: dt.timedelta = DEFAULT_LIFETIME) -> Optional[dict]:
    """Issue a fresh session for *user_id*. Returns the row including the token."""
    expires_at = dt.datetime.utcnow() + lifetime
    with get_connection() as conn:
        sess_id = _get_unique_session_id(conn)
        token = _generate_token()
        try:
            conn.execute(
                """INSERT INTO sessions (id, token, user_id, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (sess_id, token, user_id, expires_at.isoformat()),
            )
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("create_session failed for %r: %s", user_id, exc)
            return None
        conn.row_factory = _row_to_dict
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (sess_id,)).fetchone()
        conn.row_factory = None
        return row


def get_session_by_token(
    token: str,
    *,
    idle_lifetime: dt.timedelta = DEFAULT_IDLE_LIFETIME,
) -> Optional[dict]:
    """Constant-time token lookup. Returns the session row, or None on
    miss / absolute expiry / idle expiry / revocation. Touches
    last_used_at on hit. Within the rotation grace window, the
    previous token (rotated_from_token) also resolves to the row.

    Logs lifecycle events on idle/expired/revoked-use paths.
    """

    if not token:
        return None
    now = dt.datetime.utcnow()
    grace_cutoff = (now - ROTATION_GRACE_WINDOW).isoformat()
    with get_connection() as conn:
        conn.row_factory = _row_to_dict
        rows = conn.execute("SELECT * FROM sessions").fetchall()
        conn.row_factory = None
        for row in rows:
            # Match against either current or rotated-from token (constant time).
            primary_match = hmac.compare_digest(row["token"], token)
            rotated_match = (
                row.get("rotated_from_token")
                and hmac.compare_digest(row["rotated_from_token"], token)
                and (row.get("last_used_at") or "") > grace_cutoff
            )
            if not primary_match and not rotated_match:
                continue

            # Revocation check.
            if row.get("revoked_at"):
                session_events.log_session_event(
                    row["id"], row["user_id"], "used_after_revocation",
                    metadata={"reason": row.get("revoke_reason")},
                )
                return None

            # Absolute expiry check.
            expires = dt.datetime.fromisoformat(row["expires_at"])
            if expires <= now:
                session_events.log_session_event(
                    row["id"], row["user_id"], "expired",
                )
                return None

            # Idle expiry check.
            last_used = row.get("last_used_at")
            if last_used:
                try:
                    last_used_dt = dt.datetime.fromisoformat(last_used)
                except ValueError:
                    last_used_dt = now  # tolerate corrupt timestamp
                if now - last_used_dt > idle_lifetime:
                    session_events.log_session_event(
                        row["id"], row["user_id"], "idle_expired",
                        metadata={
                            "idle_minutes": int(
                                (now - last_used_dt).total_seconds() / 60
                            ),
                        },
                    )
                    return None

            # Touch last_used_at.
            conn.execute(
                "UPDATE sessions SET last_used_at = ? WHERE id = ?",
                (now.isoformat(), row["id"]),
            )
            conn.commit()
            row["last_used_at"] = now.isoformat()
            return row
    return None


def revoke_session(token: str, *, reason: str = "logout") -> bool:
    """Soft-revoke a single session by token. Returns True if matched."""

    if not token:
        return False
    now = dt.datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.row_factory = _row_to_dict
        rows = conn.execute(
            "SELECT id, user_id, token FROM sessions WHERE revoked_at IS NULL"
        ).fetchall()
        conn.row_factory = None
        for row in rows:
            if hmac.compare_digest(row["token"], token):
                conn.execute(
                    "UPDATE sessions SET revoked_at = ?, revoke_reason = ? WHERE id = ?",
                    (now, reason, row["id"]),
                )
                conn.commit()
                session_events.log_session_event(
                    row["id"], row["user_id"], "revoked",
                    metadata={"reason": reason},
                )
                return True
    return False


def rotate_session(token: str) -> Optional[dict]:
    """Issue a new token for the session matched by `token`. The previous
    token is preserved in `rotated_from_token` for the grace window.

    Returns the updated row, or None if `token` doesn't match an active session.
    """

    if not token:
        return None
    now = dt.datetime.utcnow().isoformat()
    new_token = _generate_token()
    with get_connection() as conn:
        conn.row_factory = _row_to_dict
        rows = conn.execute(
            "SELECT * FROM sessions WHERE revoked_at IS NULL"
        ).fetchall()
        conn.row_factory = None
        for row in rows:
            if not hmac.compare_digest(row["token"], token):
                continue
            old_token = row["token"]
            conn.execute(
                """UPDATE sessions
                   SET token = ?, rotated_from_token = ?, last_used_at = ?
                   WHERE id = ?""",
                (new_token, old_token, now, row["id"]),
            )
            conn.commit()
            row["token"] = new_token
            row["rotated_from_token"] = old_token
            row["last_used_at"] = now
            session_events.log_session_event(
                row["id"], row["user_id"], "rotated",
                metadata={"previous_token_hash": _hash_token(old_token)},
            )
            return row
    return None


def revoke_user_sessions(user_id: str, *, reason: str) -> int:
    """Mark every active session for `user_id` as revoked. Returns count.

    Reasons: 'role_change', 'key_rotation', 'admin', 'logout', etc.
    """

    now = dt.datetime.utcnow().isoformat()
    with get_connection() as conn:
        # Capture the affected sessions for audit log before the UPDATE.
        conn.row_factory = _row_to_dict
        rows = conn.execute(
            "SELECT id FROM sessions WHERE user_id = ? AND revoked_at IS NULL",
            (user_id,),
        ).fetchall()
        conn.row_factory = None
        cursor = conn.execute(
            """UPDATE sessions
               SET revoked_at = ?, revoke_reason = ?
               WHERE user_id = ? AND revoked_at IS NULL""",
            (now, reason, user_id),
        )
        conn.commit()
        affected = cursor.rowcount

    for row in rows:
        session_events.log_session_event(
            row["id"], user_id, "revoked",
            metadata={"reason": reason},
        )
    return affected


def purge_expired_sessions() -> int:
    """Delete every session whose expires_at has passed. Returns the count."""
    now = dt.datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        conn.commit()
        return cursor.rowcount
