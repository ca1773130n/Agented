"""SQLite-backed execution queue with per-trigger concurrency and background dispatcher.

Replaces fire-and-forget thread dispatch with a durable queue that:
- Persists pending executions in SQLite (survives restarts)
- Enforces per-trigger concurrency caps (default 1)
- Checks circuit breaker state before dispatching
- Dispatches in FIFO order within priority levels

Architecture follows persist-queue (2025) SQLite-backed queue patterns.
"""

import json
import logging
import threading
from typing import ClassVar, Dict, Optional

from ..db.execution_queue import (
    cancel_pending_entries,
    count_active_for_trigger,
    enqueue_execution,
    get_pending_entries,
    get_queue_depth,
    get_queue_summary,
    reset_stale_dispatching,
    update_entry_status,
)

logger = logging.getLogger(__name__)

# Maximum pending entries per trigger before rejecting (429)
MAX_QUEUE_DEPTH_PER_TRIGGER = 100


class ExecutionQueueService:
    """SQLite-backed execution queue with background dispatcher thread.

    Uses @classmethod methods following existing service patterns. The dispatcher
    thread polls the queue every 1 second and dispatches entries up to per-trigger
    concurrency caps.
    """

    _dispatcher_thread: ClassVar[Optional[threading.Thread]] = None
    _stop_event: ClassVar[threading.Event] = threading.Event()
    _concurrency_caps: ClassVar[Dict[str, int]] = {}
    _default_concurrency_cap: ClassVar[int] = 1

    @classmethod
    def start_dispatcher(cls) -> None:
        """Start the background dispatcher thread.

        Also recovers any entries stuck in 'dispatching' status from a previous
        crash/restart (stale recovery).

        Called from create_app() during startup.
        """
        # Stale recovery: reset dispatching entries back to pending
        try:
            recovered = reset_stale_dispatching()
            if recovered:
                logger.info(
                    "Recovered %d stale dispatching queue entries back to pending", recovered
                )
        except Exception:
            logger.exception("Failed to recover stale dispatching entries")

        cls._stop_event.clear()

        if cls._dispatcher_thread is not None and cls._dispatcher_thread.is_alive():
            logger.warning("Dispatcher thread already running, skipping start")
            return

        cls._dispatcher_thread = threading.Thread(
            target=cls._dispatcher_loop,
            name="execution-queue-dispatcher",
            daemon=True,
        )
        cls._dispatcher_thread.start()
        logger.info("Execution queue dispatcher started")

    @classmethod
    def stop_dispatcher(cls) -> None:
        """Stop the dispatcher thread gracefully."""
        cls._stop_event.set()
        if cls._dispatcher_thread is not None and cls._dispatcher_thread.is_alive():
            cls._dispatcher_thread.join(timeout=5.0)
            logger.info("Execution queue dispatcher stopped")
        cls._dispatcher_thread = None

    @classmethod
    def enqueue(
        cls,
        trigger_id: str,
        trigger_type: str,
        message_text: str = "",
        event_data: Optional[dict] = None,
    ) -> str:
        """Enqueue an execution for later dispatch.

        Args:
            trigger_id: The trigger generating this execution.
            trigger_type: One of webhook, github, schedule, manual.
            message_text: Rendered message/prompt text.
            event_data: Event payload dict (will be JSON-serialized).

        Returns:
            Queue entry ID.

        Raises:
            QueueFullError: If per-trigger queue depth exceeds MAX_QUEUE_DEPTH_PER_TRIGGER.
        """
        # Check per-trigger queue depth cap
        current_depth = get_queue_depth(trigger_id)
        if current_depth >= MAX_QUEUE_DEPTH_PER_TRIGGER:
            raise QueueFullError(
                f"Queue depth limit ({MAX_QUEUE_DEPTH_PER_TRIGGER}) exceeded "
                f"for trigger {trigger_id}"
            )

        event_json = json.dumps(event_data, default=str) if event_data else "{}"
        entry_id = enqueue_execution(
            trigger_id=trigger_id,
            trigger_type=trigger_type,
            message_text=message_text,
            event_data=event_json,
        )
        logger.info("Enqueued execution %s for trigger %s (%s)", entry_id, trigger_id, trigger_type)
        return entry_id

    @classmethod
    def _dispatcher_loop(cls) -> None:
        """Main dispatcher loop. Polls queue every 1 second."""
        logger.info("Dispatcher loop started")
        while not cls._stop_event.is_set():
            try:
                cls._dispatch_batch()
            except Exception:
                logger.exception("Error in dispatcher loop iteration")

            # Wait 1 second or until stop is requested
            cls._stop_event.wait(timeout=1.0)

        logger.info("Dispatcher loop exiting")

    @classmethod
    def _dispatch_batch(cls) -> None:
        """Fetch pending entries and dispatch eligible ones."""
        entries = get_pending_entries(limit=10)
        if not entries:
            return

        for entry in entries:
            trigger_id = entry["trigger_id"]
            entry_id = entry["id"]

            # Check concurrency cap
            cap = cls.get_concurrency_cap(trigger_id)
            active = count_active_for_trigger(trigger_id)
            if active >= cap:
                continue  # Skip, will retry next poll cycle

            # Check circuit breaker -- get backend type from trigger config
            try:
                from .circuit_breaker_service import CircuitBreakerService

                # Look up trigger to get backend_type
                from ..database import get_trigger

                trigger = get_trigger(trigger_id)
                if trigger:
                    backend_type = trigger.get("backend_type", "claude")
                    if not CircuitBreakerService.can_execute(backend_type):
                        logger.debug(
                            "Circuit breaker OPEN for %s, skipping entry %s",
                            backend_type,
                            entry_id,
                        )
                        continue  # Leave in queue, will retry next poll cycle
            except Exception:
                logger.exception("Error checking circuit breaker for entry %s", entry_id)
                # Proceed with dispatch even if breaker check fails

            # CAS update to dispatching
            updated = update_entry_status(entry_id, "dispatching", expected_status="pending")
            if not updated:
                continue  # Another thread got it first

            # Spawn thread to execute
            thread = threading.Thread(
                target=cls._dispatch_entry,
                args=(entry,),
                daemon=True,
                name=f"dispatch-{entry_id}",
            )
            thread.start()

    @classmethod
    def _dispatch_entry(cls, entry: dict) -> None:
        """Execute a single queue entry in a background thread.

        Calls OrchestrationService.execute_with_fallback() for standard triggers,
        or TeamExecutionService for team-mode triggers.
        """
        entry_id = entry["id"]
        trigger_id = entry["trigger_id"]
        trigger_type = entry["trigger_type"]

        try:
            from ..database import get_trigger

            trigger = get_trigger(trigger_id)
            if not trigger:
                logger.error("Trigger %s not found for queue entry %s", trigger_id, entry_id)
                update_entry_status(entry_id, "failed", expected_status="dispatching")
                return

            message_text = entry.get("message_text", "")
            event_data_raw = entry.get("event_data", "{}")
            event = json.loads(event_data_raw) if event_data_raw and event_data_raw != "{}" else None

            # Delegate to team execution if execution_mode is 'team'
            if trigger.get("execution_mode") == "team" and trigger.get("team_id"):
                from .team_execution_service import TeamExecutionService

                TeamExecutionService.execute_team(
                    trigger["team_id"], message_text, event, trigger_type
                )
            else:
                from .orchestration_service import OrchestrationService

                OrchestrationService.execute_with_fallback(
                    trigger, message_text, event, trigger_type
                )

            update_entry_status(entry_id, "completed", expected_status="dispatching")
            logger.info("Queue entry %s completed successfully", entry_id)

        except Exception:
            logger.exception("Queue entry %s failed", entry_id)
            update_entry_status(entry_id, "failed", expected_status="dispatching")

    @classmethod
    def get_concurrency_cap(cls, trigger_id: str) -> int:
        """Get the concurrency cap for a trigger.

        Args:
            trigger_id: The trigger to look up.

        Returns:
            Concurrency cap (default 1).
        """
        return cls._concurrency_caps.get(trigger_id, cls._default_concurrency_cap)

    @classmethod
    def set_concurrency_cap(cls, trigger_id: str, cap: int) -> None:
        """Set the concurrency cap for a trigger.

        Args:
            trigger_id: The trigger to configure.
            cap: Maximum concurrent executions (must be >= 1).
        """
        cls._concurrency_caps[trigger_id] = max(1, cap)

    @classmethod
    def reset(cls) -> None:
        """Reset all in-memory state. Used for testing."""
        cls.stop_dispatcher()
        cls._concurrency_caps.clear()
        cls._stop_event.clear()


class QueueFullError(Exception):
    """Raised when per-trigger queue depth exceeds the configured limit."""

    pass
