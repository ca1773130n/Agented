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
from typing import List, Optional

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
from ..db import verification_records
from . import trigger_event_service
from .audit_log_service import AuditLogService
from .budget_service import BudgetService
from .command_builder import CommandBuilder
from .diff_context_service import DiffContextService
from .execution_log_service import ExecutionLogService
from .execution_retry import ExecutionRetryManager
from .execution_runner import (
    auto_resolve_and_pr,
    budget_monitor,
    build_subprocess_env,
    clone_repos,
    fetch_pr_diff,
    stream_pipe,
)
from .github_service import GitHubService
from .process_manager import ProcessManager
from .prompt_renderer import PromptRenderer
from .trigger_dispatcher import (
    dispatch_github_event as _dispatch_github_event,
)
from .trigger_dispatcher import (
    dispatch_pr_comment_commands as _dispatch_pr_comment_commands,
)
from .trigger_dispatcher import (
    dispatch_webhook_event as _dispatch_webhook_event,
)
from .trigger_dispatcher import (
    match_payload as _match_payload,
)

logger = logging.getLogger(__name__)


def _capture_session_id(execution_id: str, usage_data) -> None:
    """Persist the harness-reported session id as a resume handle (Phase 4,
    Unit B). Claude's terminal result JSON carries it; crashed/SIGKILLed runs
    never print that JSON, so they have no handle — documented limitation.
    Best-effort: never raises."""
    try:
        session_id = (usage_data or {}).get("session_id")
        if session_id:
            from ..db.execution_logs import set_execution_session_id

            set_execution_session_id(execution_id, session_id)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("session_id capture failed for %s: %s", execution_id, e)


def _verification_pr_gate(execution_id: str) -> bool:
    """Advisory post-hoc gate (Harness-1 Phase 2, P5): allow the downstream
    PR side-effect unless a verification claim is marked 'failed'. Returns
    True to proceed, False to skip. Best-effort: any error allows (fail-open),
    since this must never block a healthy run on a gate-infra hiccup."""
    try:
        if verification_records.has_failed(execution_id):
            logger.warning("Skipping auto-PR for %s: a verification claim failed", execution_id)
            return False
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("verification gate check failed for %s: %s", execution_id, e)
    return True


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


