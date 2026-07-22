"""Litestar startup + shutdown hooks (wave 80).

Mirrors the work that `app/__init__.py:create_app` did during Flask
startup so the Litestar process can run alone once Flask is retired.
"""

from __future__ import annotations

import atexit
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Non-fatal startup warnings collected during _on_startup. Surfaced via
# /health/readiness and consulted by the existing Flask-era code paths
# that import _startup_warnings from app.
_startup_warnings: list[str] = []


def _seed_bundled_marketplace() -> None:
    from app.db.plugins import create_marketplace, get_all_marketplaces
    from app.services.setup_service import BUNDLE_MARKETPLACE_NAME, BUNDLE_MARKETPLACE_URL

    for mkt in get_all_marketplaces():
        if mkt.get("url") == BUNDLE_MARKETPLACE_URL:
            return
    create_marketplace(BUNDLE_MARKETPLACE_NAME, BUNDLE_MARKETPLACE_URL)
    logger.info("Seeded bundled marketplace: %s", BUNDLE_MARKETPLACE_NAME)


def _seed_system_agent() -> None:
    from app.db.connection import get_connection

    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM super_agents WHERE id = 'sa-system'").fetchone()
        if existing:
            return
        conn.execute(
            """INSERT INTO super_agents (id, name, description, backend_type, created_at)
               VALUES ('sa-system', 'System',
               'Automated error diagnosis and repair agent for the Agented platform',
               'claude', CURRENT_TIMESTAMP)""",
        )
        conn.commit()


def _init_database() -> None:
    from app.database import (
        auto_register_project_root,
        init_db,
        migrate_existing_paths,
        seed_bot_templates,
        seed_predefined_triggers,
        seed_preset_mcp_servers,
    )
    from app.db.bundle_seeds import seed_bundled_teams_and_agents
    from app.db.rbac import backfill_bootstrap_admin
    from app.services.instance_service import InstanceService
    from app.services.super_agent_session_service import SuperAgentSessionService

    init_db()
    # Self-heal a locked-out install: if a human signed up before the
    # first-operator-admin bootstrap existed (so no user holds admin), promote
    # the earliest real login account. No-op once any user is admin.
    promoted = backfill_bootstrap_admin()
    if promoted:
        _startup_warnings.append(f"bootstrap_admin_promoted:{promoted}")
    seed_predefined_triggers()
    seed_preset_mcp_servers()
    seed_bot_templates()
    seed_bundled_teams_and_agents()
    _seed_bundled_marketplace()
    _seed_system_agent()
    # Phase 17-06: idempotent forge-creator default bundle (5 global-scope
    # creator skills). Own try/except so a seed issue can't take down startup.
    try:
        from app.services.forge_creator_seed import seed_forge_creator_bundle

        seed_forge_creator_bundle()
    except Exception:
        logger.warning("forge-creator seed failed", exc_info=True)
    migrate_existing_paths()
    auto_register_project_root()
    InstanceService.ensure_worktrees()
    SuperAgentSessionService.restore_active_sessions()
    SuperAgentSessionService.cleanup_stale_sessions()


def _detect_backends() -> None:
    from app.db.backends import check_and_update_backend_installed, get_all_backends
    from app.services.backend_detection_service import BACKEND_CAPABILITIES, detect_backend
    from app.services.grd_cli_service import GrdCliService

    type_to_id = {b["type"]: b["id"] for b in get_all_backends()}
    for backend_type in BACKEND_CAPABILITIES:
        installed, version, _ = detect_backend(backend_type)
        bid = type_to_id.get(backend_type)
        if bid:
            check_and_update_backend_installed(bid, installed, version)
        if not installed:
            _startup_warnings.append(f"cli_missing:{backend_type}")

    # v0.7.84 — probe both ``grd-tools.js`` (legacy write ops) and
    # ``gd.js`` (v0.3.24 Ouroboros surface). The Litestar app keeps
    # running either way; routes that need a binary check
    # ``GrdCliService.available()`` and degrade gracefully.
    GrdCliService.detect_binaries()
    avail = GrdCliService.available()
    if avail["grd_tools_available"]:
        logger.info("GRD grd-tools binary detected: %s", avail["grd_tools_path"])
    else:
        logger.warning(
            "GRD grd-tools binary not found — write operations will be unavailable. "
            "Configure grd_binary_path in Agented settings or set CLAUDE_PLUGIN_ROOT env var."
        )
    if avail["gd_available"]:
        logger.info("GRD gd binary detected: %s", avail["gd_path"])
    else:
        logger.warning(
            "GRD gd binary not found — v0.3.24 Ouroboros commands "
            "(think / health / dead-end / genome / verify mechanical) unavailable."
        )


