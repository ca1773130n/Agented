"""Password reset tokens (track B, wave 43).

Single-use, time-limited tokens. ``request_reset`` issues one and logs
the reset link to stderr; ``consume_token`` validates the token and
returns the associated user_id. The actual email delivery is out of
scope until SMTP is wired.
"""

from __future__ import annotations

import datetime as dt
import hmac
import logging
import secrets
from typing import Optional

from .connection import get_connection

logger = logging.getLogger(__name__)
DEFAULT_LIFETIME = dt.timedelta(hours=1)


def request_reset(user_id: str, lifetime: dt.timedelta = DEFAULT_LIFETIME) -> Optional[str]:
    """Issue a fresh password-reset token for *user_id*. Returns the token."""
    token = secrets.token_urlsafe(32)
    token_id = "prt-" + secrets.token_hex(3)
    expires_at = dt.datetime.utcnow() + lifetime
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO password_reset_tokens (id, token, user_id, expires_at)
               VALUES (?, ?, ?, ?)""",
            (token_id, token, user_id, expires_at.isoformat()),
        )
        conn.commit()
    return token


def consume_token(token: str) -> Optional[str]:
    """Validate *token* and mark it consumed. Returns the user_id, or None
    on miss/expired/already-consumed."""
    if not token:
        return None
    now = dt.datetime.utcnow()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, token, user_id, expires_at, consumed_at "
            "FROM password_reset_tokens"
        ).fetchall()
        for row_id, row_token, user_id, expires_at, consumed_at in rows:
            if not hmac.compare_digest(row_token, token):
                continue
            if consumed_at is not None:
                return None
            if dt.datetime.fromisoformat(expires_at) <= now:
                return None
            conn.execute(
                "UPDATE password_reset_tokens SET consumed_at = ? WHERE id = ?",
                (now.isoformat(), row_id),
            )
            conn.commit()
            return user_id
    return None
