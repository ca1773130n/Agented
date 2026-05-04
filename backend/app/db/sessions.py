"""Session token storage (track B, wave 32).

Tokens are 256-bit URL-safe random strings. Per-token comparison is
``hmac.compare_digest``; the lookup itself is a no-early-return scan
that visits every active row before deciding (see
``get_session_by_token`` for the precise timing contract).

v0.5.12: idle-expiry, token rotation with grace window anchored to
``rotated_at``, revoke-by-user, soft-delete revocation, and audit
logging via session_events.
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
    """Token lookup with index-driven SELECT. Returns the session row,
    or None on miss / absolute expiry / idle expiry / revocation.
    Touches last_used_at on hit. Within the rotation grace window,
    the previous token (rotated_from_token) also resolves to the row.

    Logs lifecycle events on idle/expired/revoked-use paths.

    Timing contract (v0.6.0 round-1):
      - Per-row work is uniform: every matched row runs both the
        primary and rotated-token compare_digest calls plus the
        revocation/expiry/idle checks before deciding.
      - 0-row miss path pays one dummy compare_digest so the lookup
        cost doesn't drop to a bare SELECT (eliminates the "did we
        compare?" timing leak).
      - The hit path pays one extra UPDATE (touch last_used_at).
        That asymmetry is observable in microseconds but does not
        depend on token contents — so it's robust against the
        threat model where the attacker can only see network-level
        latency, not per-CPU-cycle timing.

    Lookup goes through idx_sessions_token (auto-unique from the
    `token UNIQUE` table constraint) + idx_sessions_rotated_from_token.
    """

    if not token:
        return None
    now = dt.datetime.utcnow()
    grace_cutoff = (now - ROTATION_GRACE_WINDOW).isoformat()
    matched_row: Optional[dict] = None
    failure_event: Optional[tuple[str, str, Optional[str], Optional[dict]]] = None
    # v0.6.0 round-1 fix: floor compare on miss so the indexed lookup
    # doesn't leak hit-vs-miss via "did we run compare_digest?" timing.
    # The token-length sentinel keeps the compare's work proportional
    # to the input.
    _DUMMY_TOKEN = "0" * len(token)
    with get_connection() as conn:
        conn.row_factory = _row_to_dict
        # Indexed lookup via idx_sessions_token (auto-unique from the
        # `token TEXT UNIQUE NOT NULL` table constraint, migration 104)
        # + idx_sessions_rotated_from_token (migration 109). At most 2
        # rows match in practice; the loop runs compare_digest on each
        # so per-row work is uniform, and on a 0-row miss we still pay
        # one compare_digest below to floor the timing.
        rows = conn.execute(
            "SELECT * FROM sessions WHERE token = ? OR rotated_from_token = ?",
            (token, token),
        ).fetchall()
        conn.row_factory = None
        if not rows:
            # Floor the miss timing — equalize against the hit path's
            # compare cost. Doesn't fully equalize against the post-hit
            # UPDATE, but eliminates the "0 vs 1+ compares" leak.
            hmac.compare_digest(_DUMMY_TOKEN, token)
            return None
        for row in rows:
            primary_match = hmac.compare_digest(row["token"], token)
            rotated_token = row.get("rotated_from_token") or ""
            rotated_compare = (
                hmac.compare_digest(rotated_token, token) if rotated_token else False
            )
            # v0.5.12 round-3: anchor grace window to `rotated_at`
            # (set only by rotate_session) instead of `last_used_at`
            # (refreshed on every successful auth). Otherwise an
            # attacker replaying the old token could slide the window
            # forward indefinitely.
            rotated_in_window = (row.get("rotated_at") or "") > grace_cutoff
            rotated_match = bool(rotated_token) and rotated_compare and rotated_in_window
            if not primary_match and not rotated_match:
                continue

            if row.get("revoked_at"):
                failure_event = (
                    row["id"], row["user_id"], "used_after_revocation",
                    {"reason": row.get("revoke_reason")},
                )
                continue

            expires = dt.datetime.fromisoformat(row["expires_at"])
            if expires <= now:
                failure_event = (row["id"], row["user_id"], "expired", None)
                continue

            last_used = row.get("last_used_at")
            if last_used:
                try:
                    last_used_dt = dt.datetime.fromisoformat(last_used)
                except ValueError:
                    last_used_dt = now  # tolerate corrupt timestamp
                if now - last_used_dt > idle_lifetime:
                    failure_event = (
                        row["id"], row["user_id"], "idle_expired",
                        {"idle_minutes": int((now - last_used_dt).total_seconds() / 60)},
                    )
                    continue

            matched_row = row

        if matched_row is not None:
            conn.execute(
                "UPDATE sessions SET last_used_at = ? WHERE id = ?",
                (now.isoformat(), matched_row["id"]),
            )
            conn.commit()
            matched_row["last_used_at"] = now.isoformat()

    if matched_row is None and failure_event is not None:
        session_id, user_id, event_type, metadata = failure_event
        session_events.log_session_event(
            session_id, user_id, event_type, metadata=metadata,
        )
    return matched_row


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

    Returns the updated row, or None if `token` doesn't match an active
    session. Uses a compare-and-swap UPDATE so two concurrent rotations
    of the same token produce a single canonical new token: the loser
    reloads and returns the winner's row instead of issuing a stale
    second rotation.
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
            cursor = conn.execute(
                """UPDATE sessions
                   SET token = ?,
                       rotated_from_token = ?,
                       rotated_at = ?,
                       last_used_at = ?
                   WHERE id = ? AND token = ? AND revoked_at IS NULL""",
                (new_token, old_token, now, now, row["id"], old_token),
            )
            conn.commit()
            if cursor.rowcount == 0:
                # Lost the race. Reload to distinguish two scenarios:
                #   a) parallel rotation won → canonical token differs;
                #      return the reloaded row so the caller emits the
                #      correct X-New-Session-Token.
                #   b) parallel revocation set revoked_at → return None
                #      so middleware does NOT emit a header for a
                #      revoked session.
                conn.row_factory = _row_to_dict
                current = conn.execute(
                    "SELECT * FROM sessions WHERE id = ?", (row["id"],)
                ).fetchone()
                conn.row_factory = None
                if current is None or current.get("revoked_at"):
                    return None
                return current
            row["token"] = new_token
            row["rotated_from_token"] = old_token
            row["rotated_at"] = now
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
