"""OIDC identity link DB layer (Phase 25, 25-04). Raw SQLite, no ORM."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def link_identity(
    provider: str, issuer: str, subject: str, user_id: str, email: Optional[str] = None
) -> bool:
    """Link a verified (issuer, subject) to a local user_id. Idempotent.

    Uses INSERT OR IGNORE on the (issuer, subject) primary key so a repeated
    first-login is a no-op rather than an error.
    """
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO oidc_identities "
            "(provider, issuer, subject, user_id, email, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (provider, issuer, subject, user_id, email, now),
        )
        conn.commit()
    return True


def get_user_for_identity(issuer: str, subject: str) -> Optional[str]:
    """Return the ``user_id`` linked to (issuer, subject), or None."""
    if not issuer or not subject:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT user_id FROM oidc_identities WHERE issuer = ? AND subject = ?",
            (issuer, subject),
        ).fetchone()
    return row["user_id"] if row else None
