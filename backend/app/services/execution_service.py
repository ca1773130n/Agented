"""Trigger execution service with database-only status tracking and real-time logging."""

import datetime
import hashlib
import hmac
import json
import logging
import os
import random
import re
import shutil
import signal
import subprocess
import threading
from typing import Dict, List, Optional

from app.config import PROJECT_ROOT

from ..database import (
    PREDEFINED_TRIGGER_ID,
    delete_pending_retry,
    get_all_pending_retries,
    get_latest_execution_for_trigger,
    get_paths_for_trigger_detailed,
    get_triggers_by_trigger_source,
    get_webhook_triggers,
    upsert_pending_retry,
)
from ..db.webhook_dedup import check_and_insert_dedup_key
from ..utils.json_path import get_nested_value
from .audit_log_service import AuditLogService
from .budget_service import BudgetService
from .execution_log_service import ExecutionLogService
from .github_service import GitHubService
from .process_manager import ProcessManager
from .rate_limit_service import RateLimitService

logger = logging.getLogger(__name__)


def _trace_logger(execution_id: str) -> logging.LoggerAdapter:
    """Return a LoggerAdapter that tags every log record with the execution trace ID.

    Usage::

        tlog = _trace_logger(execution_id)
        tlog.info("subprocess started: %s", cmd)

    To surface the trace_id in log output, include ``%(trace_id)s`` in the
    root logging format, e.g.::

        logging.basicConfig(format="[%(trace_id)s] %(levelname)s %(message)s")

    The adapter always provides ``trace_id`` via ``extra``, so it is safe even
    when the root formatter does not reference it.
    """
    return logging.LoggerAdapter(logger, {"trace_id": execution_id})


TRIGGER_LOG_DIR = os.path.join(PROJECT_ROOT, ".claude/skills/weekly-security-audit/reports")

# Validate write access to TRIGGER_LOG_DIR at import time so misconfiguration is
# surfaced immediately rather than silently swallowed at first trigger save.
try:
    os.makedirs(TRIGGER_LOG_DIR, exist_ok=True)
    if not os.access(TRIGGER_LOG_DIR, os.W_OK):
        logger.warning(
            "TRIGGER_LOG_DIR is not writable: %s — trigger reports will fail to save",
            TRIGGER_LOG_DIR,
        )
except Exception as _dir_err:
    logger.warning(
        "Could not create TRIGGER_LOG_DIR %s: %s — trigger reports will fail to save",
        TRIGGER_LOG_DIR,
        _dir_err,
    )


class ExecutionState:
    """String constants for execution status values.

    Using a class of constants (rather than scattered string literals) means a
    typo in a status name is caught at import time instead of silently producing
    an invalid state in the database.
    """

    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    IDLE = "idle"