def _build_account_env_overrides(account_id: int) -> Optional[dict]:
    """Return env-var overrides for the given account id.

    Looks up the account row from backend_accounts then delegates to
    OrchestrationService._build_account_env (the canonical helper at ~:379).
    Returns None if the account is not found.
    """
    from ..database import get_connection
    from .orchestration_service import OrchestrationService

    with get_connection() as conn:
        # JOIN the backend row: _build_account_env branches on
        # account['backend_type'] (CLAUDE_CONFIG_DIR vs GEMINI_CLI_HOME),
        # which lives on ai_backends.type, not backend_accounts.
        row = conn.execute(
            "SELECT ba.*, ab.type AS backend_type "
            "FROM backend_accounts ba "
            "LEFT JOIN ai_backends ab ON ab.id = ba.backend_id "
            "WHERE ba.id = ?",
            (account_id,),
        ).fetchone()
    if not row:
        return None
    return OrchestrationService._build_account_env(dict(row))


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

    # Phase 4: in-flight redispatch origins (closes the async no-fan-out race;
    # workers=1). The DB redispatched_from check covers restarts.
    _redispatch_lock = threading.Lock()
    _redispatch_in_flight: set = set()

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

    @classmethod
    def redispatch_execution(cls, execution_id: str) -> dict:
        """Re-run an interrupted/failed execution as a NEW execution using the
        stored prompt (deterministic — no re-render). Claude runs that carry a
        session_id resume with --resume + a continuation prompt; everything
        else re-runs fresh (Phase 4, Unit A).

        Returns {"execution_id": new_id} on success, or {"error": reason} on failure.
        Errors: not_found, not_eligible, trigger_missing, already_redispatched.
        """
        from ..db.execution_logs import get_execution_log, get_redispatch_child
        from ..db.triggers import get_trigger

        original = get_execution_log(execution_id)
        if not original:
            return {"error": "not_found"}
        if original.get("status") not in ("interrupted", "failed"):
            return {"error": "not_eligible"}

        # Deterministic replay: prefer the trigger as it was AT RUN TIME (the
        # stored trigger_config_snapshot); fall back to the current DB trigger
        # for legacy rows without a snapshot. Paths/cwd still resolve at
        # re-dispatch time — documented semantics (spec Unit A).
        trigger = None
        snapshot = original.get("trigger_config_snapshot")
        if snapshot:
            try:
                import json as _json

                parsed = _json.loads(snapshot)
                if isinstance(parsed, dict) and parsed.get("id"):
                    trigger = parsed
            except (TypeError, ValueError):
                pass
        if trigger is None and original.get("trigger_id"):
            trigger = get_trigger(original["trigger_id"])
        if not trigger:
            return {"error": "trigger_missing"}

        stored_prompt = original.get("prompt") or ""
        resume_session_id = None
        prompt_override = stored_prompt
        if original.get("backend_type") == "claude" and original.get("session_id"):
            resume_session_id = original["session_id"]
            prompt_override = (
                "You were interrupted while working on the task below. "
                "Continue from where you left off.\n\n" + stored_prompt
            )

        # Identity: replay the original account so claude --resume runs against
        # the SAME CLAUDE_CONFIG_DIR (a session id is unusable under another
        # account's config dir) and usage attribution stays correct.
        account_id = original.get("account_id")
        env_overrides = None
        if account_id:
            env_overrides = _build_account_env_overrides(account_id)

        # No-fan-out guard — claimed LAST, after every early-return above, so
        # no path can leak the in-flight marker. The DB child row only appears
        # once the background thread reaches start_execution, so the DB check
        # alone is racy for rapid double-calls; the in-process set closes the
        # window (workers=1 deployment model; the DB check covers restarts).
        # NOTHING between this claim and thread.start() may return early.
        with cls._redispatch_lock:
            if execution_id in cls._redispatch_in_flight or get_redispatch_child(execution_id):
                return {"error": "already_redispatched"}
            cls._redispatch_in_flight.add(execution_id)

        AuditLogService.log(
            action="execution.redispatched",
            entity_type="trigger",
            entity_id=original.get("trigger_id") or "",
            outcome="dispatched",
            details={"origin_execution_id": execution_id, "resumed": bool(resume_session_id)},
        )

        # run_trigger BLOCKS until the subprocess exits, so dispatch in a
        # background thread with a PREALLOCATED execution id and return
        # immediately — mirror the manual-run pattern in trigger_service.py:~521.
        from ..database import generate_execution_id

        new_id = generate_execution_id(trigger.get("id") or "redispatch")

        def _dispatch():
            try:
                cls.run_trigger(
                    trigger,
                    "",
                    trigger_type=original.get("trigger_type") or "manual",
                    account_id=account_id,
                    env_overrides=env_overrides,
                    execution_id=new_id,
                    prompt_override=prompt_override,
                    resume_session_id=resume_session_id,
                    redispatched_from=execution_id,
                )
            finally:
                # By now the child row exists (or the dispatch failed) — the
                # DB-side guard takes over; release the in-flight marker.
                with cls._redispatch_lock:
                    cls._redispatch_in_flight.discard(execution_id)

        threading.Thread(target=_dispatch, daemon=True).start()
        return {"execution_id": new_id}

    @classmethod
    def auto_redispatch_interrupted(cls) -> int:
        """Startup recovery (Phase 4): one re-dispatch attempt for interrupted
        executions whose trigger opted in via auto_redispatch=1. Returns count."""
        from ..db.connection import get_connection

        with get_connection() as conn:
            rows = conn.execute(
                """SELECT e.execution_id FROM execution_logs e
                   JOIN triggers t ON t.id = e.trigger_id
                   WHERE e.status = 'interrupted'
                     AND t.auto_redispatch = 1
                     AND NOT EXISTS (
                         SELECT 1 FROM execution_logs c
                         WHERE c.redispatched_from = e.execution_id
                     )"""
            ).fetchall()
        count = 0
        for row in rows:
            try:
                result = cls.redispatch_execution(row["execution_id"])
                if "execution_id" in result:
                    count += 1
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("auto-redispatch failed for %s: %s", row["execution_id"], e)
        if count:
            logger.info("Auto-redispatched %d interrupted execution(s)", count)
        return count

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
        """Capture an incoming trigger payload to the DB. Returns event id as str.

        v0.7.1: writes to the trigger_events table via TriggerEventService.
        Set AGENTED_TRIGGER_EVENT_FILES=1 to additionally emit the legacy
        JSON file under data/trigger_events/ for debugging.
        """
        # The dispatcher may stash the raw signature header on the event dict
        # under a private key; pull it out (and remove from the persisted body)
        # so the column is populated correctly.
        signature_header = None
        if isinstance(event, dict):
            signature_header = event.get("_signature_header")
        try:
            payload_json = json.dumps(event, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            logger.warning("Failed to serialize trigger event payload: %s", e)
            payload_json = json.dumps({"_serialization_error": str(e)})

        try:
            eid = trigger_event_service.record(
                trigger_id=trigger.get("id"),
                payload=payload_json,
                signature_header=signature_header,
                dispatch_status="fired",
                matched=True,
            )
        except Exception as e:
            logger.warning("Failed to record trigger event in DB: %s", e, exc_info=True)
            # Fall back to a synthetic id so callers don't crash.
            eid = 0

        if os.environ.get("AGENTED_TRIGGER_EVENT_FILES") == "1":
            ExecutionService._legacy_save_trigger_event_file(trigger, event)

        return str(eid)

    @staticmethod
    def _legacy_save_trigger_event_file(trigger: dict, event: dict) -> None:
        """Pre-v0.7.1 JSON-file capture path; debug-only when env flag is set."""
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
            logger.debug("Saved trigger event (legacy file): %s", trigger_file)
        except Exception as e:
            logger.warning("Failed to save trigger event file: %s", e, exc_info=True)

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
        resume_session_id: str = None,
    ) -> list:
        """Build the CLI command for the specified backend.

        Delegates to ``CommandBuilder.build()`` -- kept as a facade so existing
        call sites (including test mocks) continue to resolve.
        """
        return CommandBuilder.build(
            backend, prompt, allowed_paths, model, codex_settings, allowed_tools, resume_session_id
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
        backend_type: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> None:
        """Periodically check budget during execution and kill process if hard limit exceeded."""
        return budget_monitor(
            execution_id,
            trigger_id,
            entity_type,
            entity_id,
            process,
            interval_seconds,
            backend_type=backend_type,
            team_id=team_id,
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
    def _build_subprocess_env(
        env_overrides: dict, proxy_url: Optional[str] = None
    ) -> Optional[dict]:
        """Build subprocess environment, injecting vault secrets and account overrides.

        Phase 24: when ``proxy_url`` is set, the egress proxy env (HTTPS_PROXY/
        HTTP_PROXY/NO_PROXY) is merged so the child routes outbound through the
        deny-by-default proxy and matches the sandbox ``--setenv``.
        """
        return build_subprocess_env(env_overrides, proxy_url=proxy_url)

    @classmethod
    def _enforce_launch_policy(
        cls,
        *,
        session_id: str,
        team_id: Optional[str],
        cmd: list,
        backend: str,
        sandboxed: bool = False,
        total_cost_usd: float = 0.0,
        tool_calls: int = 0,
    ) -> None:
        """Evaluate the stackable policy layer at the process-launch boundary.

        Called AFTER cmd/proc_env are built but BEFORE ``subprocess.Popen`` (the
        launch boundary, run_trigger:~767). Evaluating here — not inside the
        daemon stream-reader threads — is the rule from 23-RESEARCH.md Pitfall 1:
        a blocking ASK must hold the LAUNCHING call, never the live output pipe.

        Policy is anchored on the SESSION scope (session-not-bot HARD rule); the
        bot/trigger id is NEVER a policy key. ``action.kind == "process_launch"``
        so ``ask_on_os_tools`` and ``enforce_sandbox`` (inert) builtins can match.

        CONSOLIDATION (23-03, Pitfall 5): predefined safety bots (bot-security,
        bot-pr-review) launch through this same boundary, so their governance now
        DELEGATES to this one session-scoped policy gate rather than a parallel
        inline bot-keyed check — there is no second governance layer to keep in
        sync, and nothing is keyed on the bot id.

        Behaviour:
          - decision == "deny"  -> raise PolicyDenied (caller aborts, no Popen).
          - decision == "ask"   -> block via PolicyService.await_decision (reuses
            the human-gate SSE round-trip); anything but "approve" raises
            PolicyDenied (timeout fails closed to deny inside await_decision).
          - decision == "allow" -> return (caller proceeds to Popen unchanged).
        """
        from .policy_service import PolicyService

        # Delegate to the ONE shared launch gate (23 BLOCKER 4) so this path and
        # ProjectSessionManager.create_session enforce identical semantics — there
        # is no second gate implementation to drift out of sync.
        PolicyService.enforce_launch(
            session_id=session_id,
            team_id=team_id,
            cmd=cmd,
            backend=backend,
            # Phase 24: the REAL sandboxed flag from build_sandbox_prefix — no longer
            # hardcoded False. When a policy mandates enforce_sandbox and the launch
            # is NOT sandboxed (degraded / sandbox disabled), evaluate() DENIES and
            # this raises PolicyDenied so the process never starts (fail closed).
            sandboxed=sandboxed,
            total_cost_usd=total_cost_usd,
            tool_calls=tool_calls,
        )

    @classmethod
    def _egress_allowlist_from_env(cls) -> set:
        """Per-run egress allowlist. ``AGENTED_EGRESS_ALLOWLIST`` (comma-separated)
        overrides; otherwise a conservative required set. Empty ⇒ deny-by-default."""
        raw = os.environ.get("AGENTED_EGRESS_ALLOWLIST")
        if raw is not None:
            return {h.strip() for h in raw.split(",") if h.strip()}
        return {"github.com", "api.github.com", "api.anthropic.com"}

    @classmethod
    def _start_egress_proxy_or_fail_closed(
        cls,
        *,
        execution_id: Optional[str],
        policy_session_id: str,
        env_overrides: dict,
        proc_env: Optional[dict],
    ) -> tuple:
        """Start the deny-by-default egress proxy for this run, or FAIL CLOSED.

        SECURITY (24-fix, crit 3): when ``AGENTED_SANDBOX`` is opted in the operator
        requires deny-by-default egress control, so a proxy that CANNOT start must
        REFUSE the launch (raise ``PolicyDenied``) — the previous behaviour continued
        WITHOUT egress filtering (fail OPEN), which silently defeated the control.

        Returns ``(egress_handle, proxy_url, proc_env)``. When sandboxing is disabled
        the run has no egress proxy and this returns ``(None, None, proc_env)``
        unchanged. On success ``proc_env`` is rebuilt so ``HTTPS_PROXY``/``HTTP_PROXY``
        match the sandbox ``--setenv`` and the proxy the child is pointed at.
        """
        from .sandbox_wrap import sandbox_enabled

        if not sandbox_enabled():
            return None, None, proc_env
        try:
            from .egress_proxy import ThreadedEgressProxy

            egress_handle = ThreadedEgressProxy(
                cls._egress_allowlist_from_env(), session_id=policy_session_id
            ).start()
            proxy_url = egress_handle.url
            # Defense-in-depth (24-fix, BLOCKER 2): even though ``start()`` now raises
            # when the proxy never becomes ready, treat a missing/empty url here as a
            # not-ready failure too — never build the child env (and reach Popen)
            # trusting a dead proxy url (that would run WITHOUT egress filtering).
            if not proxy_url:
                raise RuntimeError("egress proxy started but exposed no url (not ready)")
            proc_env = cls._build_subprocess_env(env_overrides, proxy_url=proxy_url)
            return egress_handle, proxy_url, proc_env
        except Exception as exc:
            from .policy_service import PolicyDenied

            logger.error(
                "egress proxy failed to start for %s; refusing launch "
                "(sandbox/egress required — fail closed)",
                execution_id,
                exc_info=True,
            )
            raise PolicyDenied(
                {
                    "decision": "deny",
                    "reason": (
                        "egress proxy failed to start; refusing launch because egress "
                        "control is required (AGENTED_SANDBOX)"
                    ),
                }
            ) from exc

    @classmethod
    def _apply_sandbox_and_enforce(
        cls,
        cmd: list,
        workspace: str,
        *,
        session_id: str,
        team_id: Optional[str],
        backend: str,
        proxy_url: Optional[str] = None,
        total_cost_usd: float = 0.0,
        tool_calls: int = 0,
    ) -> tuple:
        """Phase-24 launch seam: OS-sandbox-wrap the command, then run the Phase-23
        launch gate with the REAL ``sandboxed`` flag BEFORE ``subprocess.Popen``.

        Returns ``(wrapped_cmd, sandboxed)``. A DENY inside ``_enforce_launch_policy``
        raises ``PolicyDenied`` and the caller never reaches Popen — so an
        ``enforce_sandbox`` policy refuses an unsandboxable launch (crit 4, fail
        closed). ``wrap_harness_command`` is a no-op pass-through unless
        ``AGENTED_SANDBOX`` is set, so normal operation is unchanged by default.
        """
        from .sandbox_wrap import wrap_harness_command

        wrapped, sandboxed = wrap_harness_command(cmd, workspace, net=True, proxy_url=proxy_url)
        cls._enforce_launch_policy(
            session_id=session_id,
            team_id=team_id,
            cmd=wrapped,
            backend=backend,
            sandboxed=sandboxed,
            total_cost_usd=total_cost_usd,
            tool_calls=tool_calls,
        )
        return wrapped, sandboxed

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
        execution_id: str = None,
        prompt_override: str = None,
        resume_session_id: str = None,
        redispatched_from: str = None,
    ) -> Optional[str]:
        """Execute a trigger's prompt with real-time log streaming. Returns execution_id.

        ``execution_id`` may be pre-allocated by the caller (06 L1) so a
        background runner is trackable before start_execution runs.
        ``prompt_override`` skips PromptRenderer and all post-render augmentations.
        ``resume_session_id`` is forwarded to build_command for claude --resume.
        ``redispatched_from`` is persisted as provenance after start_execution."""
        trigger_id = trigger["id"]
        preallocated_execution_id = execution_id
        execution_id = None
        cloned_dirs = []  # temp dirs to clean up
        github_repo_map = {}  # clone_dir -> repo_url (for auto-resolve PR flow)
        egress_handle = None  # Phase 24: deny-by-default egress proxy for this run

        try:
            # Get detailed path info (includes path_type and github_repo_url)
            path_entries = get_paths_for_trigger_detailed(trigger_id)

            effective_paths = cls._clone_repos(path_entries, cloned_dirs, github_repo_map)

            paths_str = ", ".join(effective_paths) if effective_paths else "no paths configured"

            # Render prompt — override path uses the stored prompt verbatim and
            # skips all post-render augmentations (diff injection, skill paths).
            if prompt_override is not None:
                prompt = prompt_override
            else:
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
                backend,
                prompt,
                effective_paths,
                model,
                allowed_tools=allowed_tools,
                resume_session_id=resume_session_id,
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
                execution_id=preallocated_execution_id,
            )
            if redispatched_from:
                from ..db.execution_logs import set_redispatched_from

                set_redispatched_from(execution_id, redispatched_from)
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

            # Life-Harness: snapshot which Forge primitives were active for
            # this execution (project-scoped). Forge's renderer chain owns
            # the actual injection; we only record what shipped so the
            # evolution loop can attribute trajectories to harness versions.
            # Best-effort; never blocks the spawn.
            try:
                from app.services.harness_snapshot_service import (
                    capture_snapshot_for_execution,
                )

                capture_snapshot_for_execution(
                    execution_id=execution_id,
                    trigger=trigger,
                    harness_kind=backend,
                )
            except Exception:
                logger.debug(
                    "harness snapshot capture raised for %s",
                    execution_id,
                    exc_info=True,
                )

            # Policy is SESSION-scoped (session-not-bot rule): prefer the injected
            # AGENTED_SESSION_ID, falling back to execution_id; team scope is
            # best-effort from the trigger's _team_id.
            policy_session_id = (proc_env or {}).get("AGENTED_SESSION_ID") or execution_id

            # Phase 24 (24-fix, crit 3): deny-by-default egress proxy (opt-in via
            # AGENTED_SANDBOX). Starting it FAILS CLOSED — a proxy that cannot start
            # refuses the launch (raises PolicyDenied, caught below → clean FAILED,
            # Popen never reached) rather than silently running with NO egress
            # filtering (the fail-OPEN hole this closes).
            egress_handle, proxy_url, proc_env = cls._start_egress_proxy_or_fail_closed(
                execution_id=execution_id,
                policy_session_id=policy_session_id,
                env_overrides=env_overrides,
                proc_env=proc_env,
            )

            # Stackable policy gate (23-03) + OS sandbox (24-03): wrap the command in
            # the OS sandbox, set the REAL sandboxed flag, and evaluate the launch gate
            # BEFORE Popen (Pitfall 1 — never block the daemon stream-reader threads).
            # A DENY (incl. enforce_sandbox on an unsandboxable launch) raises
            # PolicyDenied; an ASK blocks the launching call until an operator resolves
            # it. The process never starts on a refusal.
            cmd, _sandboxed = cls._apply_sandbox_and_enforce(
                cmd,
                effective_cwd,
                session_id=policy_session_id,
                team_id=trigger.get("_team_id"),
                backend=backend,
                proxy_url=proxy_url,
            )

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
                kwargs={"backend_type": backend, "team_id": trigger.get("_team_id")},
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
                # Reap the killed child so it doesn't linger as a zombie (01 M1).
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    tlog.warning("timed-out process did not reap after SIGKILL")
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

            # Capture the harness session id for ANY terminal outcome (Phase 4):
            # failed-but-cleanly-exited claude runs are the main resume audience.
            _capture_session_id(
                execution_id,
                BudgetService.extract_token_usage(
                    ExecutionLogService.get_stdout_log(execution_id), backend
                ),
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
                    cls._maybe_auto_resolve_and_pr(
                        execution_id, trigger, github_repo_map, scan_output
                    )
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
            from .policy_service import PolicyDenied

            # A policy DENY (or operator-denied ASK) at the launch boundary aborts
            # the run WITHOUT launching the subprocess — surface the verdict reason
            # as a clean FAILED, not an unexpected error/stacktrace.
            if isinstance(e, PolicyDenied):
                error_msg = f"Blocked by policy: {e}"
                logger.warning("Policy blocked execution for trigger '%s': %s", trigger["name"], e)
            else:
                error_msg = str(e)
                logger.exception("Error running trigger '%s'", trigger["name"])
            if execution_id:
                ExecutionLogService.finish_execution(
                    execution_id=execution_id, status=ExecutionState.FAILED, error_message=error_msg
                )
        finally:
            # Phase 24: tear down the per-run egress proxy (best-effort).
            if egress_handle is not None:
                try:
                    egress_handle.stop()
                except Exception:
                    logger.debug("egress proxy stop raised", exc_info=True)
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
            # Life-Harness: emit session-completion event for this trigger
            # execution so the annotator + evolver observe it. Best-effort;
            # session_id is the execution_id, project_id resolved via
            # project_paths join inside the handler if not passed here.
            if execution_id:
                try:
                    from app.services.execution_events import emit_session_complete
                    from app.services.harness_snapshot_service import (
                        _resolve_trigger_project_id,
                    )

                    _final_status = "completed"
                    try:
                        from app.database import get_execution_log

                        _row = get_execution_log(execution_id)
                        if _row:
                            _final_status = _row.get("status") or "completed"
                    except Exception:
                        pass
                    emit_session_complete(
                        "trigger_execution",
                        execution_id,
                        _resolve_trigger_project_id(trigger or {}),
                        _final_status,
                        None,
                    )
                except Exception:
                    logger.debug(
                        "session_events emit failed for %s",
                        execution_id,
                        exc_info=True,
                    )

        return execution_id

    @classmethod
    def _auto_resolve_and_pr(
        cls, trigger: dict, github_repo_map: dict, scan_output: str
    ) -> List[str]:
        """Resolve issues in GitHub repos and create PRs. Returns list of PR URLs."""
        return auto_resolve_and_pr(trigger, github_repo_map, scan_output)

    @classmethod
    def _maybe_auto_resolve_and_pr(cls, execution_id, trigger, github_repo_map, scan_output):
        """Run the auto-resolve+PR side-effect unless a verification claim
        failed (Harness-1 Phase 2, P5). The gate is advisory: with no records
        it always proceeds. Delegates to the existing ``_auto_resolve_and_pr``
        wrapper (DRY) rather than re-calling the module function."""
        if _verification_pr_gate(execution_id):
            cls._auto_resolve_and_pr(trigger, github_repo_map, scan_output)

    # ── Dispatchers (delegated to trigger_dispatcher) ─────────────────────────

    @classmethod
    def dispatch_webhook_event(
        cls,
        payload: dict,
        raw_payload: bytes = None,
        signature_header: str = None,
        skip_signature_validation: bool = False,
    ) -> bool:
        """Dispatch a webhook event to matching triggers and teams based on configurable field matching.

        ``skip_signature_validation`` is used by the admin-only replay endpoint
        after the original raw bytes are gone — re-encoding parsed JSON does
        not reproduce the original signature, so HMAC checks would always fail.
        """
        return _dispatch_webhook_event(
            payload,
            raw_payload,
            signature_header,
            save_trigger_event_fn=cls.save_trigger_event,
            skip_signature_validation=skip_signature_validation,
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
    def dispatch_pr_comment_commands(cls, repo_url: str, commands: list, pr_data: dict) -> bool:
        """Dispatch slash commands from a PR comment to matching triggers."""
        return _dispatch_pr_comment_commands(
            repo_url=repo_url,
            commands=commands,
            pr_data=pr_data,
            save_trigger_event_fn=cls.save_trigger_event,
        )
