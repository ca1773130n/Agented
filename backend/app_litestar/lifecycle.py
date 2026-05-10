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
        existing = conn.execute(
            "SELECT id FROM super_agents WHERE id = 'sa-system'"
        ).fetchone()
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
    from app.services.instance_service import InstanceService
    from app.services.super_agent_session_service import SuperAgentSessionService

    init_db()
    seed_predefined_triggers()
    seed_preset_mcp_servers()
    seed_bot_templates()
    seed_bundled_teams_and_agents()
    _seed_bundled_marketplace()
    _seed_system_agent()
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

    grd_path = GrdCliService.detect_binary()
    if grd_path:
        logger.info("GRD binary detected: %s", grd_path)
    else:
        logger.warning(
            "GRD binary not found — GRD CLI write operations will be unavailable. "
            "Configure grd_binary_path in Agented settings or set CLAUDE_PLUGIN_ROOT env var."
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
        ]
        for func, interval_kwargs, job_id in periodic_jobs:
            SchedulerService._scheduler.add_job(
                func=func,
                trigger="interval",
                id=job_id,
                replace_existing=True,
                **interval_kwargs,
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
                logger.info(
                    "CLIProxyAPI global proxy started on port %d", CLIProxyManager._port
                )
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
    _detect_backends()
    # Pass `None` because SchedulerService.init expects a Flask-style object
    # only for testing-mode detection, which doesn't apply when Litestar
    # runs standalone. The service tolerates None via attribute getattr.
    _setup_scheduler(None)
    _register_cleanup_handlers()
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
    try:
        from app.services.process_manager import ProcessManager

        ProcessManager.cancel_all(timeout=10)
    except Exception:
        logger.debug("ProcessManager.cancel_all failed during shutdown", exc_info=True)
