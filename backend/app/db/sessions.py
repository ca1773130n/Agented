"""Session token storage (track B, wave 32).

Tokens are 256-bit URL-safe random strings. Verification is constant-time
(hmac.compare_digest) and rotates ``last_used_at`` so a future grooming
job can prune idle sessions.
"""

from __future__ import annotations

import datetime as dt
import hmac
import logging
import secrets
from typing import Optional

from .connection import get_connection
from .ids import _get_unique_session_id

logger = logging.getLogger(__name__)

DEFAULT_LIFETIME = dt.timedelta(days=14)


def _row_to_dict(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def _generate_token() -> str:
    """256-bit URL-safe random token (43 chars)."""
    return secrets.token_urlsafe(32)


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


def get_session_by_token(token: str) -> Optional[dict]:
    """Constant-time token lookup. Returns the session row, or None on miss
    or expiry. Touches last_used_at on hit."""
    if not token:
        return None
    now = dt.datetime.utcnow()
    with get_connection() as conn:
        conn.row_factory = _row_to_dict
        rows = conn.execute("SELECT * FROM sessions").fetchall()
        conn.row_factory = None
        for row in rows:
            if not hmac.compare_digest(row["token"], token):
                continue
            expires = dt.datetime.fromisoformat(row["expires_at"])
            if expires <= now:
                return None
            conn.execute(
                "UPDATE sessions SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?",
                (row["id"],),
            )
            conn.commit()
            row["last_used_at"] = now.isoformat()
            return row
    return None


def revoke_session(token: str) -> bool:
    """Delete a session row by its token. Returns True if a row was removed."""
    if not token:
        return False
    with get_connection() as conn:
        rows = conn.execute("SELECT id, token FROM sessions").fetchall()
        for row_id, row_token in rows:
            if hmac.compare_digest(row_token, token):
                cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (row_id,))
                conn.commit()
                return cursor.rowcount > 0
    return False


def purge_expired_sessions() -> int:
    """Delete every session whose expires_at has passed. Returns the count."""
    now = dt.datetime.utcnow().isoformat()
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        conn.commit()
        return cursor.rowcount