def purge_trigger_events_job() -> None:
    """v0.7.1: daily TTL purge of trigger_events.

    Retention controlled by TRIGGER_EVENT_RETENTION_DAYS env var (default 30).
    Exposed at module top-level so the scheduler can register it by reference
    and the corresponding pytest can import + invoke it directly.
    """
    from app.services import trigger_event_service

    days = int(os.environ.get("TRIGGER_EVENT_RETENTION_DAYS", "30"))
    try:
        deleted = trigger_event_service.purge_older_than(days=days)
        if deleted:
            logger.info("Purged %d trigger_events older than %d days", deleted, days)
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("Trigger events purge job failed: %s", e, exc_info=True)


def purge_super_agent_activity_job() -> None:
    """v0.7.7: daily TTL purge of super_agent_activity.

    Retention controlled by SUPER_AGENT_ACTIVITY_RETENTION_DAYS env var
    (default 30). Mirrors purge_trigger_events_job — exposed at module
    top-level so the scheduler can register it by reference and tests can
    import + invoke it directly.
    """
    from app.services import super_agent_activity_service

    days = int(os.environ.get("SUPER_AGENT_ACTIVITY_RETENTION_DAYS", "30"))
    try:
        deleted = super_agent_activity_service.purge_older_than(days=days)
        if deleted:
            logger.info(
                "Purged %d super_agent_activity rows older than %d days",
                deleted,
                days,
            )
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("Super-agent activity purge job failed: %s", e, exc_info=True)


def refresh_stale_model_caches_job() -> None:
    """v0.7.8: daily background refresh of expiring model_discovery_cache rows.

    Looks ahead one day (grace_seconds=86400) so caches are renewed before
    they actually go stale, keeping interactive callers off the slow
    subprocess/PTY discovery path. Mirrors purge_super_agent_activity_job:
    exposed at module top-level so the scheduler can register it by
    reference and tests can import + invoke it directly.
    """
    from app.services import model_cache_service

    try:
        stale = model_cache_service.list_stale(grace_seconds=86400)
        if not stale:
            return
        for row in stale:
            try:
                model_cache_service.refresh(row["backend_kind"], row["auth_method"])
            except Exception as inner:  # pragma: no cover — defensive
                logger.warning(
                    "Model cache refresh failed for %s/%s: %s",
                    row.get("backend_kind"),
                    row.get("auth_method"),
                    inner,
                    exc_info=True,
                )
        logger.info("Refreshed %d stale model_discovery_cache rows", len(stale))
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("Model cache refresh job failed: %s", e, exc_info=True)


def autonomous_apply_job() -> None:
    """Periodic: evaluate + auto-apply eligible rounds for autonomy-enabled projects."""
    try:
        from app.db import project_autonomy_config as cfg
        from app.services.harness_autonomy import process_project_autonomy

        for row in cfg.list_enabled():
            try:
                process_project_autonomy(row["project_id"])
            except Exception:
                logger.warning(
                    "autonomy job: project %s failed",
                    row.get("project_id"),
                    exc_info=True,
                )
    except Exception:
        logger.warning("autonomous_apply_job failed", exc_info=True)


def skill_sleep_nightly_job() -> None:
    """Periodic (SkillOpt P5b): run a staged Skill-Sleep round for each skill
    bound to an autonomy-enabled project that is past its cooldown. Staged
    only — an operator still adopts; never auto-writes a skill."""
    try:
        from app.services.skill_sleep_service import SkillSleepScheduler

        result = SkillSleepScheduler.run_due()
        if result.get("ran"):
            logger.info("skill-sleep nightly: ran %d round(s)", len(result["ran"]))
    except Exception:
        logger.warning("skill_sleep_nightly_job failed", exc_info=True)


