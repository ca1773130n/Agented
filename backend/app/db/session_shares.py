"""Share-token DB layer for live-share / co-drive (Phase 25, 25-01).

Raw SQLite via ``get_connection()`` (no ORM), mirroring ``db/sessions.py`` and
``db/password_resets.py``. The token model reuses ``secrets.token_urlsafe(32)``
— NO new crypto. A share token:

* is cryptographically random and opaque,
* is scoped to exactly ONE ``session_id``,
* carries a ``scope`` in {``read``, ``chat``} (a ``read`` token physically
  cannot reach the co-drive write path — 25-02 checks scope before any IO),
* is REVOCABLE (``revoked=1``) and EXPIRING (``expires_at``),
* resolves to a row ONLY while ``revoked==0 AND expires_at>now`` — otherwise
  ``None`` (fail closed).

A share grants READ + chat on ONE session; it never carries operator/admin
rights and never exposes the operator's API key or session cookie.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from .connection import get_connection

logger = logging.getLogger(__name__)

# Default token entropy (bytes before base64url). 32 bytes → ~43 url-safe chars.
_TOKEN_NBYTES = 32
# Default lifetime for a minted share token (24h) — bounded so a leaked URL
# stops working even if the operator forgets to revoke it.
DEFAULT_TTL_SECONDS = 24 * 60 * 60
VALID_SCOPES = ("read", "chat")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_dict(row) -> dict:
    return dict(row) if row is not None else None


def mint_share_token(
    session_id: str,
    scope: str = "read",
    created_by: Optional[str] = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Mint a scoped, expiring share token for ``session_id``. Returns the token.

    ``scope`` must be one of :data:`VALID_SCOPES`. ``ttl_seconds`` may be
    negative (used by tests to mint an already-expired token).
    """
    if scope not in VALID_SCOPES:
        raise ValueError(f"invalid share scope {scope!r} (want one of {VALID_SCOPES})")
    token = secrets.token_urlsafe(_TOKEN_NBYTES)
    now = _now()
    expires_at = now + timedelta(seconds=ttl_seconds)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO session_share_tokens "
            "(token, session_id, scope, created_by, created_at, expires_at, revoked) "
            "VALUES (?, ?, ?, ?, ?, ?, 0)",
            (token, session_id, scope, created_by, now.isoformat(), expires_at.isoformat()),
        )
        conn.commit()
    return token


def resolve_share_token(token: str) -> Optional[dict]:
    """Return the share-token row ONLY when it is live (not revoked, not expired).

    A revoked token, an expired token, or an unknown token all resolve to
    ``None`` (fail closed). The returned dict includes ``session_id`` + ``scope``.
    """
    if not token:
        return None
    with get_connection() as conn:
        conn.row_factory = None
        row = conn.execute(
            "SELECT token, session_id, scope, created_by, created_at, expires_at, revoked "
            "FROM session_share_tokens WHERE token = ?",
            (token,),
        ).fetchone()
    if row is None:
        return None
    d = {
        "token": row[0],
        "session_id": row[1],
        "scope": row[2],
        "created_by": row[3],
        "created_at": row[4],
        "expires_at": row[5],
        "revoked": row[6],
    }
    if d["revoked"]:
        return None
    try:
        expires_at = datetime.fromisoformat(d["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        # An unparseable expiry is treated as expired (fail closed).
        return None
    if expires_at <= _now():
        return None
    return d


def revoke_share_token(token: str) -> bool:
    """Revoke a share token. Returns True if a live row was flipped to revoked."""
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE session_share_tokens SET revoked = 1 WHERE token = ? AND revoked = 0",
            (token,),
        )
        conn.commit()
        return cur.rowcount > 0


def list_shares_for_session(session_id: str) -> list[dict]:
    """List all share-token rows minted for ``session_id`` (incl. revoked/expired)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT token, session_id, scope, created_by, created_at, expires_at, revoked "
            "FROM session_share_tokens WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,),
        ).fetchall()
    return [
        {
            "token": r[0],
            "session_id": r[1],
            "scope": r[2],
            "created_by": r[3],
            "created_at": r[4],
            "expires_at": r[5],
            "revoked": r[6],
        }
        for r in rows
    ]