class ExecutionService:
    """Service for trigger execution and status tracking via database."""

    # Webhook deduplication TTL in seconds (DB-backed via webhook_dedup_keys table)
    WEBHOOK_DEDUP_WINDOW = 10

    # Thread-safe dict tracking rate limit detections: {execution_id: cooldown_seconds}
    _rate_limit_detected: Dict[str, int] = {}
    # _rate_limit_lock guards _rate_limit_detected, _pending_retries, _retry_timers, and _retry_counts.
    # Acquire before any read or write to those dicts.
    _rate_limit_lock = threading.Lock()

    # Seconds within which identical (trigger, payload) pairs are suppressed (DB-backed)
    WEBHOOK_DEDUP_WINDOW = 10

    # Pending rate-limit retries: {trigger_id: {"retry_at": str, "cooldown_seconds": int, ...}}
    _pending_retries: Dict[str, dict] = {}
    # Active retry timers: {trigger_id: threading.Timer}
    _retry_timers: Dict[str, threading.Timer] = {}
    # Per-trigger consecutive retry attempt counter: {trigger_id: int}
    _retry_counts: Dict[str, int] = {}
    # Maximum consecutive rate-limit retries before giving up
    MAX_RETRY_ATTEMPTS = 5
    # Cap on backoff delay (seconds) to avoid extremely long waits
    MAX_RETRY_DELAY = 3600

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
        trigger_id = trigger["id"]

        # Cancel existing timer for this trigger
        with cls._rate_limit_lock:
            existing = cls._retry_timers.pop(trigger_id, None)
            attempt_count = cls._retry_counts.get(trigger_id, 0) + 1
            cls._retry_counts[trigger_id] = attempt_count
        if existing:
            existing.cancel()

        if attempt_count > cls.MAX_RETRY_ATTEMPTS:
            logger.error(
                "Rate-limit retry for trigger %s has exceeded max attempts (%d/%d) — "
                "giving up to prevent infinite retry loop",
                trigger_id,
                attempt_count,
                cls.MAX_RETRY_ATTEMPTS,
            )
            AuditLogService.log(
                action="retry.exhausted",
                entity_type="trigger",
                entity_id=trigger_id,
                outcome="terminal_failure",
                details={
                    "attempt_count": attempt_count,
                    "max_attempts": cls.MAX_RETRY_ATTEMPTS,
                    "trigger_type": trigger_type,
                },
            )
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
                    f"(max={cls.MAX_RETRY_ATTEMPTS}). No further retries will be scheduled.",
                )
                ExecutionLogService.finish_execution(
                    execution_id=terminal_exec_id,
                    status=ExecutionState.FAILED,
                    exit_code=-1,
                    error_message=(
                        f"Rate-limit retry exhausted: {attempt_count}/{cls.MAX_RETRY_ATTEMPTS} attempts"
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

        def _retry():
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
        backoff_delay = (
            min(cooldown_seconds * (2 ** (attempt_count - 1)), cls.MAX_RETRY_DELAY) + jitter
        )

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
            cls.MAX_RETRY_ATTEMPTS,
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
                ):
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

    @classmethod
    def get_status(cls, trigger_id: str) -> dict:
        """Get execution status for a trigger from database."""
        execution = get_latest_execution_for_trigger(trigger_id)
        if not execution:
            return {"status": ExecutionState.IDLE}
        return {
            "status": execution.get("status", ExecutionState.IDLE),
            "started_at": execution.get("started_at"),
            "finished_at": execution.get("finished_at"),
            "error_message": execution.get("error_message"),
            "execution_id": execution.get("execution_id"),
        }

    @staticmethod
    def save_trigger_event(trigger: dict, event: dict) -> str:
        """Save the original trigger event for audit tracking. Returns event trigger_id."""
        os.makedirs(TRIGGER_LOG_DIR, exist_ok=True)

        trigger_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        trigger_data = {
            "trigger_id": trigger.get("id"),
            "timestamp": datetime.datetime.now().isoformat(),
            "trigger_name": trigger.get("name"),
            "trigger_source": trigger.get("trigger_source"),
            "original_event": event,
        }

        trigger_file = os.path.join(TRIGGER_LOG_DIR, f"trigger_{trigger_id}.json")
        try:
            with open(trigger_file, "w", encoding="utf-8") as f:
                json.dump(trigger_data, f, indent=2, ensure_ascii=False)
            logger.debug("Saved trigger event: %s", trigger_file)
        except Exception as e:
            logger.warning("Failed to save trigger event: %s", e, exc_info=True)

        return trigger_id

    @staticmethod
    def save_threat_report(trigger_id: str, message_text: str) -> str:
        """Save webhook message as threat report file. Returns file path."""
        os.makedirs(TRIGGER_LOG_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"threat_report_{trigger_id}_{timestamp}.txt"
        filepath = os.path.join(TRIGGER_LOG_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(message_text)

        logger.info("Saved threat report: %s", filepath)
        return filepath

    # Execution timeout bounds (seconds)
    TIMEOUT_MIN = 60  # 1 minute minimum
    TIMEOUT_MAX = 3600  # 1 hour maximum
    TIMEOUT_DEFAULT = 600  # 10 minutes default

    @staticmethod
    def build_command(
        backend: str,
        prompt: str,
        allowed_paths: list = None,
        model: str = None,
        codex_settings: dict = None,
        allowed_tools: str = None,
    ) -> list:
        """Build the CLI command for the specified backend."""
        if backend == "opencode":
            cmd = ["opencode", "run", "--format", "json", prompt]
            if model:
                cmd.extend(["--model", model])
            return cmd
        elif backend == "gemini":
            cmd = ["gemini", "-p", prompt, "--output-format", "json"]
            if model:
                cmd.extend(["--model", model])
            if allowed_paths:
                for path in allowed_paths:
                    cmd.extend(["--include-directories", path])
            return cmd
        elif backend == "codex":
            cmd = ["codex", "exec", "--json", "--full-auto"]
            if model:
                cmd.extend(["--model", model])
            if codex_settings:
                reasoning = codex_settings.get("reasoning_level")
                if reasoning and reasoning in ("low", "medium", "high"):
                    cmd.extend(["--reasoning-effort", reasoning])
            cmd.append(prompt)
            return cmd
        else:
            # claude (default)
            tools = allowed_tools or "Read,Glob,Grep,Bash"
            cmd = [
                "claude",
                "-p",
                prompt,
                "--verbose",
                "--output-format",
                "json",
                "--allowedTools",
                tools,
            ]
            if model:
                cmd.extend(["--model", model])
            if allowed_paths:
                for path in allowed_paths:
                    cmd.extend(["--add-dir", path])
            return cmd

    @classmethod
    def _budget_monitor(
        cls,
        execution_id: str,
        trigger_id: str,
        entity_type: str,
        entity_id: str,
        process: "subprocess.Popen",
        interval_seconds: int = 30,
    ) -> None:
        """Periodically check budget during execution and kill process if hard limit exceeded."""
        import time as _time

        while process.poll() is None:
            _time.sleep(interval_seconds)
            if process.poll() is not None:
                break
            try:
                budget_check = BudgetService.check_budget(entity_type, entity_id)
                if not budget_check["allowed"]:
                    reason = budget_check.get("reason", "hard limit reached")
                    logger.warning(
                        "Budget hard limit exceeded during execution %s (%s/%s) — terminating process. %s",
                        execution_id,
                        entity_type,
                        entity_id,
                        reason,
                    )
                    try:
                        import os as _os

                        _os.killpg(_os.getpgid(process.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except Exception as kill_err:
                        logger.error(
                            "Failed to kill over-budget process for execution %s: %s",
                            execution_id,
                            kill_err,
                            exc_info=True,
                        )
                    ExecutionLogService.append_log(
                        execution_id,
                        "stderr",
                        f"[BUDGET] Execution terminated: {reason}",
                    )
                    AuditLogService.log(
                        action="execution.budget_exceeded",
                        entity_type=entity_type,
                        entity_id=entity_id,
                        outcome="killed",
                        details={"execution_id": execution_id, "reason": reason},
                    )
                    break
            except Exception as monitor_err:
                logger.debug("Budget monitor check failed for %s: %s", execution_id, monitor_err)

    @classmethod
    def _stream_pipe(cls, execution_id: str, stream_name: str, pipe, backend_type: str = None):
        """Read from a pipe line by line and stream to log service.

        When stream_name is 'stderr' and backend_type is provided, checks each line
        for rate limit patterns and flags the execution if detected.
        """
        try:
            for line in iter(pipe.readline, ""):
                if line:
                    content = line.rstrip("\n\r")
                    ExecutionLogService.append_log(execution_id, stream_name, content)
                    logger.debug("[%s] %s", stream_name, content)

                    # Check for rate limit patterns in stderr
                    if stream_name == "stderr" and backend_type:
                        cooldown = RateLimitService.check_stderr_line(content, backend_type)
                        if cooldown is not None:
                            with cls._rate_limit_lock:
                                cls._rate_limit_detected[execution_id] = cooldown
                            logger.warning(
                                "Rate limit detected for execution %s, cooldown=%ds",
                                execution_id,
                                cooldown,
                            )
                            AuditLogService.log(
                                action="rate_limit.detected",
                                entity_type="execution",
                                entity_id=execution_id,
                                outcome="rate_limited",
                                details={
                                    "backend_type": backend_type,
                                    "cooldown_seconds": cooldown,
                                },
                            )
        except (OSError, ValueError) as e:
            logger.error(
                "Error reading %s stream for execution %s: %s",
                stream_name,
                execution_id,
                e,
                exc_info=True,
            )
        except Exception:
            logger.exception("Unexpected error reading %s stream for execution %s", stream_name, execution_id)
        finally:
            pipe.close()

    @classmethod
    def run_trigger(
        cls,
        trigger: dict,
        message_text: str,
        event: dict = None,
        trigger_type: str = "webhook",
        env_overrides: dict = None,
        account_id: int = None,
        working_directory: str = None,
    ) -> Optional[str]:
        """Execute a trigger's prompt with real-time log streaming. Returns execution_id."""
        trigger_id = trigger["id"]
        execution_id = None
        cloned_dirs = []  # temp dirs to clean up
        github_repo_map = {}  # clone_dir -> repo_url (for auto-resolve PR flow)

        try:
            # Get detailed path info (includes path_type and github_repo_url)
            path_entries = get_paths_for_trigger_detailed(trigger_id)

            effective_paths = []
            for entry in path_entries:
                if entry["path_type"] == "github":
                    repo_url = entry["github_repo_url"]
                    logger.info("Cloning GitHub repo: %s", repo_url)
                    clone_dir = GitHubService.clone_repo(repo_url)
                    cloned_dirs.append(clone_dir)
                    effective_paths.append(clone_dir)
                    github_repo_map[clone_dir] = repo_url
                else:
                    effective_paths.append(entry["local_project_path"])

            paths_str = ", ".join(effective_paths) if effective_paths else "no paths configured"

            # Build prompt from template
            prompt = trigger["prompt_template"]
            prompt = prompt.replace("{trigger_id}", trigger_id)
            prompt = prompt.replace("{bot_id}", trigger_id)  # Legacy placeholder support
            prompt = prompt.replace("{paths}", paths_str)
            prompt = prompt.replace("{message}", message_text)

            # Add trigger context if available
            if event:
                # Handle GitHub PR placeholders
                if event.get("type") == "github_pr":
                    prompt = prompt.replace("{pr_url}", event.get("pr_url", ""))
                    prompt = prompt.replace("{pr_number}", str(event.get("pr_number", "")))
                    prompt = prompt.replace("{pr_title}", event.get("pr_title", ""))
                    prompt = prompt.replace("{pr_author}", event.get("pr_author", ""))
                    prompt = prompt.replace("{repo_url}", event.get("repo_url", ""))
                    prompt = prompt.replace("{repo_full_name}", event.get("repo_full_name", ""))

            # Warn about any unresolved {placeholder} patterns remaining in the prompt
            _KNOWN_PLACEHOLDERS = {
                "trigger_id",
                "bot_id",
                "paths",
                "message",
                "pr_url",
                "pr_number",
                "pr_title",
                "pr_author",
                "repo_url",
                "repo_full_name",
            }
            remaining = re.findall(r"\{(\w+)\}", prompt)
            unknown = [p for p in remaining if p not in _KNOWN_PLACEHOLDERS]
            if unknown:
                logger.warning(
                    "Prompt template for trigger '%s' contains unresolved placeholders: %s",
                    trigger.get("name", trigger_id),
                    unknown,
                )

            # Prepend skill_command if configured and not already in prompt
            skill_command = trigger.get("skill_command", "")
            if skill_command and not prompt.lstrip().startswith(skill_command):
                prompt = f"{skill_command} {prompt}"

            # For security audit skill, save message as threat report and prepend path
            if "/weekly-security-audit" in prompt:
                threat_report_path = cls.save_threat_report(trigger_id, message_text)
                prompt = prompt.replace(
                    "/weekly-security-audit", f"/weekly-security-audit {threat_report_path}"
                )

            backend = trigger["backend_type"]
            model = trigger.get("model")
            allowed_tools = trigger.get("allowed_tools")
            cmd = cls.build_command(
                backend, prompt, effective_paths, model, allowed_tools=allowed_tools
            )

            # Wrap with stdbuf to force line-buffered output for real-time streaming
            # -oL = line buffer stdout, -eL = line buffer stderr
            # stdbuf is only available on Linux (GNU coreutils); skip on macOS/Windows
            if shutil.which("stdbuf"):
                cmd = ["stdbuf", "-oL", "-eL"] + cmd

            cmd_str = " ".join(cmd)

            effective_cwd = working_directory or PROJECT_ROOT

            # Snapshot trigger config for audit trail
            trigger_config_snapshot = json.dumps(trigger, default=str)

            # Start execution logging — execution_id serves as the trace ID for
            # all subsequent log statements in this execution's pipeline.
            execution_id = ExecutionLogService.start_execution(
                trigger_id=trigger_id,
                trigger_type=trigger_type,
                prompt=prompt,
                backend_type=backend,
                command=cmd_str,
                trigger_config_snapshot=trigger_config_snapshot,
                account_id=account_id,
            )
            # Trace logger — prefixes all subsequent log lines with the execution ID
            # so that trigger receipt → subprocess output → completion can be correlated.
            tlog = _trace_logger(execution_id)
            tlog.info(
                "Execution started: trigger='%s' backend=%s cwd=%s cmd=%s...",
                trigger["name"],
                backend,
                effective_cwd,
                cmd_str[:200],
            )

            AuditLogService.log(
                action="execution.start",
                entity_type="trigger",
                entity_id=trigger_id,
                outcome="started",
                details={
                    "execution_id": execution_id,
                    "trigger_type": trigger_type,
                    "backend_type": backend,
                    "account_id": account_id,
                },
            )

            # Pre-execution budget check (wrapped in try/except -- never crash execution flow)
            try:
                budget_check = BudgetService.check_budget("trigger", trigger_id)
                if not budget_check["allowed"]:
                    limit_info = budget_check.get("limit") or {}
                    period = limit_info.get("period", "monthly")
                    hard_limit = limit_info.get("hard_limit_usd", "N/A")
                    budget_detail = (
                        f"{budget_check.get('reason', 'hard limit reached')}; "
                        f"spend=${budget_check.get('current_spend', 0):.4f}, "
                        f"hard_limit=${hard_limit}, "
                        f"period={period}"
                    )
                    tlog.warning(
                        "Budget check blocked execution for trigger '%s': %s",
                        trigger.get("name", trigger_id),
                        budget_detail,
                    )
                    ExecutionLogService.append_log(
                        execution_id,
                        "stderr",
                        f"Execution aborted: budget limit exceeded. {budget_detail}",
                    )
                    ExecutionLogService.finish_execution(
                        execution_id=execution_id,
                        status=ExecutionState.FAILED,
                        exit_code=-1,
                        error_message=f"Budget limit exceeded: {budget_detail}",
                    )
                    return execution_id
            except Exception as e:
                tlog.error(
                    "Budget pre-check failed for trigger '%s': %s",
                    trigger.get("name", trigger_id),
                    e,
                    exc_info=True,
                )

            # Build process environment with optional overrides
            proc_env = {**os.environ, **env_overrides} if env_overrides else None

            # Use Popen for streaming output (start_new_session for process group management)
            process = subprocess.Popen(
                cmd,
                cwd=effective_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                start_new_session=True,  # Process group for clean cleanup
                env=proc_env,
            )

            # Register with ProcessManager for cancellation and shutdown tracking
            ProcessManager.register(execution_id, process, trigger_id)

            # Start threads to read stdout and stderr
            stdout_thread = threading.Thread(
                target=cls._stream_pipe, args=(execution_id, "stdout", process.stdout), daemon=True
            )
            stderr_thread = threading.Thread(
                target=cls._stream_pipe,
                args=(execution_id, "stderr", process.stderr, backend),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            # Start budget monitor thread — kills process if hard limit is exceeded mid-run
            entity_type = trigger.get("_entity_type", "trigger")
            entity_id = trigger.get("_entity_id", trigger_id)
            budget_monitor_thread = threading.Thread(
                target=cls._budget_monitor,
                args=(execution_id, trigger_id, entity_type, entity_id, process),
                daemon=True,
            )
            budget_monitor_thread.start()

            # Use per-trigger timeout if configured, clamped to [TIMEOUT_MIN, TIMEOUT_MAX]
            raw_timeout = trigger.get("timeout_seconds") or cls.TIMEOUT_DEFAULT
            effective_timeout = max(cls.TIMEOUT_MIN, min(cls.TIMEOUT_MAX, int(raw_timeout)))
            timeout_label = (
                f"{effective_timeout // 60} minutes"
                if effective_timeout >= 60
                else f"{effective_timeout} seconds"
            )

            # Wait for process with timeout
            try:
                exit_code = process.wait(timeout=effective_timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except OSError as e:
                    tlog.debug("Process already exited during timeout cleanup: %s", e)
                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)
                if stdout_thread.is_alive():
                    tlog.warning("stdout reader thread still alive after kill")
                if stderr_thread.is_alive():
                    tlog.warning("stderr reader thread still alive after kill")
                tlog.warning("Trigger '%s' timed out after %s", trigger["name"], timeout_label)
                ExecutionLogService.append_log(
                    execution_id,
                    "stderr",
                    f"[TIMEOUT] Trigger '{trigger['name']}' timed out after {timeout_label}",
                )
                ExecutionLogService.finish_execution(
                    execution_id=execution_id,
                    status=ExecutionState.TIMEOUT,
                    error_message=f"Command timed out after {timeout_label}",
                )
                AuditLogService.log(
                    action="execution.finish",
                    entity_type="trigger",
                    entity_id=trigger_id,
                    outcome="timeout",
                    details={"execution_id": execution_id},
                )
                return execution_id

            # Wait for pipe readers to finish
            stdout_thread.join(timeout=10)
            stderr_thread.join(timeout=10)
            if stdout_thread.is_alive():
                tlog.error("stdout reader thread still alive after process exit — output may be incomplete")
                ExecutionLogService.append_log(
                    execution_id,
                    "stderr",
                    "[WARNING] stdout reader did not exit cleanly — output may be incomplete",
                )
            if stderr_thread.is_alive():
                tlog.error("stderr reader thread still alive after process exit — output may be incomplete")
                ExecutionLogService.append_log(
                    execution_id,
                    "stderr",
                    "[WARNING] stderr reader did not exit cleanly — output may be incomplete",
                )

            tlog.info("%s exit code: %d", backend, exit_code)
            ExecutionLogService.append_log(
                execution_id, "stderr", f"[EXIT] {backend} exit code: {exit_code}"
            )

            # Check if this execution was cancelled via the cancel endpoint
            if ProcessManager.is_cancelled(execution_id):
                ExecutionLogService.finish_execution(
                    execution_id=execution_id,
                    status=ExecutionState.CANCELLED,
                    exit_code=exit_code,
                    error_message="Cancelled by user",
                )
                AuditLogService.log(
                    action="execution.finish",
                    entity_type="trigger",
                    entity_id=trigger_id,
                    outcome="cancelled",
                    details={"execution_id": execution_id, "exit_code": exit_code},
                )
            elif exit_code == 0:
                # Auto-resolve + PR flow for security trigger with GitHub repos
                if (
                    trigger.get("auto_resolve")
                    and trigger_id == PREDEFINED_TRIGGER_ID
                    and github_repo_map
                ):
                    # Get scan output from execution logs
                    scan_output = ExecutionLogService.get_stdout_log(execution_id)
                    cls._auto_resolve_and_pr(trigger, github_repo_map, scan_output)
                ExecutionLogService.finish_execution(
                    execution_id=execution_id, status=ExecutionState.SUCCESS, exit_code=exit_code
                )
                AuditLogService.log(
                    action="execution.finish",
                    entity_type="trigger",
                    entity_id=trigger_id,
                    outcome="success",
                    details={"execution_id": execution_id, "exit_code": exit_code},
                )

                # Extract and record token usage after successful execution
                try:
                    stdout_log = ExecutionLogService.get_stdout_log(execution_id)
                    usage_data = BudgetService.extract_token_usage(stdout_log, backend)
                    if usage_data:
                        entity_type = trigger.get("_entity_type", "trigger")
                        entity_id = trigger.get("_entity_id", trigger_id)
                        BudgetService.record_usage(
                            execution_id=execution_id,
                            entity_type=entity_type,
                            entity_id=entity_id,
                            backend_type=backend,
                            account_id=account_id,
                            usage_data=usage_data,
                        )
                except (TypeError, ValueError) as e:
                    tlog.error("Failed to record token usage: %s", e, exc_info=True)
                except Exception:
                    tlog.exception("Unexpected error recording token usage")
            else:
                error_msg = f"Exit code: {exit_code}"
                ExecutionLogService.finish_execution(
                    execution_id=execution_id,
                    status=ExecutionState.FAILED,
                    exit_code=exit_code,
                    error_message=error_msg,
                )
                AuditLogService.log(
                    action="execution.finish",
                    entity_type="trigger",
                    entity_id=trigger_id,
                    outcome="failed",
                    details={
                        "execution_id": execution_id,
                        "exit_code": exit_code,
                        "error": error_msg,
                    },
                )

        except FileNotFoundError:
            backend = trigger.get("backend_type", "claude")
            error_msg = f"{backend} command not found"
            logger.error("%s. Is %s CLI installed?", error_msg, backend)
            if execution_id:
                ExecutionLogService.finish_execution(
                    execution_id=execution_id, status=ExecutionState.FAILED, error_message=error_msg
                )
        except Exception as e:
            error_msg = str(e)
            logger.exception("Error running trigger '%s'", trigger["name"])
            if execution_id:
                ExecutionLogService.finish_execution(
                    execution_id=execution_id, status=ExecutionState.FAILED, error_message=error_msg
                )
        finally:
            # Clean up all cloned directories (each wrapped independently to ensure all are attempted)
            for d in cloned_dirs:
                try:
                    GitHubService.cleanup_clone(d)
                except OSError as e:
                    logger.error(
                        "Failed to clean up cloned directory %s: %s", d, e, exc_info=True
                    )
                except Exception:
                    logger.exception("Unexpected error cleaning up cloned directory: %s", d)
            # Remove from ProcessManager tracking
            if execution_id:
                ProcessManager.cleanup(execution_id)

        return execution_id

    @classmethod
    def _auto_resolve_and_pr(
        cls, trigger: dict, github_repo_map: dict, scan_output: str
    ) -> List[str]:
        """Resolve issues in GitHub repos and create PRs. Returns list of PR URLs."""
        pr_urls = []

        for clone_dir, repo_url in github_repo_map.items():
            try:
                branch_name = GitHubService.generate_branch_name()

                # Create a new branch
                if not GitHubService.create_branch(clone_dir, branch_name):
                    logger.warning("Skipping PR for %s: branch creation failed", repo_url)
                    continue

                # Run resolve command with Edit/Write permissions
                resolve_prompt = (
                    "IMPORTANT: You must ONLY fix the specific security vulnerabilities "
                    "listed in the audit results below. Do NOT make any other changes "
                    "or general security improvements.\n\n"
                    "## Audit Results\n\n"
                    f"{scan_output}\n\n"
                    "## Instructions\n"
                    "1. Read the audit findings above carefully\n"
                    "2. For each vulnerability found, apply the specific fix\n"
                    "3. If a fix command is provided (like 'pip install package>=version'), execute it\n"
                    "4. Do NOT modify any code that isn't directly related to the vulnerabilities listed\n"
                    "5. If no vulnerabilities were found in the audit, make NO changes\n"
                )
                cmd = [
                    "claude",
                    "-p",
                    resolve_prompt,
                    "--verbose",
                    "--allowedTools",
                    "Read,Glob,Grep,Bash,Edit,Write",
                    "--add-dir",
                    clone_dir,
                ]
                logger.info("Running resolve on %s...", repo_url)
                resolve_result = subprocess.run(
                    cmd,
                    cwd=clone_dir,
                    capture_output=True,
                    text=True,
                    timeout=900,  # 15 minute timeout
                    start_new_session=True,  # Process group for clean cleanup
                )
                if resolve_result.returncode != 0:
                    logger.warning(
                        "Auto-resolve command failed for %s (exit=%d): %s",
                        repo_url,
                        resolve_result.returncode,
                        resolve_result.stderr[:500] if resolve_result.stderr else "(no stderr)",
                    )
                    continue

                # Commit changes
                committed = GitHubService.commit_changes(
                    clone_dir,
                    "fix(security): resolve vulnerabilities\n\nAutomatic security fix by Agented",
                )

                if committed:
                    pushed = GitHubService.push_branch(clone_dir, branch_name)
                    if pushed:
                        pr_url = GitHubService.create_pull_request(
                            repo_path=clone_dir,
                            branch_name=branch_name,
                            title="fix(security): resolve vulnerabilities",
                            body=(
                                "## Security Fix\n\n"
                                "This PR was automatically generated by Agented "
                                "to resolve detected security vulnerabilities.\n\n"
                                "Please review the changes carefully before merging."
                            ),
                        )
                        if pr_url:
                            pr_urls.append(pr_url)
                        else:
                            # PR creation failed after branch was pushed — roll back the remote branch
                            logger.warning(
                                "PR creation failed for %s; rolling back remote branch '%s'",
                                repo_url,
                                branch_name,
                            )
                            GitHubService.delete_remote_branch(clone_dir, branch_name)
                else:
                    logger.info("No changes to resolve for %s", repo_url)

            except Exception:
                logger.exception("Auto-resolve failed for %s", repo_url)

        return pr_urls

    @staticmethod
    def _verify_webhook_hmac(raw_payload: bytes, signature_header: str, secret: str) -> bool:
        """Verify HMAC-SHA256 signature for a webhook payload.

        Signature header format: sha256=<hex-digest>
        Returns True if the signature is valid, False otherwise.
        """
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = signature_header[7:]
        computed = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, expected)

    @classmethod
    def dispatch_webhook_event(
        cls,
        payload: dict,
        raw_payload: bytes = None,
        signature_header: str = None,
    ) -> bool:
        """Dispatch a webhook event to matching triggers and teams based on configurable field matching.

        Args:
            payload: The JSON webhook payload (parsed dict)
            raw_payload: Raw request body bytes, used for HMAC validation
            signature_header: Value of the X-Webhook-Signature-256 header

        Returns:
            True if at least one trigger or team was triggered
        """
        triggered = False

        # --- Trigger dispatch ---
        triggers = get_webhook_triggers()
        for trigger in triggers:
            match_field_path = trigger.get("match_field_path")
            match_field_value = trigger.get("match_field_value")
            text_field_path = trigger.get("text_field_path", "text")
            detection_keyword = trigger.get("detection_keyword", "")

            # HMAC validation: if this trigger has a webhook_secret configured,
            # require a valid signature. Skip trigger if signature is missing or invalid.
            webhook_secret = trigger.get("webhook_secret")
            if webhook_secret:
                if raw_payload is None or not cls._verify_webhook_hmac(
                    raw_payload, signature_header or "", webhook_secret
                ):
                    logger.warning(
                        "Webhook HMAC validation failed for trigger '%s' (%s); skipping dispatch",
                        trigger["name"],
                        trigger["id"],
                    )
                    continue

            # Check if payload matches the trigger's field criteria
            if match_field_path and match_field_value:
                actual_value = get_nested_value(payload, match_field_path)
                if str(actual_value) != str(match_field_value):
                    continue  # Field value doesn't match

            # Extract text from payload using configured path
            text = get_nested_value(payload, text_field_path)
            if text is None:
                text = ""
            elif not isinstance(text, str):
                text = str(text)

            # Check keyword match if detection_keyword is set
            if detection_keyword and detection_keyword not in text:
                continue  # Keyword not found in text

            # DB-backed deduplication: skip if identical payload was dispatched within TTL
            payload_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            is_new = check_and_insert_dedup_key(
                trigger_id=trigger["id"],
                payload_hash=payload_hash,
                ttl_seconds=cls.WEBHOOK_DEDUP_WINDOW,
            )
            if not is_new:
                logger.info(
                    "Webhook dedup: skipping duplicate dispatch for trigger '%s' (DB-backed)",
                    trigger["name"],
                )
                continue

            logger.info("Trigger '%s' triggered by webhook", trigger["name"])
            cls.save_trigger_event(trigger, payload)

            # Delegate to team execution if execution_mode is 'team'
            if trigger.get("execution_mode") == "team" and trigger.get("team_id"):
                from .team_execution_service import TeamExecutionService

                thread = threading.Thread(
                    target=TeamExecutionService.execute_team,
                    args=(trigger["team_id"], text, payload, "webhook"),
                    daemon=True,
                )
                thread.start()
                triggered = True
                continue  # Skip normal dispatch for this trigger

            from .orchestration_service import OrchestrationService

            thread = threading.Thread(
                target=OrchestrationService.execute_with_fallback,
                args=(trigger, text, payload, "webhook"),
                daemon=True,
            )
            thread.start()
            triggered = True

        # --- Team dispatch ---
        from ..database import get_webhook_teams

        teams = get_webhook_teams()
        for team in teams:
            # Parse trigger_config for field-matching rules (same schema as triggers)
            trigger_config = team.get("trigger_config")
            if trigger_config and isinstance(trigger_config, str):
                try:
                    trigger_config = json.loads(trigger_config)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(
                        "Failed to parse trigger_config JSON for team '%s' (%s): %s — using empty config",
                        team.get("name", ""),
                        team.get("id", ""),
                        e,
                    )
                    trigger_config = {}
            if not trigger_config:
                trigger_config = {}

            match_field_path = trigger_config.get("match_field_path")
            match_field_value = trigger_config.get("match_field_value")
            text_field_path = trigger_config.get("text_field_path", "text")
            detection_keyword = trigger_config.get("detection_keyword", "")

            # Check if payload matches the team's field criteria
            if match_field_path and match_field_value:
                actual_value = get_nested_value(payload, match_field_path)
                if str(actual_value) != str(match_field_value):
                    continue

            # Extract text from payload
            text = get_nested_value(payload, text_field_path)
            if text is None:
                text = ""
            elif not isinstance(text, str):
                text = str(text)

            # Check keyword match
            if detection_keyword and detection_keyword not in text:
                continue

            logger.info("Team '%s' triggered by webhook", team["name"])

            from .team_execution_service import TeamExecutionService

            TeamExecutionService.execute_team(team["id"], text, payload, "webhook")
            triggered = True

        if not triggered:
            logger.debug("No webhook-triggered triggers or teams matched")

        return triggered

    @staticmethod
    def build_resolve_command(audit_summary: str, project_paths: list) -> list:
        """Build Claude command with edit permissions for resolving security issues."""
        prompt = f"Resolve security threats reported by these results. Update dependencies and fix vulnerabilities:\n\n{audit_summary}"
        cmd = [
            "claude",
            "-p",
            prompt,
            "--verbose",
            "--allowedTools",
            "Read,Glob,Grep,Bash,Edit,Write",
        ]
        for path in project_paths:
            cmd.extend(["--add-dir", path])
        return cmd

    @classmethod
    def run_resolve_command(cls, audit_summary: str, project_paths: list):
        """Execute Claude command to resolve security issues."""
        cmd = cls.build_resolve_command(audit_summary, project_paths)

        try:
            logger.info("Executing resolve command: %s...", " ".join(cmd[:10]))
            logger.info("Working directory: %s", PROJECT_ROOT)
            logger.info("Project paths: %s", project_paths)
            result = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=900,  # 15 minute timeout
            )
            logger.info("Resolve output (stdout): %s", result.stdout)
            if result.stderr:
                logger.info("Resolve output (stderr): %s", result.stderr)
            logger.info("Resolve exit code: %d", result.returncode)
        except subprocess.TimeoutExpired:
            logger.error("Resolve command timed out after 15 minutes")
        except FileNotFoundError:
            logger.error("Claude command not found. Is Claude CLI installed?")
        except Exception:
            logger.exception("Error running resolve command")

    @classmethod
    def dispatch_github_event(cls, repo_url: str, pr_data: dict) -> bool:
        """Dispatch a GitHub PR event to matching triggers and teams.

        Args:
            repo_url: The GitHub repository URL
            pr_data: Dictionary containing PR information:
                - pr_number: PR number
                - pr_title: PR title
                - pr_url: PR URL
                - pr_author: PR author username
                - repo_full_name: Repository full name (owner/repo)
                - action: PR action (opened, synchronize, reopened)

        Returns:
            True if at least one trigger or team was triggered
        """
        triggered = False

        # --- Trigger dispatch ---
        triggers = get_triggers_by_trigger_source("github")
        for trigger in triggers:
            logger.info("Triggering '%s' for GitHub PR event", trigger["name"])

            # Build message text from PR data
            message_text = (
                f"PR #{pr_data['pr_number']}: {pr_data['pr_title']}\n"
                f"URL: {pr_data['pr_url']}\n"
                f"Author: {pr_data['pr_author']}\n"
                f"Repository: {pr_data['repo_full_name']}\n"
                f"Action: {pr_data['action']}"
            )

            # Build event context for logging
            event = {"type": "github_pr", "repo_url": repo_url, **pr_data}

            # Save trigger event
            cls.save_trigger_event(trigger, event)

            # Delegate to team execution if execution_mode is 'team'
            if trigger.get("execution_mode") == "team" and trigger.get("team_id"):
                from .team_execution_service import TeamExecutionService

                thread = threading.Thread(
                    target=TeamExecutionService.execute_team,
                    args=(trigger["team_id"], message_text, event, "github_webhook"),
                    daemon=True,
                )
                thread.start()
                triggered = True
                continue  # Skip normal dispatch for this trigger

            # Run trigger in background thread via orchestration (handles fallback chains)
            from .orchestration_service import OrchestrationService

            thread = threading.Thread(
                target=OrchestrationService.execute_with_fallback,
                args=(trigger, message_text, event, "github_webhook"),
                daemon=True,
            )
            thread.start()
            triggered = True

        # --- Team dispatch ---
        from ..database import get_teams_by_trigger_source

        teams = get_teams_by_trigger_source("github")
        for team in teams:
            logger.info("Triggering team '%s' for GitHub PR event", team["name"])

            message_text = (
                f"PR #{pr_data.get('pr_number', '')}: {pr_data.get('pr_title', '')}\n"
                f"URL: {pr_data.get('pr_url', '')}\n"
                f"Author: {pr_data.get('pr_author', '')}\n"
                f"Repository: {pr_data.get('repo_full_name', '')}\n"
                f"Action: {pr_data.get('action', '')}"
            )

            event = {"type": "github_pr", "repo_url": repo_url, **pr_data}

            from .team_execution_service import TeamExecutionService

            TeamExecutionService.execute_team(team["id"], message_text, event, "github")
            triggered = True

        if not triggered:
            logger.debug("No GitHub-triggered triggers or teams found")

        return triggered
