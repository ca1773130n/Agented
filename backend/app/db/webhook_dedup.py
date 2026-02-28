"""SQLite-backed webhook deduplication for Agented.

Uses INSERT OR IGNORE on a UNIQUE constraint for atomic check-and-insert,
ensuring no race condition between concurrent greenlets. Dedup keys survive
server restarts because they are persisted in SQLite.

Reference: 05-RESEARCH.md Recommendation 4.
"""

import logging
import time

from .connection import get_connection

logger = logging.getLogger(__name__)


def check_and_insert_dedup_key(
    trigger_id: str, payload_hash: str, ttl_seconds: int = 10
) -> bool:
    """Atomically check-and-insert a dedup key. Returns True if NEW (not duplicate).

    Uses INSERT OR IGNORE to avoid race conditions:
    1. DELETE any expired entry for this exact key pair (allows re-delivery after TTL).
    2. INSERT OR IGNORE the key with the current timestamp.
    3. Return whether the INSERT actually inserted a row (rowcount > 0).

    Args:
        trigger_id: The trigger ID that matched the webhook.
        payload_hash: A short hash of the webhook payload.
        ttl_seconds: Time-to-live in seconds (default 10).

    Returns:
        True if the key was newly inserted (not a duplicate).
        False if a non-expired duplicate already exists.
    """
    cutoff = time.time() - ttl_seconds
    now = time.time()

    with get_connection() as conn:
        # Remove any expired entry for this exact key pair so re-delivery works after TTL
        conn.execute(
            "DELETE FROM webhook_dedup_keys "
            "WHERE trigger_id = ? AND payload_hash = ? AND created_at < ?",
            (trigger_id, payload_hash, cutoff),
        )

        # Atomic insert — silently ignored if a non-expired duplicate exists
        cursor = conn.execute(
            "INSERT OR IGNORE INTO webhook_dedup_keys "
            "(trigger_id, payload_hash, created_at) VALUES (?, ?, ?)",
            (trigger_id, payload_hash, now),
        )
        conn.commit()

        is_new = cursor.rowcount > 0
        if not is_new:
            logger.debug(
                "Dedup key exists: trigger=%s hash=%s (duplicate within %ds)",
                trigger_id,
                payload_hash,
                ttl_seconds,
            )
        return is_new


def cleanup_expired_keys(ttl_seconds: int = 10) -> int:
    """Delete all expired dedup keys from the table.

    Called by APScheduler every 60 seconds to prevent unbounded table growth.

    Args:
        ttl_seconds: Time-to-live in seconds (default 10).

    Returns:
        Number of rows deleted.
    """
    cutoff = time.time() - ttl_seconds

    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM webhook_dedup_keys WHERE created_at < ?",
            (cutoff,),
        )
        conn.commit()
        deleted = cursor.rowcount

    if deleted > 0:
        logger.info("Webhook dedup cleanup: removed %d expired key(s)", deleted)
    return deleted
