"""Rotation service — core rotation decision engine for proactive account rotation.

Detects when running sessions approach rate limits, selects the best target account
via weighted scoring, gracefully terminates the current process (SIGTERM + SIGKILL
fallback), and starts a continuation execution on the target account.

Composes existing infrastructure: ProcessManager (process lifecycle), ExecutionLogService
(log capture), MonitoringService (utilization data), rotation_events CRUD (audit trail),
and ExecutionService (continuation execution).
"""

import logging
import os
import signal
import subprocess
import threading
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class RotationService:
    """Core rotation decision engine with weighted scoring and graceful process handoff.

    All methods are classmethods following the existing service pattern
    (AgentSchedulerService, MonitoringService). Thread-safe via _lock for in-memory state.
    """

    # In-memory state: {execution_id: {consecutive_polls, last_checked, ...}}
    _rotation_state: dict = {}
    _lock = threading.Lock()

    # Configuration constants
    MAX_ROTATIONS_PER_EXECUTION = 3  # Prevent infinite rotation loops
    ROTATION_UTILIZATION_THRESHOLD = 80.0  # Percentage threshold to trigger rotation
    SIGTERM_TIMEOUT = 5  # Seconds to wait after SIGTERM before SIGKILL
    DEFAULT_CONTEXT_LINES = 200  # Lines of output to include in continuation prompt

    @classmethod
    def should_rotate(cls, execution_id: str, account_id: int) -> dict:
        """Core decision function: should this execution be rotated?

        Returns {"should_rotate": bool, "reason": str, "utilization_pct": float}.

        Decision logic:
        - Returns False if execution already reached MAX_ROTATIONS_PER_EXECUTION.
        - Returns False if no monitoring data available (fail-safe: do not rotate
          on insufficient data).
        - Returns True when estimated utilization exceeds ROTATION_UTILIZATION_THRESHOLD
          AND ETA status is "projected" with minutes_remaining < safety margin.
        """
        from ..db.rotations import get_rotation_events_by_execution

        # Check rotation chain length limit
        existing_rotations = get_rotation_events_by_execution(execution_id)
        if len(existing_rotations) >= cls.MAX_ROTATIONS_PER_EXECUTION:
            logger.info(
                f"Rotation skipped for {execution_id}: max rotations "
                f"({cls.MAX_ROTATIONS_PER_EXECUTION}) reached"
            )
            return {
                "should_rotate": False,
                "reason": "max_rotations_reached",
                "utilization_pct": 0.0,
            }

        # Get monitoring status with ETA projections
        from ..database import get_monitoring_config
        from .monitoring_service import MonitoringService

        status = MonitoringService.get_monitoring_status()
        windows = status.get("windows", [])

        if not windows:
            logger.debug(f"Rotation check for {execution_id}: no monitoring windows available")
            return {
                "should_rotate": False,
                "reason": "no_monitoring_data",
                "utilization_pct": 0.0,
            }

        # Load safety margin from config
        config = get_monitoring_config()
        safety_margin_minutes = config.get("safety_margin_minutes", 5)

        # Find the most concerning window for this account
        account_windows = [w for w in windows if w.get("account_id") == account_id]
        if not account_windows:
            logger.debug(f"Rotation check for {execution_id}: no windows for account {account_id}")
            return {
                "should_rotate": False,
                "reason": "no_account_data",
                "utilization_pct": 0.0,
            }

        # Check each window for the account
        highest_utilization = 0.0
        should_rotate = False
        rotation_reason = "utilization_safe"

        for window in account_windows:
            pct = window.get("percentage", 0.0)
            eta = window.get("eta", {})
            eta_status = eta.get("status", "no_data")
            minutes_remaining = eta.get("minutes_remaining")

            if pct > highest_utilization:
                highest_utilization = pct

            # Rotation trigger: high utilization AND approaching limit
            if (
                pct >= cls.ROTATION_UTILIZATION_THRESHOLD
                and eta_status == "projected"
                and minutes_remaining is not None
                and minutes_remaining < safety_margin_minutes
            ):
                should_rotate = True
                rotation_reason = (
                    f"utilization {pct}% exceeds threshold, "
                    f"ETA {minutes_remaining:.1f}min < safety margin {safety_margin_minutes}min"
                )

        if should_rotate:
            logger.info(f"Rotation recommended for {execution_id}: {rotation_reason}")
        else:
            logger.debug(
                f"Rotation not needed for {execution_id}: "
                f"utilization {highest_utilization}%, reason={rotation_reason}"
            )

        return {
            "should_rotate": should_rotate,
            "reason": rotation_reason,
            "utilization_pct": highest_utilization,
        }

    @classmethod
    def score_accounts(cls, backend_type: str, current_account_id: int) -> list[dict]:
        """Score available accounts for rotation target selection.

        Uses weighted scoring: score = (0.6 * remaining_capacity) + (0.2 * same_backend)
                                       - (0.2 * shared_credential_penalty)

        Returns list of {"account": dict, "score": float} sorted by score DESC.
        """
        from ..database import get_accounts_for_backend_type
        from .agent_scheduler_service import AgentSchedulerService
        from .provider_usage_client import CredentialResolver
        from .rate_limit_service import RateLimitService

        accounts = get_accounts_for_backend_type(backend_type)
        now = datetime.now(timezone.utc)

        # Get current account's credential fingerprint for sharing detection
        current_account = next((a for a in accounts if a["id"] == current_account_id), None)
        current_fp = None
        if current_account:
            current_fp = CredentialResolver.get_token_fingerprint(current_account, backend_type)

        candidates = []
        for account in accounts:
            if account["id"] == current_account_id:
                continue  # Skip the account we're rotating FROM

            if RateLimitService.is_rate_limited(account["id"]):
                logger.debug(f"Score accounts: skipping rate-limited account {account['id']}")
                continue

            # Check scheduler eligibility (stopped accounts are excluded)
            eligibility = AgentSchedulerService.check_eligibility(account["id"])
            if not eligibility.get("eligible", True):
                logger.debug(f"Score accounts: skipping scheduler-stopped account {account['id']}")
                continue

            # Factor 1: Remaining capacity (0.0 to 1.0)
            remaining_pct = cls._get_remaining_capacity_pct(account["id"], now)

            # Factor 2: Same-backend preference (always 1.0 since all candidates
            # are same backend_type)
            same_backend = 1.0

            # Factor 3: Credential sharing penalty
            fp = CredentialResolver.get_token_fingerprint(account, backend_type)
            shared_penalty = 1.0 if (fp and current_fp and fp == current_fp) else 0.0

            score = (0.6 * remaining_pct) + (0.2 * same_backend) - (0.2 * shared_penalty)
            candidates.append({"account": account, "score": score})

        candidates.sort(key=lambda x: x["score"], reverse=True)

        if candidates:
            logger.info(
                f"Score accounts: {len(candidates)} candidates for {backend_type}, "
                f"best score={candidates[0]['score']:.2f}"
            )
        else:
            logger.warning(f"Score accounts: no candidates available for {backend_type}")

        return candidates

    @classmethod
    def build_continuation_prompt(
        cls,
        execution_id: str,
        original_prompt: str,
        context_lines: int = 200,
    ) -> str:
        """Build a continuation prompt with last N lines of context.

        MUST be called BEFORE process termination, as log buffers are cleared
        after process exits.
        """
        from .execution_log_service import ExecutionLogService

        # Capture log lines BEFORE termination
        stdout_log = ExecutionLogService.get_stdout_log(execution_id)
        lines = stdout_log.split("\n") if stdout_log else []
        last_n = lines[-context_lines:] if len(lines) > context_lines else lines
        context = "\n".join(last_n)

        return (
            "CONTINUATION: This is a continuation of a previous session that was "
            "rotated due to rate limit management. Continue the task from where "
            "the previous session left off.\n\n"
            f"## Original Task\n{original_prompt}\n\n"
            f"## Previous Session Output (last {len(last_n)} lines)\n"
            f"```\n{context}\n```\n\n"
            "## Instructions\n"
            "Review the previous session output above and continue the task. "
            "Do not repeat work that was already completed."
        )

    @classmethod
    def execute_rotation(
        cls,
        execution_id: str,
        trigger: dict,
        message_text: str,
        event: dict = None,
        trigger_type: str = "webhook",
    ) -> Optional[str]:
        """Full rotation flow: evaluate, score, terminate, restart.

        Returns continuation_execution_id on success, None otherwise.
        """
        from ..db.rotations import add_rotation_event, update_rotation_event
        from .execution_log_service import ExecutionLogService

        rotation_event_id = None

        try:
            # Step 1: Get current execution's account_id
            execution = ExecutionLogService.get_execution(execution_id)
            if not execution:
                logger.warning(f"Rotation: execution {execution_id} not found")
                return None

            account_id = execution.get("account_id")
            if not account_id:
                logger.warning(f"Rotation: no account_id for execution {execution_id}")
                return None

            # Step 2: Check if we should rotate
            decision = cls.should_rotate(execution_id, account_id)
            if not decision["should_rotate"]:
                logger.debug(f"Rotation: not needed for {execution_id} ({decision['reason']})")
                return None

            utilization_pct = decision["utilization_pct"]
            backend_type = execution.get("backend_type", "claude")

            # Step 3: Score and select target account
            candidates = cls.score_accounts(backend_type, account_id)
            if not candidates:
                # No candidates available -- record as skipped
                rotation_event_id = add_rotation_event(
                    execution_id=execution_id,
                    from_account_id=account_id,
                    to_account_id=None,
                    reason="no_candidates_available",
                    urgency="normal",
                )
                if rotation_event_id:
                    update_rotation_event(
                        rotation_event_id,
                        rotation_status="skipped",
                        utilization_at_rotation=utilization_pct,
                    )
                logger.warning(f"Rotation: no candidates for {execution_id}, skipping")
                return None

            target = candidates[0]
            target_account = target["account"]
            target_account_id = target_account["id"]

            # Step 4: Capture continuation prompt BEFORE termination
            original_prompt = execution.get("prompt", message_text)
            continuation_prompt = cls.build_continuation_prompt(
                execution_id, original_prompt, cls.DEFAULT_CONTEXT_LINES
            )

            # Step 5: Record rotation event as pending
            rotation_event_id = add_rotation_event(
                execution_id=execution_id,
                from_account_id=account_id,
                to_account_id=target_account_id,
                reason=decision["reason"],
                urgency="normal",
            )

            # Step 6: Terminate current process
            terminated = cls._terminate_process(execution_id, timeout=cls.SIGTERM_TIMEOUT)
            if not terminated:
                logger.warning(f"Rotation: could not terminate process for {execution_id}")

            # Step 7: Cleanup process tracking and finalize execution
            from .process_manager import ProcessManager

            ProcessManager.cleanup(execution_id)
            ExecutionLogService.finish_execution(execution_id, status="rotated")

            # Step 8: Build env overrides from target account
            from .orchestration_service import OrchestrationService

            env_overrides = OrchestrationService._build_account_env(target_account)

            # Step 9: Start continuation execution
            from .execution_service import ExecutionService

            modified_trigger = {**trigger, "backend_type": backend_type}
            continuation_execution_id = ExecutionService.run_trigger(
                modified_trigger,
                continuation_prompt,
                event,
                trigger_type,
                env_overrides=env_overrides,
                account_id=target_account_id,
            )

            # Step 10: Update rotation event with completion
            if rotation_event_id:
                completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                update_rotation_event(
                    rotation_event_id,
                    rotation_status="completed",
                    utilization_at_rotation=utilization_pct,
                    continuation_execution_id=continuation_execution_id,
                    completed_at=completed_at,
                )

            logger.info(
                f"Rotation completed: {execution_id} -> {continuation_execution_id} "
                f"(account {account_id} -> {target_account_id})"
            )

            # Step 11: Return continuation execution ID
            return continuation_execution_id

        except Exception as e:
            logger.error(f"Rotation failed for {execution_id}: {e}")
            # Update rotation event to failed status
            if rotation_event_id:
                try:
                    update_rotation_event(
                        rotation_event_id,
                        rotation_status="failed",
                    )
                except Exception as update_err:
                    logger.error(f"Failed to update rotation event status: {update_err}")
            return None

    @classmethod
    def _terminate_process(cls, execution_id: str, timeout: int = 5) -> bool:
        """Gracefully terminate a running process. SIGTERM first, SIGKILL fallback.

        Returns True if process was terminated.
        """
        from .process_manager import ProcessManager

        with ProcessManager._lock:
            info = ProcessManager._processes.get(execution_id)
        if not info:
            logger.debug(f"Terminate: no process found for {execution_id}")
            return False

        # Send SIGTERM to process group
        try:
            os.killpg(info.pgid, signal.SIGTERM)
            logger.info(f"Sent SIGTERM to pgid {info.pgid} for execution {execution_id}")
        except ProcessLookupError:
            logger.info(f"Process group {info.pgid} already dead for {execution_id}")
            return True  # Already dead

        # Wait for graceful shutdown
        try:
            info.process.wait(timeout=timeout)
            logger.info(f"Process {execution_id} exited after SIGTERM")
            return True
        except subprocess.TimeoutExpired:
            pass

        # SIGKILL fallback
        try:
            os.killpg(info.pgid, signal.SIGKILL)
            logger.warning(f"Sent SIGKILL to pgid {info.pgid} for execution {execution_id}")
            info.process.wait(timeout=3)
            return True
        except (ProcessLookupError, subprocess.TimeoutExpired):
            return True

    @classmethod
    def get_rotation_history(cls, execution_id: str = None, limit: int = 50) -> list[dict]:
        """Audit trail query for rotation events.

        If execution_id provided, returns events for that execution.
        Otherwise returns all recent events.
        """
        from ..db.rotations import get_all_rotation_events, get_rotation_events_by_execution

        if execution_id:
            return get_rotation_events_by_execution(execution_id)
        return get_all_rotation_events(limit)

    @classmethod
    def _get_remaining_capacity_pct(cls, account_id: int, now: datetime) -> float:
        """Helper for score_accounts: get remaining capacity as fraction (0.0 to 1.0).

        Uses the latest monitoring snapshot for the account.
        Returns 0.5 (neutral default) if no snapshot data available.
        """
        from .monitoring_service import MonitoringService

        status = MonitoringService.get_monitoring_status()
        windows = status.get("windows", [])

        account_windows = [w for w in windows if w.get("account_id") == account_id]
        if not account_windows:
            return 0.5  # Neutral default

        # Use the highest utilization window (most conservative)
        max_pct = max(w.get("percentage", 0.0) for w in account_windows)
        return (100.0 - max_pct) / 100.0

    @classmethod
    def reset_rotation_state(cls, execution_id: str):
        """Cleanup method: remove execution from in-memory rotation state.

        Called after execution completes (regardless of rotation).
        """
        with cls._lock:
            removed = cls._rotation_state.pop(execution_id, None)
        if removed:
            logger.debug(f"Reset rotation state for {execution_id}")
