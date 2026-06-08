"""Chat retry queue service (rate-limit rotation Phase 2).

When `streaming_helper` exhausts every eligible account for a chat turn
(all rate-limited), it parks the turn here instead of just erroring. The
`chat_retry_queue` scheduler job calls :meth:`process_pending` every ~20s;
for each queued turn it asks the rotation layer whether any eligible
account now exists and, if so, re-dispatches the turn (which rotates onto
the freed account). The queue is persisted, so it survives a restart.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Give up after this many dispatch attempts so a permanently-broken turn
# can't loop forever. Each scheduler re-dispatch + each fresh exhaustion
# bumps the counter.
MAX_ATTEMPTS = 24


class ChatRetryService:
    """Persistent queue + scheduler-driven re-dispatch for rate-limited turns."""

    @classmethod
    def enqueue(
        cls,
        *,
        session_id: str,
        super_agent_id: str,
        backend: Optional[str],
        account_id: Optional[str],
        model: Optional[str],
        cwd: Optional[str],
        chat_mode: Optional[str],
        instance_id: Optional[str],
        use_cli_agent: Optional[bool],
        reason: Optional[str],
    ) -> None:
        """Park a chat turn for retry once an account frees up."""
        from ..db.chat_retry_queue import enqueue_chat_retry

        enqueue_chat_retry(
            session_id=session_id,
            super_agent_id=super_agent_id,
            backend=backend,
            account_id=account_id,
            model=model,
            cwd=cwd,
            chat_mode=chat_mode,
            instance_id=instance_id,
            use_cli_agent=use_cli_agent,
            reason=reason,
        )
        logger.info("Chat retry queued for session %s (backend=%s)", session_id, backend)

    @classmethod
    def has_eligible_account(cls, backend: Optional[str]) -> bool:
        """True when at least one non-rate-limited account exists to retry on
        (same backend or, per policy, another CLI backend)."""
        from .account_rotation_service import rotation_candidates

        return bool(rotation_candidates(backend or "", exclude_account_ids=set()))

    @classmethod
    def process_pending(cls) -> int:
        """Scheduler tick: re-dispatch queued turns that now have an eligible
        account. Returns the number re-dispatched. Wrapped so a failure can't
        kill the APScheduler job."""
        dispatched = 0
        try:
            from ..db.chat_retry_queue import (
                delete_chat_retry,
                list_pending_chat_retries,
                mark_chat_retry_attempted,
            )

            pending = list_pending_chat_retries()
            if not pending:
                return 0

            for row in pending:
                session_id = row["session_id"]
                backend = row.get("backend")

                if row.get("attempts", 0) >= MAX_ATTEMPTS:
                    logger.warning(
                        "Chat retry for session %s exceeded %d attempts — giving up",
                        session_id,
                        MAX_ATTEMPTS,
                    )
                    delete_chat_retry(session_id)
                    cls._notify_gave_up(session_id, backend)
                    continue

                if not cls.has_eligible_account(backend):
                    # Still fully rate-limited — leave it queued.
                    continue

                # An account freed up. Remove from the queue BEFORE dispatch so
                # the next tick can't double-fire; if the re-dispatch exhausts
                # again, streaming_helper re-enqueues (bumping attempts).
                mark_chat_retry_attempted(session_id)
                delete_chat_retry(session_id)
                cls._dispatch(row)
                dispatched += 1
        except Exception:
            logger.warning("chat retry queue processing failed", exc_info=True)
        return dispatched

    @classmethod
    def _dispatch(cls, row: dict) -> None:
        """Re-run the parked turn. ``run_streaming_response`` rebuilds the
        prompt from the session's conversation log (the user message is
        already persisted), so we only need the original routing args."""
        from .chat_state_service import ChatStateService
        from .streaming_helper import run_streaming_response

        session_id = row["session_id"]
        try:
            ChatStateService.push_delta(
                session_id,
                "retry_dispatch",
                {"backend": row.get("backend")},
            )
        except Exception:
            logger.debug("retry_dispatch delta push failed", exc_info=True)

        logger.info("Re-dispatching queued chat turn for session %s", session_id)
        run_streaming_response(
            session_id=session_id,
            super_agent_id=row["super_agent_id"],
            backend=row.get("backend"),
            account_id=row.get("account_id"),
            model=row.get("model"),
            cwd=row.get("cwd"),
            chat_mode=row.get("chat_mode"),
            instance_id=row.get("instance_id"),
            use_cli_agent=row.get("use_cli_agent"),
        )

    @classmethod
    def _notify_gave_up(cls, session_id: str, backend: Optional[str]) -> None:
        try:
            from .chat_state_service import ChatStateService

            ChatStateService.push_delta(
                session_id,
                "error",
                {
                    "error": "Gave up retrying after repeated rate limits.",
                    "kind": "rate_limited_giveup",
                },
            )
            ChatStateService.push_status(session_id, "error")
        except Exception:
            logger.debug("give-up notice push failed", exc_info=True)
