"""Orchestration service for fallback chain execution with account rotation."""

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..database import (
    get_fallback_chain,
    increment_account_executions,
)
from .budget_service import BudgetService
from .rate_limit_service import RateLimitService

logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    """Outcome of execute_with_fallback — discriminates the three non-success cases."""

    DISPATCHED = "dispatched"  # Execution started; execution_id is populated
    BUDGET_BLOCKED = "budget_blocked"  # Pre-execution budget check failed
    CHAIN_EXHAUSTED = "chain_exhausted"  # All fallback chain entries exhausted
    LAUNCH_FAILED = "launch_failed"  # Execution attempted but failed to launch


@dataclass
class ExecutionResult:
    """Result of execute_with_fallback with a discriminated status.

    Replaces Optional[str] so callers can distinguish why execution did not start.
    - DISPATCHED: execution_id is populated; execution was launched
    - BUDGET_BLOCKED: budget pre-check failed; detail contains spend / limit info
    - CHAIN_EXHAUSTED: all fallback chain entries were rate-limited or unavailable
    - LAUNCH_FAILED: run_trigger returned None (command not found, process error, etc.)
    """

    status: ExecutionStatus
    execution_id: Optional[str] = None
    detail: Optional[str] = None  # Human-readable context (e.g. budget error details)


