"""Retry and rate-limit state management extracted from ExecutionService.

Owns the in-memory retry state dicts and exposes classmethods that
ExecutionService delegates to for backward compatibility.
"""

import datetime
import json
import logging
import random
import threading
from typing import Dict, Optional

from app.config import MAX_RETRY_ATTEMPTS, MAX_RETRY_DELAY

from ..database import delete_pending_retry, get_all_pending_retries, upsert_pending_retry

logger = logging.getLogger(__name__)


class ExecutionRetryManager:
    """Manages rate-limit retry scheduling, tracking, and persistence."""

    # Thread-safe dict tracking rate limit detections: {execution_id: cooldown_seconds}
    _rate_limit_detected: Dict[str, int] = {}
    # Thread-safe dict tracking transient failure detections: {execution_id: error_description}
    _transient_failure_detected: Dict[str, str] = {}
    # _rate_limit_lock guards _rate_limit_detected, _transient_failure_detected,
    # _pending_retries, _retry_timers, and _retry_counts.
    # Acquire before any read or write to those dicts.
    _rate_limit_lock = threading.Lock()

    # Pending rate-limit retries: {trigger_id: {"retry_at": str, "cooldown_seconds": int, ...}}
    _pending_retries: Dict[str, dict] = {}
    # Active retry timers: {trigger_id: threading.Timer}
    _retry_timers: Dict[str, threading.Timer] = {}
    # Per-trigger consecutive retry attempt counter: {trigger_id: int}
    _retry_counts: Dict[str, int] = {}

    @classmethod
    def was_rate_limited(cls, execution_id: str) -> Optional[int]:
        """Check if an execution was rate-limited. Returns cooldown seconds or None.

        Pops the entry from the tracking dict (one-time check).
        """
        if not execution_id:
            return None
        with cls._rate_limit_lock:
            return cls._rate_limit_detected.pop(execution_id, None)

    @classmethod
    def was_transient_failure(cls, execution_id: str) -> Optional[str]:
        """Check if an execution had a transient failure. Returns error description or None.

        Pops the entry from the tracking dict (one-time check).
        Uses CircuitBreakerService.is_transient_error for classification.
        """
        if not execution_id:
            return None
        with cls._rate_limit_lock:
            return cls._transient_failure_detected.pop(execution_id, None)

    @classmethod
    def schedule_retry(
        cls,
        trigger: dict,
        message_text: str,
        event: Optional[dict],
        trigger_type: str,
        cooldown_seconds: int,
    ) -> None:
        """Schedule a retry execution after rate-limit cooldown expires.

        Replaces any existing pending retry for the same trigger.
        Called by OrchestrationService when all fallback accounts are exhausted
        and at least one was rate-limited.
        """
        # Lazy imports to avoid circular dependencies
        from .audit_log_service import AuditLogService
        from .execution_log_service import ExecutionLogService

        trigger_id = trigger["id"]

        # Cancel existing timer for this trigger
        with cls._rate_limit_lock:
            existing = cls._retry_timers.pop(trigger_id, None)
            attempt_count = cls._retry_counts.get(trigger_id, 0) + 1
            cls._retry_counts[trigger_id] = attempt_count
        if existing:
            existing.cancel()

        if attempt_count > MAX_RETRY_ATTEMPTS:
            logger.error(
                "Rate-limit retry for trigger %s has exceeded max attempts (%d/%d) — "
                "giving up to prevent infinite retry loop",
                trigger_id,
                attempt_count,
                MAX_RETRY_ATTEMPTS,
            )
            AuditLogService.log(
                action="retry.exhausted",
                entity_type="trigger",
                entity_id=trigger_id,
                outcome="terminal_failure",
                details={
                    "attempt_count": attempt_count,
                    "max_attempts": MAX_RETRY_ATTEMPTS,
                    "trigger_type": trigger_type,
                },
            )
            # Import ExecutionState locally to avoid circular import
            from .execution_service import ExecutionState

            # Create a failed execution record so the terminal state is observable in the UI
            terminal_exec_id = ExecutionLogService.start_execution(
                trigger_id=trigger_id,
                trigger_type=trigger_type,
                prompt="[rate-limit retry exhausted]",
                backend_type=trigger.get("backend_type", "claude"),
            )
            if terminal_exec_id:
                ExecutionLogService.append_log(
                    terminal_exec_id,
                    "stderr",
                    f"[TERMINAL] Rate-limit retry exhausted after {attempt_count} attempts "
                    f"(max={MAX_RETRY_ATTEMPTS}). No further retries will be scheduled.",
                )
                ExecutionLogService.finish_execution(
                    execution_id=terminal_exec_id,
                    status=ExecutionState.FAILED,
                    exit_code=-1,
                    error_message=(
                        f"Rate-limit retry exhausted: {attempt_count}/{MAX_RETRY_ATTEMPTS} attempts"
                    ),
                )
            with cls._rate_limit_lock:
                cls._retry_counts.pop(trigger_id, None)
            delete_pending_retry(trigger_id)
            return

        retry_at = (
            datetime.datetime.now() + datetime.timedelta(seconds=cooldown_seconds)
        ).isoformat()

        with cls._rate_limit_lock:
            cls._pending_retries[trigger_id] = {
                "trigger_id": trigger_id,
                "cooldown_seconds": cooldown_seconds,
                "retry_at": retry_at,
                "scheduled_at": datetime.datetime.now().isoformat(),
                "attempt": attempt_count,
            }

        # Persist to DB so the retry survives a server restart
        upsert_pending_retry(
            trigger_id=trigger_id,
            trigger_json=json.dumps(trigger, default=str),
            message_text=message_text,
            event_json=json.dumps(event, default=str) if event else "{}",
            trigger_type=trigger_type,
            cooldown_seconds=cooldown_seconds,
            retry_at=retry_at,
        )

        def _retry() -> None:
            with cls._rate_limit_lock:
                cls._retry_timers.pop(trigger_id, None)
                cls._pending_retries.pop(trigger_id, None)
                cls._retry_counts.pop(trigger_id, None)
            delete_pending_retry(trigger_id)
            logger.info(
                "Executing rate-limit retry for trigger %s (attempt %d)", trigger_id, attempt_count
            )
            from .orchestration_service import OrchestrationService

            OrchestrationService.execute_with_fallback(trigger, message_text, event, trigger_type)

        # Exponential backoff: base * 2^(attempt-1), capped at MAX_RETRY_DELAY, plus random jitter
        # to reduce thundering herd when multiple executions hit rate limits simultaneously.
        jitter = random.uniform(0, min(10, cooldown_seconds))
        backoff_delay = min(cooldown_seconds * (2 ** (attempt_count - 1)), MAX_RETRY_DELAY) + jitter

        timer = threading.Timer(backoff_delay, _retry)
        timer.daemon = True
        timer.start()
        with cls._rate_limit_lock:
            cls._retry_timers[trigger_id] = timer

        logger.info(
            "Rate-limit retry scheduled: trigger=%s, attempt=%d/%d, base_cooldown=%ds, "
            "backoff_delay=%.1fs, retry_at=%s",
            trigger_id,
            attempt_count,
            MAX_RETRY_ATTEMPTS,
            cooldown_seconds,
            backoff_delay,
            retry_at,
        )

    @classmethod
    def get_pending_retries(cls) -> dict:
        """Return a snapshot of all pending rate-limit retries keyed by trigger_id.

        Merges in-memory state with the DB so callers see all pending retries regardless
        of whether the in-memory timer was restored after a restart.
        """
        with cls._rate_limit_lock:
            result = dict(cls._pending_retries)
        # Supplement with DB rows not currently tracked in memory
        try:
            for row in get_all_pending_retries():
                tid = row["trigger_id"]
                if tid not in result:
                    result[tid] = {
                        "trigger_id": tid,
                        "cooldown_seconds": row.get("cooldown_seconds", 0),
                        "retry_at": row.get("retry_at", ""),
                        "scheduled_at": row.get("created_at", ""),
                    }
        except Exception as e:
            logger.warning("Could not load pending retries from DB: %s", e, exc_info=True)
        return result

    @classmethod
    def restore_pending_retries(cls) -> int:
        """Re-schedule any pending retries persisted in the DB. Returns the count restored.

        Called once at app startup to recover retries that were in-flight when the server
        was last restarted.
        """
        restored = 0
        try:
            rows = get_all_pending_retries()
        except Exception as e:
            logger.error("Failed to load pending retries from DB for restore: %s", e, exc_info=True)
            return 0

        now = datetime.datetime.now()
        for row in rows:
            trigger_id = row["trigger_id"]
            try:
                trigger = json.loads(row["trigger_json"])
                message_text = row.get("message_text", "")
                event_raw = row.get("event_json") or "{}"
                event = json.loads(event_raw) if event_raw != "{}" else None
                trigger_type = row.get("trigger_type", "webhook")
                retry_at_str = row["retry_at"]
                retry_at = datetime.datetime.fromisoformat(retry_at_str)

                # Compute remaining delay; fire immediately if already past due
                remaining = max(0.0, (retry_at - now).total_seconds())

                # Remove stale in-memory entry so schedule_retry can re-add it cleanly.
                # Cancel is called inside the lock to close the window between the pop
                # and the cancel where a timer could fire and cause double-execution.
                with cls._rate_limit_lock:
                    cls._pending_retries.pop(trigger_id, None)
                    old_timer = cls._retry_timers.pop(trigger_id, None)
                    if old_timer:
                        old_timer.cancel()

                def _retry(
                    _trigger=trigger,
                    _message=message_text,
                    _event=event,
                    _type=trigger_type,
                    _tid=trigger_id,
                ) -> None:
                    with cls._rate_limit_lock:
                        cls._retry_timers.pop(_tid, None)
                        cls._pending_retries.pop(_tid, None)
                    delete_pending_retry(_tid)
                    logger.info("Executing restored rate-limit retry for trigger %s", _tid)
                    from .orchestration_service import OrchestrationService

                    OrchestrationService.execute_with_fallback(_trigger, _message, _event, _type)

                with cls._rate_limit_lock:
                    cls._pending_retries[trigger_id] = {
                        "trigger_id": trigger_id,
                        "cooldown_seconds": row.get("cooldown_seconds", 0),
                        "retry_at": retry_at_str,
                        "scheduled_at": row.get("created_at", ""),
                    }

                timer = threading.Timer(remaining, _retry)
                timer.daemon = True
                timer.start()

                with cls._rate_limit_lock:
                    cls._retry_timers[trigger_id] = timer

                logger.info(
                    "Restored pending retry for trigger %s (fires in %.1fs)",
                    trigger_id,
                    remaining,
                )
                restored += 1
            except Exception as e:
                logger.error(
                    "Failed to restore pending retry for trigger %s: %s",
                    trigger_id,
                    e,
                    exc_info=True,
                )

        if restored:
            logger.warning(
                "Restored %d rate-limit retry/retries from DB after server restart", restored
            )
        return restored