def _setup_scheduler(app: Any) -> None:
    from app.services.scheduler_service import SchedulerService

    SchedulerService.init(app)

    # Monitoring services
    from app.services.health_monitor_service import HealthMonitorService
    from app.services.monitoring_service import MonitoringService

    MonitoringService.init()
    HealthMonitorService.init()

    # Periodic jobs
    if SchedulerService._scheduler:
        from app.db.webhook_dedup import cleanup_expired_keys
        from app.services.agent_conversation_service import AgentConversationService
        from app.services.chat_retry_service import ChatRetryService
        from app.services.cliproxy_manager import CLIProxyManager
        from app.services.memory_evolution import (
            process_pending_extractions,
            run_consolidation_check,
            run_decay_all,
        )
        from app.services.project_workspace_service import ProjectWorkspaceService
        from app.services.session_collection_service import SessionCollectionService
        from app.services.super_agent_session_service import (
            SuperAgentSessionService as _SASvc,
        )

        periodic_jobs = [
            (
                SessionCollectionService.collect_all,
                {"minutes": 10},
                "session_usage_collection",
            ),
            (ProjectWorkspaceService.sync_all_repos, {"minutes": 30}, "project_repo_sync"),
            (
                AgentConversationService.cleanup_stale_conversations,
                {"minutes": 5},
                "stale_conversation_cleanup",
            ),
            (cleanup_expired_keys, {"seconds": 60}, "webhook_dedup_cleanup"),
            (process_pending_extractions, {"seconds": 30}, "kg_entity_extraction"),
            (run_consolidation_check, {"minutes": 5}, "memory_consolidation_check"),
            (run_decay_all, {"hours": 24}, "knowledge_decay"),
            (_SASvc.cleanup_stale_sessions, {"hours": 6}, "stale_sa_session_cleanup"),
            # v0.7.1: daily TTL purge of trigger_events.
            (purge_trigger_events_job, {"hours": 24}, "trigger_event_purge"),
            # v0.7.7: daily TTL purge of super_agent_activity.
            (
                purge_super_agent_activity_job,
                {"hours": 24},
                "super_agent_activity_purge",
            ),
            # v0.7.8: daily background refresh of expiring model caches.
            (
                refresh_stale_model_caches_job,
                {"hours": 24},
                "model_cache_refresh",
            ),
            # Phase D: periodic autonomy poller — auto-apply eligible rounds.
            (autonomous_apply_job, {"minutes": 5}, "harness_autonomous_apply"),
            # SkillOpt P5b: nightly staged Skill-Sleep rounds for bound skills.
            (skill_sleep_nightly_job, {"hours": 24}, "skill_sleep_nightly"),
            # Chat rate-limit rotation Phase 2: re-dispatch parked chat turns
            # once a rate-limited account frees up.
            (ChatRetryService.process_pending, {"seconds": 20}, "chat_retry_queue"),
            # CLIProxy auth keepalive: probe to keep refreshable tokens warm and
            # surface dead-refresh-token accounts that need an interactive re-login.
            (CLIProxyManager.keepalive_job, {"minutes": 30}, "cliproxy_auth_keepalive"),
        ]
        for func, interval_kwargs, job_id in periodic_jobs:
            SchedulerService._scheduler.add_job(
                func=func,
                trigger="interval",
                id=job_id,
                replace_existing=True,
                **interval_kwargs,
            )

        # Rate-limit / usage monitoring as a FIRST-CLASS background daemon
        # job. Previously it was registered only inside
        # MonitoringService.init()'s conditional auto-enable path, so it
        # could effectively run "only while the operator is browsing" (the
        # frontend's pollNow drives extra polls). Register it explicitly here
        # on every startup at the CONFIGURED interval, gated on enabled. Same
        # job id => idempotent with init() (one job, no double-poll).
        try:
            from app.database import get_monitoring_config

            _mon_cfg = get_monitoring_config()
            if _mon_cfg.get("enabled"):
                _mon_interval = max(1, int(_mon_cfg.get("polling_minutes", 5)))
                SchedulerService._scheduler.add_job(
                    func=MonitoringService._poll_usage,
                    trigger="interval",
                    minutes=_mon_interval,
                    id="token_usage_monitoring",
                    replace_existing=True,
                )
                logger.info("Monitoring daemon job registered: poll every %d min", _mon_interval)
        except Exception:
            logger.warning("monitoring daemon job registration failed", exc_info=True)

        # Competitive-intelligence poller (REQ-28). Authenticated conditional
        # polling of competitor github_repo sources (ETag/If-None-Match -> free
        # 304s). Registered as a SEPARATE config-gated interval job, mirroring
        # the monitoring-daemon block above — default DISABLED, and it does NOT
        # touch the periodic_jobs list or the Phase-D autonomy poller.
        try:
            from app.services.competitor_poll_service import CompetitorPollService

            # Register/remove the SCHEDULED poll job from the stored config.
            # Same behavior as the old inline add_job (default DISABLED), but now
            # the operator toggle (CompetitorPollService.reconfigure via the
            # /api/competitor-intel/config route) can flip it at RUNTIME.
            CompetitorPollService.apply_stored_config()
        except Exception:
            logger.warning("competitor-intel poll job registration failed", exc_info=True)

        # When a standalone usage daemon (scripts/run_usage_daemon.py) owns
        # background tracking, drop the in-process collection + monitoring
        # jobs so the same work isn't done twice (and two writers don't
        # contend on SQLite). The daemon runs them 24/7 regardless of whether
        # this web backend is up.
        if os.environ.get("AGENTED_EXTERNAL_USAGE_DAEMON", "").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            for _jid in ("session_usage_collection", "token_usage_monitoring"):
                try:
                    SchedulerService._scheduler.remove_job(_jid)
                except Exception:  # noqa: BLE001 — job may not exist
                    pass
            logger.info(
                "AGENTED_EXTERNAL_USAGE_DAEMON set — in-process usage tracking "
                "deferred to the standalone daemon"
            )

    # Auxiliary schedulers
    from app.services.agent_scheduler_service import AgentSchedulerService
    from app.services.rotation_evaluator import RotationEvaluator

    AgentSchedulerService.init()
    RotationEvaluator.init()


