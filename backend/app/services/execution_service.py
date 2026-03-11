"""Trigger execution service with database-only status tracking and real-time logging.

This module is the public facade. Implementation is split across:
- execution_retry.py   — retry/rate-limit state (ExecutionRetryManager)
- execution_runner.py  — subprocess helpers (stream_pipe, budget_monitor, clone_repos, etc.)
- trigger_dispatcher.py — webhook/GitHub event dispatching
"""

import datetime
import json
import logging
import os
import shutil
import signal
import subprocess
import threading
from typing import Dict, List, Optional

from app.config import (
    EXECUTION_TIMEOUT_DEFAULT,
    EXECUTION_TIMEOUT_MAX,
    EXECUTION_TIMEOUT_MIN,
    PROJECT_ROOT,
    SIGTERM_GRACE_SECONDS,
    THREAD_JOIN_TIMEOUT,
)

from ..database import (
    PREDEFINED_TRIGGER_ID,
    get_latest_execution_for_trigger,
    get_paths_for_trigger_detailed,
)
from .audit_log_service import AuditLogService
from .budget_service import BudgetService
from .command_builder import CommandBuilder
from .diff_context_service import DiffContextService
from .execution_log_service import ExecutionLogService
from .execution_retry import ExecutionRetryManager
from .execution_runner import (
    auto_resolve_and_pr,
    build_subprocess_env,
    budget_monitor,
    clone_repos,
    fetch_pr_diff,
    stream_pipe,
)
from .github_service import GitHubService
from .process_manager import ProcessManager
from .prompt_renderer import PromptRenderer
from .trigger_dispatcher import (
    dispatch_github_event as _dispatch_github_event,
    dispatch_pr_comment_commands as _dispatch_pr_comment_commands,
    dispatch_webhook_event as _dispatch_webhook_event,
    match_payload as _match_payload,
)

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


TRIGGER_LOG_DIR = os.path.join(PROJECT_ROOT, "data/trigger_events")
SECURITY_AUDIT_REPORT_DIR = os.path.join(
    PROJECT_ROOT, ".claude/skills/weekly-security-audit/reports"
)

for _dir in (TRIGGER_LOG_DIR, SECURITY_AUDIT_REPORT_DIR):
    try:
        os.makedirs(_dir, exist_ok=True)
        if not os.access(_dir, os.W_OK):
            logger.warning("Directory is not writable: %s", _dir)
    except Exception as _dir_err:
        logger.warning("Could not create directory %s: %s", _dir, _dir_err)


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
    PAUSED = "paused"
    PAUSE_TIMEOUT = "pause_timeout"