class OrchestrationService:
    """Service that wraps ExecutionService with fallback chain and account rotation."""

    @classmethod
    def execute_with_fallback(
        cls,
        trigger: dict,
        message_text: str,
        event: dict = None,
        trigger_type: str = "webhook",
    ) -> ExecutionResult:
        """Execute a trigger using its fallback chain, rotating accounts on rate limits.

        1. Get fallback chain for the trigger
        2. If no chain, fall through to default ExecutionService.run_trigger (backward compatible)
        3. For each chain entry, pick best account and attempt execution
        4. On rate limit, mark account and try next chain entry
        5. On success/non-rate-limit failure, return ExecutionResult(DISPATCHED)
        6. If all chain entries exhausted, return ExecutionResult(CHAIN_EXHAUSTED)

        Returns an ExecutionResult; check .status to distinguish outcomes.
        """
        # Import here to avoid circular imports
        from .execution_service import ExecutionService

        chain = get_fallback_chain("trigger", trigger["id"])

        if not chain:
            # No fallback chain configured -- backward compatible direct execution
            execution_id = ExecutionService.run_trigger(trigger, message_text, event, trigger_type)
            if execution_id:
                return ExecutionResult(status=ExecutionStatus.DISPATCHED, execution_id=execution_id)
            return ExecutionResult(status=ExecutionStatus.LAUNCH_FAILED)

        logger.info(
            f"Executing trigger '{trigger['name']}' with fallback chain ({len(chain)} entries)"
        )

        # Track rate-limit cooldowns so we can schedule a retry if all accounts are exhausted
        rate_limited_cooldowns = []
        # Track backends skipped due to no available accounts for CHAIN_EXHAUSTED detail
        no_accounts_backends: list[str] = []

        # Pre-execution budget check
        budget_check = BudgetService.check_budget("trigger", trigger["id"])
        if not budget_check["allowed"]:
            limit_info = budget_check.get("limit") or {}
            period = limit_info.get("period", "monthly")
            hard_limit = limit_info.get("hard_limit_usd", "N/A")
            detail = (
                f"trigger '{trigger['name']}' (id={trigger['id']}): "
                f"{budget_check['reason']}; "
                f"spend=${budget_check.get('current_spend', 0):.4f}, "
                f"hard_limit=${hard_limit}, "
                f"period={period}"
            )
            logger.warning(f"Budget check blocked execution for {detail}")
            return ExecutionResult(status=ExecutionStatus.BUDGET_BLOCKED, detail=detail)

        if budget_check.get("reason") == "soft_limit_warning":
            logger.warning(
                f"Soft budget limit warning for trigger '{trigger['name']}': "
                f"spend ${budget_check.get('current_spend', 0):.2f}, "
                f"remaining ${budget_check.get('remaining_usd', 'N/A')}"
            )

        for chain_entry in chain:
            backend_type = chain_entry["backend_type"]
            specific_account_id = chain_entry.get("account_id")

            # Pick account
            if specific_account_id:
                # Preemptive scheduler eligibility check (rate limit prediction)
                from .agent_scheduler_service import AgentSchedulerService

                eligibility = AgentSchedulerService.check_eligibility(specific_account_id)
                if not eligibility["eligible"]:
                    logger.info(
                        f"Scheduler paused account {specific_account_id}: "
                        f"{eligibility.get('message', eligibility['reason'])}"
                    )
                    continue  # Try next chain entry

                # Specific account requested -- check if rate-limited
                if RateLimitService.is_rate_limited(specific_account_id):
                    logger.info(
                        f"Specific account {specific_account_id} is rate-limited, "
                        f"skipping chain entry for {backend_type}"
                    )
                    continue
                # Use the specific account -- get its details
                from ..database import get_account_rate_limit_state

                account_state = get_account_rate_limit_state(specific_account_id)
                if not account_state:
                    logger.warning(f"Account {specific_account_id} not found, skipping chain entry")
                    continue
                # Get full account info
                from ..database import get_accounts_for_backend_type

                accounts = get_accounts_for_backend_type(backend_type)
                account = next((a for a in accounts if a["id"] == specific_account_id), None)
                if not account:
                    logger.warning(
                        f"Account {specific_account_id} not found for backend {backend_type}"
                    )
                    continue
            else:
                # Auto-select best available account
                account = RateLimitService.pick_best_account(backend_type)
                if not account:
                    logger.info(
                        f"No available accounts for backend {backend_type}, "
                        f"trying next chain entry"
                    )
                    no_accounts_backends.append(backend_type)
                    continue

            # Build env overrides from account config
            env_overrides = cls._build_account_env(account)

            # Create modified trigger dict with the chain entry's backend_type
            modified_trigger = {**trigger, "backend_type": backend_type}

            logger.info(
                f"Attempting execution with backend={backend_type}, "
                f"account={account['id']} ({account.get('account_name', 'unknown')})"
            )

            # Mark account as running (queued -> running transition)
            try:
                from .agent_scheduler_service import AgentSchedulerService

                AgentSchedulerService.mark_running(account["id"])
            except (RuntimeError, AttributeError) as e:
                logger.error(
                    "Failed to mark account %s running: %s", account["id"], e, exc_info=True
                )
            except Exception:
                logger.exception("Unexpected error marking account %s running", account["id"])

            # Execute with lifecycle hooks (mark_completed in finally block)
            try:
                execution_id = ExecutionService.run_trigger(
                    modified_trigger,
                    message_text,
                    event,
                    trigger_type,
                    env_overrides=env_overrides,
                    account_id=account["id"],
                )
            finally:
                # Mark account as completed (running -> queued transition)
                # Must be in finally block so state is always cleaned up
                try:
                    from .agent_scheduler_service import AgentSchedulerService

                    AgentSchedulerService.mark_completed(account["id"])
                except (RuntimeError, AttributeError) as e:
                    logger.error(
                        "Failed to mark account %s completed: %s", account["id"], e, exc_info=True
                    )
                except Exception:
                    logger.exception("Unexpected error marking account %s completed", account["id"])

            # Check if execution was rate-limited
            cooldown = ExecutionService.was_rate_limited(execution_id)
            if cooldown is not None:
                logger.info(
                    f"Execution {execution_id} was rate-limited "
                    f"(cooldown={cooldown}s), marking account {account['id']}"
                )
                RateLimitService.mark_rate_limited(account["id"], cooldown)
                rate_limited_cooldowns.append(cooldown)
                continue  # Try next chain entry

            # Execution succeeded or failed for non-rate-limit reason
            if execution_id:
                increment_account_executions(account["id"])
                return ExecutionResult(status=ExecutionStatus.DISPATCHED, execution_id=execution_id)
            return ExecutionResult(status=ExecutionStatus.LAUNCH_FAILED)

        # All chain entries exhausted
        logger.warning(f"All fallback chain entries exhausted for trigger '{trigger['name']}'")

        # Build a human-readable detail for the caller
        exhausted_parts = []
        if no_accounts_backends:
            exhausted_parts.append(
                f"no available accounts for: {', '.join(sorted(set(no_accounts_backends)))}"
            )
        if rate_limited_cooldowns:
            exhausted_parts.append("some backends were rate-limited")
        chain_detail = (
            "; ".join(exhausted_parts) if exhausted_parts else "all chain entries were skipped"
        )

        # Schedule a retry after the shortest rate-limit cooldown expires
        if rate_limited_cooldowns:
            min_cooldown = min(rate_limited_cooldowns)
            ExecutionService.schedule_retry(
                trigger, message_text, event, trigger_type, min_cooldown
            )

        return ExecutionResult(status=ExecutionStatus.CHAIN_EXHAUSTED, detail=chain_detail)

    @staticmethod
    def validate_fallback_chain_entries(entries: list) -> Optional[str]:
        """Validate that all backend types and account IDs in fallback chain entries exist.

        Returns error message string if validation fails, None if all valid.
        """
        from ..database import get_connection

        with get_connection() as conn:
            for entry in entries:
                cursor = conn.execute(
                    "SELECT id FROM ai_backends WHERE type = ?", (entry.backend_type,)
                )
                backend_row = cursor.fetchone()
                if not backend_row:
                    return f"Backend type '{entry.backend_type}' not found"

                if entry.account_id is not None:
                    # Verify account exists AND belongs to the specified backend type
                    cursor = conn.execute(
                        "SELECT id FROM backend_accounts WHERE id = ? AND backend_id = ?",
                        (entry.account_id, backend_row[0]),
                    )
                    if not cursor.fetchone():
                        return (
                            f"Account ID {entry.account_id} not found or does not belong "
                            f"to backend type '{entry.backend_type}'"
                        )
        return None

    @classmethod
    def _build_account_env(cls, account: dict) -> dict:
        """Build environment variable overrides from account config.

        Sets:
        - ANTHROPIC_API_KEY from api_key_env lookup
        - CLAUDE_CONFIG_DIR / GEMINI_CLI_HOME from config_path

        Returns dict of env var overrides.
        """
        env = {}
        api_key_env = account.get("api_key_env")
        if api_key_env:
            # api_key_env is the NAME of the env var (e.g., "ANTHROPIC_API_KEY_2")
            key_value = os.environ.get(api_key_env, "")
            if key_value:
                # Map to the standard env var expected by the backend
                env["ANTHROPIC_API_KEY"] = key_value

        config_path = account.get("config_path")
        if config_path:
            backend_type = account.get("backend_type", "")
            config_env_map = {
                "claude": "CLAUDE_CONFIG_DIR",
                "gemini": "GEMINI_CLI_HOME",
            }
            env_var = config_env_map.get(backend_type)
            if env_var:
                env[env_var] = config_path

        return env