def _register_cleanup_handlers() -> None:
    """Cleanup work that ran in Flask's startup path. Schedules atexit hooks."""
    try:
        from app.services.project_session_manager import ProjectSessionManager

        ProjectSessionManager.cleanup_dead_sessions()
    except Exception as exc:
        logger.error("Project session cleanup failed on startup: %s", exc, exc_info=True)
        _startup_warnings.append(f"project_session_cleanup: {exc}")

    try:
        from app.services.workflow_execution_service import WorkflowExecutionService

        WorkflowExecutionService.cleanup_stale_executions()
    except Exception as exc:
        logger.error(
            "Workflow stale execution cleanup failed on startup: %s",
            exc,
            exc_info=True,
        )
        _startup_warnings.append(f"workflow_stale_cleanup: {exc}")

    try:
        from app.services.execution_service import ExecutionService

        ExecutionService.restore_pending_retries()
    except Exception as exc:
        logger.error("Pending retry restore failed on startup: %s", exc, exc_info=True)
        _startup_warnings.append(f"pending_retry_restore: {exc}")

    try:
        from app.services.execution_service import ExecutionService

        ExecutionService.auto_redispatch_interrupted()
    except Exception as exc:
        logger.error("Auto-redispatch on startup failed: %s", exc, exc_info=True)
        _startup_warnings.append(f"auto_redispatch: {exc}")

    from app.services.agent_message_bus_service import AgentMessageBusService
    from app.services.execution_queue_service import ExecutionQueueService

    ExecutionQueueService.start_dispatcher()
    atexit.register(ExecutionQueueService.stop_dispatcher)

    AgentMessageBusService.start()
    atexit.register(AgentMessageBusService.stop)

    try:
        from app.services.cliproxy_manager import CLIProxyManager

        CLIProxyManager.kill_orphans()
        if CLIProxyManager.install_if_needed():
            if CLIProxyManager.start():
                logger.info("CLIProxyAPI global proxy started on port %d", CLIProxyManager._port)
            else:
                logger.info("CLIProxyAPI not started (no config or not ready)")
            atexit.register(CLIProxyManager.stop)
        else:
            logger.info("CLIProxyAPI binary not available -- proxy streaming disabled")
    except Exception as exc:
        logger.error(
            "CLIProxyManager initialization failed; proxy streaming will be unavailable: %s",
            exc,
            exc_info=True,
        )

    # Tesserae 0.23/0.24 "sleep cycle": a long-lived `engine --all --consolidate`
    # daemon that compresses agent memory, forgets-by-disuse (LRU), and discovers
    # cross-agent connections during idle. Gated on AGENTED_TESSERAE_CONSOLIDATE
    # (default on); no-op under AGENTED_LITESTAR_SKIP_STARTUP since this whole
    # function is skipped there.
    try:
        from app.services.tesserae_engine_daemon import TesseraeEngineDaemon

        if TesseraeEngineDaemon.start():
            atexit.register(TesseraeEngineDaemon.stop)
    except Exception as exc:
        logger.warning(
            "Tesserae consolidation daemon init failed; sleep cycle disabled: %s",
            exc,
            exc_info=True,
        )