class ExecutionService:
    """Service for trigger execution and status tracking via database.

    This class is the public API facade. Retry state is managed by
    ``ExecutionRetryManager``, subprocess helpers live in ``execution_runner``,
    and dispatching lives in ``trigger_dispatcher``. All public method signatures
    are preserved so that existing callers (32+ files) need zero import changes.
    """

    # ── Retry state (delegated to ExecutionRetryManager) ──────────────────────
    # Expose the underlying dicts for any code that accesses them directly
    _rate_limit_detected = ExecutionRetryManager._rate_limit_detected
    _transient_failure_detected = ExecutionRetryManager._transient_failure_detected
    _rate_limit_lock = ExecutionRetryManager._rate_limit_lock
    _pending_retries = ExecutionRetryManager._pending_retries
    _retry_timers = ExecutionRetryManager._retry_timers
    _retry_counts = ExecutionRetryManager._retry_counts

    @classmethod
    def was_rate_limited(cls, execution_id: str) -> Optional[int]:
        """Check if an execution was rate-limited. Returns cooldown seconds or None."""
        return ExecutionRetryManager.was_rate_limited(execution_id)

    @classmethod
    def was_transient_failure(cls, execution_id: str) -> Optional[str]:
        """Check if an execution had a transient failure. Returns error description or None."""
        return ExecutionRetryManager.was_transient_failure(execution_id)

    @classmethod
    def schedule_retry(
        cls,
        trigger: dict,
        message_text: str,
        event: Optional[dict],
        trigger_type: str,
        cooldown_seconds: int,
    ) -> None:
        """Schedule a retry execution after rate-limit cooldown expires."""
        return ExecutionRetryManager.schedule_retry(
            trigger, message_text, event, trigger_type, cooldown_seconds
        )

    @classmethod
    def get_pending_retries(cls) -> dict:
        """Return a snapshot of all pending rate-limit retries keyed by trigger_id."""
        return ExecutionRetryManager.get_pending_retries()

    @classmethod
    def restore_pending_retries(cls) -> int:
        """Re-schedule any pending retries persisted in the DB. Returns the count restored."""
        return ExecutionRetryManager.restore_pending_retries()

    # ── Status / event persistence ────────────────────────────────────────────

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
        os.makedirs(SECURITY_AUDIT_REPORT_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"threat_report_{trigger_id}_{timestamp}.txt"
        filepath = os.path.join(SECURITY_AUDIT_REPORT_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(message_text)

        logger.info("Saved threat report: %s", filepath)
        return filepath

    # ── Execution runner helpers (delegated to execution_runner) ──────────────

    @staticmethod
    def _fetch_pr_diff(event: dict) -> Optional[str]:
        """Fetch PR diff text from GitHub."""
        return fetch_pr_diff(event)

    # Execution timeout bounds imported from app.config
    TIMEOUT_MIN = EXECUTION_TIMEOUT_MIN
    TIMEOUT_MAX = EXECUTION_TIMEOUT_MAX
    TIMEOUT_DEFAULT = EXECUTION_TIMEOUT_DEFAULT

    @staticmethod
    def build_command(
        backend: str,
        prompt: str,
        allowed_paths: list = None,
        model: str = None,
        codex_settings: dict = None,
        allowed_tools: str = None,
    ) -> list:
        """Build the CLI command for the specified backend.

        Delegates to ``CommandBuilder.build()`` -- kept as a facade so existing
        call sites (including test mocks) continue to resolve.
        """
        return CommandBuilder.build(
            backend, prompt, allowed_paths, model, codex_settings, allowed_tools
        )

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
        return budget_monitor(
            execution_id, trigger_id, entity_type, entity_id, process, interval_seconds
        )

    @classmethod
    def _stream_pipe(
        cls, execution_id: str, stream_name: str, pipe, backend_type: str = None
    ) -> None:
        """Read from a pipe line by line and stream to log service."""
        return stream_pipe(
            execution_id,
            stream_name,
            pipe,
            backend_type,
            rate_limit_detected=ExecutionRetryManager._rate_limit_detected,
            transient_failure_detected=ExecutionRetryManager._transient_failure_detected,
            lock=ExecutionRetryManager._rate_limit_lock,
        )

    @classmethod
    def _clone_repos(cls, path_entries: list, cloned_dirs: list, github_repo_map: dict) -> list:
        """Resolve path entries into effective local paths, cloning GitHub repos as needed."""
        return clone_repos(path_entries, cloned_dirs, github_repo_map)

    @staticmethod
    def _build_subprocess_env(env_overrides: dict) -> Optional[dict]:
        """Build subprocess environment, injecting vault secrets and account overrides."""
        return build_subprocess_env(env_overrides)

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

            effective_paths = cls._clone_repos(path_entries, cloned_dirs, github_repo_map)

            paths_str = ", ".join(effective_paths) if effective_paths else "no paths configured"

            # Render prompt from template (delegated to PromptRenderer)
            prompt = PromptRenderer.render(trigger, trigger_id, message_text, paths_str, event)
            PromptRenderer.warn_unresolved(prompt, trigger.get("name", trigger_id), logger)

            # EXE-02: Inject diff-aware context for github_pr trigger events
            # Extracts focused diff context from PR to reduce token costs by 40-80%
            if trigger_type in ("github_webhook", "github_pr") and event:
                try:
                    pr_diff_text = cls._fetch_pr_diff(event)
                    if pr_diff_text:
                        diff_context = DiffContextService.extract_pr_diff_context(pr_diff_text)
                        if diff_context:
                            prompt = f"{prompt}\n\n--- PR Diff Context ---\n{diff_context}"
                            logger.info(
                                "Injected diff-aware context (%d chars) into prompt for trigger '%s'",
                                len(diff_context),
                                trigger.get("name", trigger_id),
                            )
                except Exception as e:
                    logger.warning(
                        "Failed to inject diff context for trigger '%s': %s",
                        trigger.get("name", trigger_id),
                        e,
                    )

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
            # so that trigger receipt -> subprocess output -> completion can be correlated.
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
                from ..db.health_alerts import create_health_alert

                budget_check = BudgetService.check_budget("trigger", trigger_id)
                if not budget_check["allowed"]:
                    limit_info = budget_check.get("limit") or {}
                    reason = budget_check.get("reason", "hard limit reached")

                    # Build detail string depending on violation type
                    if "Monthly run limit" in reason:
                        current_count = budget_check.get("monthly_run_count", "?")
                        max_runs = budget_check.get("max_monthly_runs", "?")
                        budget_detail = reason
                        alert_msg = (
                            f"Execution blocked: monthly run limit exceeded "
                            f"({current_count}/{max_runs})"
                        )
                    else:
                        period = limit_info.get("period", "monthly")
                        hard_limit = limit_info.get("hard_limit_usd", "N/A")
                        budget_detail = (
                            f"{reason}; "
                            f"spend=${budget_check.get('current_spend', 0):.4f}, "
                            f"hard_limit=${hard_limit}, "
                            f"period={period}"
                        )
                        alert_msg = f"Execution blocked: {budget_detail}"

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
                    # Create health alert for budget breach
                    try:
                        create_health_alert(
                            alert_type="budget_exceeded",
                            trigger_id=trigger_id,
                            message=alert_msg,
                            details={
                                "execution_id": execution_id,
                                "reason": reason,
                            },
                            severity="critical",
                        )
                    except Exception:
                        logger.debug(
                            "Failed to create health alert for budget exceeded on %s",
                            trigger_id,
                        )
                    return execution_id
            except Exception as e:
                tlog.error(
                    "Budget pre-check failed for trigger '%s': %s",
                    trigger.get("name", trigger_id),
                    e,
                    exc_info=True,
                )

            # Build process environment with optional overrides (includes vault secrets)
            proc_env = cls._build_subprocess_env(env_overrides)

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
                stdout_thread.join(timeout=SIGTERM_GRACE_SECONDS)
                stderr_thread.join(timeout=SIGTERM_GRACE_SECONDS)
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
            stdout_thread.join(timeout=THREAD_JOIN_TIMEOUT)
            stderr_thread.join(timeout=THREAD_JOIN_TIMEOUT)
            if stdout_thread.is_alive():
                tlog.error(
                    "stdout reader thread still alive after process exit — output may be incomplete"
                )
                ExecutionLogService.append_log(
                    execution_id,
                    "stderr",
                    "[WARNING] stdout reader did not exit cleanly — output may be incomplete",
                )
            if stderr_thread.is_alive():
                tlog.error(
                    "stderr reader thread still alive after process exit — output may be incomplete"
                )
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
                    auto_resolve_and_pr(trigger, github_repo_map, scan_output)
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
            logger.error("%s. Is %s CLI installed?", error_msg, backend, exc_info=True)
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
                    logger.error("Failed to clean up cloned directory %s: %s", d, e, exc_info=True)
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
        return auto_resolve_and_pr(trigger, github_repo_map, scan_output)

    # ── Dispatchers (delegated to trigger_dispatcher) ─────────────────────────

    @classmethod
    def dispatch_webhook_event(
        cls,
        payload: dict,
        raw_payload: bytes = None,
        signature_header: str = None,
    ) -> bool:
        """Dispatch a webhook event to matching triggers and teams based on configurable field matching."""
        return _dispatch_webhook_event(
            payload,
            raw_payload,
            signature_header,
            save_trigger_event_fn=cls.save_trigger_event,
        )

    @classmethod
    def _match_payload(cls, config: dict, payload: dict) -> Optional[str]:
        """Check whether a webhook payload matches a trigger/team config's field criteria."""
        return _match_payload(config, payload)

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
    def run_resolve_command(cls, audit_summary: str, project_paths: list) -> None:
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
            logger.error("Resolve command timed out after 15 minutes", exc_info=True)
        except FileNotFoundError:
            logger.error("Claude command not found. Is Claude CLI installed?", exc_info=True)
        except Exception:
            logger.exception("Error running resolve command")

    @classmethod
    def dispatch_github_event(cls, repo_url: str, pr_data: dict) -> bool:
        """Dispatch a GitHub PR event to matching triggers and teams."""
        return _dispatch_github_event(
            repo_url,
            pr_data,
            save_trigger_event_fn=cls.save_trigger_event,
        )

    @classmethod
    def dispatch_pr_comment_commands(
        cls, repo_url: str, commands: list, pr_data: dict
    ) -> bool:
        """Dispatch slash commands from a PR comment to matching triggers."""
        return _dispatch_pr_comment_commands(
            repo_url=repo_url,
            commands=commands,
            pr_data=pr_data,
            save_trigger_event_fn=cls.save_trigger_event,
        )
