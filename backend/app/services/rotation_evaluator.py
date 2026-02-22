"""Rotation evaluator — 15-second APScheduler interval job that monitors running sessions
and triggers hysteresis-damped rotation decisions.

Bridges the gap between monitoring data (polled every 5 minutes) and rotation action
by evaluating running sessions every 15 seconds. Hysteresis damping prevents false
rotations when utilization oscillates near the threshold.

Composes: ProcessManager (active execution list), ExecutionLogService (execution lookup),
RotationService (should_rotate + execute_rotation), SchedulerService (APScheduler job).
"""

import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class RotationEvaluator:
    """Periodic evaluator that checks running sessions and triggers rotation with hysteresis.

    All methods are classmethods following the existing service pattern
    (MonitoringService, AgentSchedulerService). Thread-safe via _lock for in-memory state.
    """

    _job_id = "rotation_evaluator"
    # {execution_id: {"consecutive_rotate_polls": int, "last_evaluated": str}}
    _evaluation_state: dict = {}
    _lock = threading.Lock()

    DEFAULT_HYSTERESIS_THRESHOLD = 2  # Consecutive "should rotate" polls before acting
    EVALUATION_INTERVAL_SECONDS = 15

    @classmethod
    def init(cls):
        """Initialize rotation evaluator. Called at app startup after MonitoringService
        and AgentSchedulerService."""
        cls._register_job()
        logger.info("RotationEvaluator initialized")

    @classmethod
    def _register_job(cls):
        """Register interval job on SchedulerService._scheduler.

        Follows MonitoringService._register_job() pattern exactly.
        coalesce=True ensures missed evaluations don't pile up.
        max_instances=1 ensures at most one evaluation runs at a time.
        """
        from .scheduler_service import SchedulerService

        if not SchedulerService._scheduler:
            logger.warning("Scheduler not available for rotation evaluator")
            return

        existing = SchedulerService._scheduler.get_job(cls._job_id)
        if existing:
            SchedulerService._scheduler.remove_job(cls._job_id)

        SchedulerService._scheduler.add_job(
            func=cls._evaluate_running_sessions,
            trigger="interval",
            seconds=cls.EVALUATION_INTERVAL_SECONDS,
            id=cls._job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

    @classmethod
    def _evaluate_running_sessions(cls):
        """Main evaluation loop (called by APScheduler every 15s).

        CRITICAL: Entire body wrapped in try/except. Unhandled exceptions in APScheduler
        jobs can kill future invocations. Logs errors and returns gracefully.
        """
        try:
            from .execution_log_service import ExecutionLogService
            from .process_manager import ProcessManager
            from .rotation_service import RotationService

            # Step 1: Get active execution IDs
            active_execution_ids = ProcessManager.get_active_executions()
            if not active_execution_ids:
                cls._cleanup_stale_state([])
                return

            # Step 2-6: Evaluate each active execution
            for execution_id in active_execution_ids:
                try:
                    cls._evaluate_single_execution(
                        execution_id, ExecutionLogService, RotationService
                    )
                except Exception as e:
                    logger.error(
                        f"RotationEvaluator: error evaluating execution {execution_id}: {e}"
                    )

            # Step 7: Clean up stale evaluation state
            cls._cleanup_stale_state(active_execution_ids)

        except Exception as e:
            logger.error(f"RotationEvaluator: unhandled error in evaluation loop: {e}")

    @classmethod
    def _evaluate_single_execution(cls, execution_id, ExecutionLogService, RotationService):
        """Evaluate a single execution for rotation need, applying hysteresis."""
        from ..database import get_trigger

        # Step 2: Get execution record to obtain account_id
        execution = ExecutionLogService.get_execution(execution_id)
        if not execution:
            return

        # Step 3: Skip executions without account_id
        account_id = execution.get("account_id")
        if not account_id:
            return

        # Step 4: Check if rotation is needed
        decision = RotationService.should_rotate(execution_id, account_id)
        should_rotate = decision.get("should_rotate", False)

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Step 5: Apply hysteresis logic
        with cls._lock:
            if execution_id not in cls._evaluation_state:
                cls._evaluation_state[execution_id] = {
                    "consecutive_rotate_polls": 0,
                    "last_evaluated": now_str,
                }

            state = cls._evaluation_state[execution_id]

            if should_rotate:
                state["consecutive_rotate_polls"] += 1
                state["last_evaluated"] = now_str
                counter = state["consecutive_rotate_polls"]
            else:
                # Reset counter on any safe evaluation
                state["consecutive_rotate_polls"] = 0
                state["last_evaluated"] = now_str
                counter = 0

        hysteresis_threshold = cls._get_hysteresis_threshold()

        # Step 6: Trigger rotation if hysteresis threshold reached
        if counter >= hysteresis_threshold:
            logger.info(
                f"RotationEvaluator: hysteresis threshold ({hysteresis_threshold}) "
                f"reached for {execution_id}, dispatching rotation"
            )

            # Get trigger data for the execution
            trigger_id = execution.get("trigger_id")
            trigger = get_trigger(trigger_id) if trigger_id else None
            if not trigger:
                trigger = {}

            original_prompt = execution.get("prompt", "")
            event = {"trigger_type": execution.get("trigger_type", "webhook")}
            trigger_type = execution.get("trigger_type", "webhook")

            # Dispatch rotation to background thread
            threading.Thread(
                target=cls._dispatch_rotation,
                args=(execution_id, trigger, original_prompt, event, trigger_type),
                daemon=True,
            ).start()

            # Reset hysteresis counter
            with cls._lock:
                if execution_id in cls._evaluation_state:
                    cls._evaluation_state[execution_id]["consecutive_rotate_polls"] = 0

    @classmethod
    def _dispatch_rotation(cls, execution_id, trigger, message_text, event, trigger_type):
        """Background rotation dispatch.

        Calls RotationService.execute_rotation(). Wrapped in try/except to prevent
        thread crashes.
        """
        try:
            from .rotation_service import RotationService

            continuation_id = RotationService.execute_rotation(
                execution_id=execution_id,
                trigger=trigger,
                message_text=message_text,
                event=event,
                trigger_type=trigger_type,
            )

            if continuation_id:
                logger.info(
                    f"RotationEvaluator: rotation dispatched for {execution_id}, "
                    f"continuation={continuation_id}"
                )
            else:
                logger.warning(
                    f"RotationEvaluator: rotation returned no continuation for {execution_id}"
                )
        except Exception as e:
            logger.warning(f"RotationEvaluator: rotation dispatch failed for {execution_id}: {e}")

    @classmethod
    def _get_hysteresis_threshold(cls) -> int:
        """Load hysteresis threshold from monitoring config or use default.

        The threshold is the number of consecutive "should rotate" polls before
        acting. At minimum 30 seconds of sustained signal (2 polls * 15 seconds).
        """
        try:
            from ..database import get_monitoring_config

            config = get_monitoring_config()
            return config.get("rotation_hysteresis_polls", cls.DEFAULT_HYSTERESIS_THRESHOLD)
        except Exception:
            return cls.DEFAULT_HYSTERESIS_THRESHOLD

    @classmethod
    def get_evaluator_status(cls) -> dict:
        """Status endpoint data. Thread-safe read under _lock."""
        with cls._lock:
            evaluation_states = dict(cls._evaluation_state)

        return {
            "job_id": cls._job_id,
            "evaluation_interval_seconds": cls.EVALUATION_INTERVAL_SECONDS,
            "hysteresis_threshold": cls._get_hysteresis_threshold(),
            "active_evaluations": len(evaluation_states),
            "evaluation_states": evaluation_states,
        }

    @classmethod
    def _cleanup_stale_state(cls, active_execution_ids: list):
        """Remove entries from _evaluation_state for executions no longer active."""
        with cls._lock:
            stale_keys = [key for key in cls._evaluation_state if key not in active_execution_ids]
            for key in stale_keys:
                del cls._evaluation_state[key]
                logger.debug(f"RotationEvaluator: cleaned up stale state for {key}")