def on_startup(app: Any) -> None:
    """Litestar `on_startup` hook — runs once when the app boots."""
    if os.environ.get("AGENTED_LITESTAR_SKIP_STARTUP") == "1":
        logger.info("AGENTED_LITESTAR_SKIP_STARTUP=1 — skipping background init")
        # v0.5.14: still register rate-limit overrides — cheap, route-table
        # only, no DB or subprocess work.
        try:
            from .rate_limit_guard import eager_register_from_app

            eager_register_from_app(app)
        except Exception as exc:  # noqa: BLE001
            logger.warning("rate-limit eager registration skipped: %s", exc)
        return
    _init_database()
    # v0.7.13: auto-upgrade cliproxyapi if below minimum required version.
    # Don't block — log a warning on failure.
    try:
        from app.services.cliproxy_manager import CLIProxyManager

        ok, msg = CLIProxyManager.ensure_min_version()
        if ok:
            logger.info("cliproxyapi version check: %s", msg)
        else:
            logger.warning("cliproxyapi version check: %s", msg)
    except Exception:
        logger.warning("cliproxyapi version check raised", exc_info=True)
    # Guard non-critical startup steps: with workers=1, an unhandled exception
    # in on_startup kills the only worker → full boot outage. Backend detection
    # is best-effort and must not take the worker down. (_init_database above is
    # intentionally NOT guarded — a broken DB should fail startup loudly rather
    # than serve traffic.)
    try:
        _detect_backends()
    except Exception:
        logger.error("backend detection failed at startup; continuing", exc_info=True)
    # Wire WorkflowTriggerService into the execution_events channel —
    # decouples workflow_execution_service from importing the trigger service
    # directly (one-way runtime dep instead of two-way).
    try:
        from app.services.execution_events import register_completion_handler
        from app.services.workflow_trigger_service import WorkflowTriggerService

        register_completion_handler(WorkflowTriggerService.on_execution_complete)
    except Exception:
        logger.warning("execution_events handler registration failed", exc_info=True)
    # Life-Harness: failure annotator classifies EVERY completed session
    # (trigger executions, workflow nodes, super-agent sessions, project
    # sessions) into H2/H3/H4/general layers. Subscribes to the
    # session-scoped event channel so the annotator receives project_id
    # directly from the emitter.
    try:
        from app.services.execution_events import register_session_handler
        from app.services.harness_failure_annotator import on_session_complete

        register_session_handler(on_session_complete)
    except Exception:
        logger.warning("harness_failure_annotator registration failed", exc_info=True)
    # Takeaway extractor — the positive-learning counterpart to the
    # annotator. Fires on the same session-completion channel. Separate
    # try/except so an extractor failure doesn't take out the annotator.
    try:
        from app.services.execution_events import register_session_handler
        from app.services.harness_takeaway_extractor import (
            on_session_complete as on_takeaway_extract,
        )

        register_session_handler(on_takeaway_extract)
    except Exception:
        logger.warning("harness_takeaway_extractor registration failed", exc_info=True)
    # Tesserae integration — opt-in per project via
    # ``projects.tesserae_project_root``. Fires on every completed
    # session; cheap no-op for projects without the column set.
    # Independent try/except so a Tesserae CLI issue can't take down
    # the takeaway or annotator paths.
    try:
        from app.services.execution_events import register_session_handler
        from app.services.tesserae_integration import (
            on_session_complete as on_tesserae_export,
        )

        register_session_handler(on_tesserae_export)
    except Exception:
        logger.warning("tesserae_integration registration failed", exc_info=True)
    # Phase 17-06: session-completion auto-import of session-scaffolded forge
    # primitives. Diffs .claude/ vs the forge manifest and imports only
    # Agented-driven-session artifacts (session_kind gate fails CLOSED on
    # foreign/unknown kinds — the Phase 17 prompt-injection mitigation),
    # recording origin content-hash + source session id. Own try/except so an
    # import error can't take down the other three handlers or session
    # completion.
    try:
        from app.services.execution_events import register_session_handler
        from app.services.forge_session_import import on_session_complete_import

        register_session_handler(on_session_complete_import)
    except Exception:
        logger.warning("forge_session_import registration failed", exc_info=True)
    # Phase 22-03: repeated-request detector. A NEW handler that extracts the
    # user request from every completed session, embeds + cosine-matches it
    # (>=0.83) against existing signals, and UPSERTs into the 22-01 store —
    # accumulating recurrence evidence for the auto-skill gate. The module also
    # self-registers on import (idempotent); this explicit block keeps it
    # consistent with the other handlers and ensures startup import. Own
    # try/except so a detector failure can't take down the other handlers.
    try:
        from app.services.execution_events import register_session_handler
        from app.services.repeated_request_detector import on_session_complete_detect

        register_session_handler(on_session_complete_detect)
    except Exception:
        logger.warning("repeated_request_detector registration failed", exc_info=True)
    # Life-Harness: sweep stale /tmp/agented-claude-overlay-* dirs left
    # behind by crashes / SIGKILLs where the per-session finally block
    # didn't run. Best-effort; never blocks startup.
    try:
        from app.services.claude_config_overlay import cleanup_stale_overlays

        cleanup_stale_overlays()
    except Exception:
        logger.debug("claude overlay GC raised on startup", exc_info=True)
    # Pass `None` because SchedulerService.init expects a Flask-style object
    # only for testing-mode detection, which doesn't apply when Litestar
    # runs standalone. The service tolerates None via attribute getattr.
    try:
        _setup_scheduler(None)
    except Exception:
        logger.error("scheduler setup failed at startup; continuing", exc_info=True)
    try:
        _register_cleanup_handlers()
    except Exception:
        logger.error("cleanup handler registration failed at startup; continuing", exc_info=True)
    # v0.5.14: pre-populate the rate-limit override registry from the app's
    # route table so the very first cold request to a guarded path sees
    # the right limit (instead of the more permissive coarse default).
    try:
        from .rate_limit_guard import eager_register_from_app

        eager_register_from_app(app)
    except Exception as exc:  # noqa: BLE001
        logger.warning("rate-limit eager registration skipped: %s", exc)


def on_shutdown() -> None:
    """Best-effort process cleanup. atexit handlers cover most of this."""
    # Stop the APScheduler thread FIRST. It is a daemon thread, so it never
    # blocks exit by itself — but if anything else delays interpreter
    # teardown (e.g. a non-daemon worker still draining), a still-running
    # scheduler keeps firing into an executor pool whose workers were torn
    # down by concurrent.futures' interpreter-exit hook, spamming
    # "RuntimeError: cannot schedule new futures after shutdown" forever.
    # Cheap: BlockingScheduler.shutdown sets the wakeup event, so the
    # background-thread join returns immediately.
    try:
        from app.services.scheduler_service import SchedulerService

        SchedulerService.shutdown()
    except Exception:
        logger.debug("SchedulerService.shutdown failed during shutdown", exc_info=True)
    try:
        from app.services.process_manager import ProcessManager

        ProcessManager.cancel_all(timeout=10)
    except Exception:
        logger.debug("ProcessManager.cancel_all failed during shutdown", exc_info=True)
