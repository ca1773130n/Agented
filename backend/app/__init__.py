"""Flask application factory with OpenAPI/Swagger UI configuration."""

import atexit
import os
import secrets

from flask_cors import CORS
from flask_openapi3 import Info, OpenAPI

from . import config as app_config

# API Info for OpenAPI spec
API_INFO = Info(
    title="Agented API",
    version="1.0.0",
    description="Bot management and security audit API for webhook automation",
)


def create_app(config=None):
    """Create and configure the Flask application."""
    app = OpenAPI(__name__, info=API_INFO, doc_prefix="/docs")
    app.url_map.strict_slashes = False

    # Load configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=app_config.DB_PATH,
    )

    if config:
        app.config.from_mapping(config)

    testing = app.config.get("TESTING", False)

    # Enable CORS
    allowed_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    allowed_origins = [o.strip() for o in allowed_origins if o.strip()]
    cors_config = {"origins": allowed_origins} if allowed_origins else {"origins": "*"}
    CORS(
        app,
        resources={
            r"/api/*": cors_config,
            r"/admin/*": cors_config,
            r"/health/*": {"origins": "*"},
            r"/docs/*": {"origins": "*"},
        },
    )

    # In testing mode, DB init is handled by the isolated_db fixture and
    # background services are not needed.
    if not testing:
        # Initialize database
        from .database import (
            auto_register_project_root,
            init_db,
            migrate_existing_paths,
            seed_predefined_triggers,
            seed_preset_mcp_servers,
        )

        init_db()
        seed_predefined_triggers()
        seed_preset_mcp_servers()
        migrate_existing_paths()
        auto_register_project_root()

        # Detect GRD binary for CLI write operations
        from .services.grd_cli_service import GrdCliService

        grd_path = GrdCliService.detect_binary()
        if grd_path:
            import logging as _grd_log

            _grd_log.getLogger(__name__).info(f"GRD binary detected: {grd_path}")
        else:
            import logging as _grd_log

            _grd_log.getLogger(__name__).warning(
                "GRD binary not found — GRD CLI write operations will be unavailable. "
                "Configure grd_binary_path in Agented settings or set CLAUDE_PLUGIN_ROOT env var."
            )

        # Clear model discovery cache on every startup — always rediscover fresh
        from .services.model_discovery_service import ModelDiscoveryService

        ModelDiscoveryService.clear_cache()

        # Initialize scheduler for scheduled triggers
        from .services.scheduler_service import SchedulerService

        SchedulerService.init(app)

        # Initialize monitoring service (depends on SchedulerService)
        from .services.monitoring_service import MonitoringService

        MonitoringService.init()

        # Schedule periodic session usage collection (every 10 minutes)
        from .services.session_collection_service import SessionCollectionService

        if SchedulerService._scheduler:
            SchedulerService._scheduler.add_job(
                func=SessionCollectionService.collect_all,
                trigger="interval",
                minutes=10,
                id="session_usage_collection",
                replace_existing=True,
            )

        # Schedule periodic repo sync (every 30 minutes)
        from .services.project_workspace_service import ProjectWorkspaceService

        if SchedulerService._scheduler:
            SchedulerService._scheduler.add_job(
                func=ProjectWorkspaceService.sync_all_repos,
                trigger="interval",
                minutes=30,
                id="project_repo_sync",
                replace_existing=True,
            )

        # Initialize agent execution scheduler (depends on MonitoringService)
        from .services.agent_scheduler_service import AgentSchedulerService

        AgentSchedulerService.init()

        # Initialize rotation evaluator (depends on MonitoringService + AgentSchedulerService)
        from .services.rotation_evaluator import RotationEvaluator

        RotationEvaluator.init()

        # Clean up dead project sessions from previous server run
        try:
            from .services.project_session_manager import ProjectSessionManager

            ProjectSessionManager.cleanup_dead_sessions()
        except Exception as _cleanup_err:
            import logging as _sess_log

            _sess_log.getLogger(__name__).warning(
                "Project session cleanup failed on startup: %s", _cleanup_err
            )

        # Initialize agent message bus (TTL sweep background worker)
        from .services.agent_message_bus_service import AgentMessageBusService

        AgentMessageBusService.start()
        atexit.register(AgentMessageBusService.stop)

        # Initialize CLIProxyAPI manager (single global instance)
        try:
            import logging as _log

            _proxy_log = _log.getLogger(__name__)
            from .services.cliproxy_manager import CLIProxyManager

            # Kill orphan cliproxyapi processes from previous runs
            CLIProxyManager.kill_orphans()

            # Auto-refresh expired OAuth tokens before starting the proxy
            try:
                refresh_result = CLIProxyManager.refresh_expired_tokens(timeout_per_account=45)
                refreshed = refresh_result.get("refreshed", [])
                failed = refresh_result.get("failed", [])
                if refreshed:
                    _proxy_log.info("Refreshed %d expired token(s): %s", len(refreshed), refreshed)
                if failed:
                    _proxy_log.warning("Failed to refresh %d token(s): %s", len(failed), failed)
            except Exception as refresh_err:
                _proxy_log.warning("Token auto-refresh skipped: %s", refresh_err)

            # Install cliproxyapi if not available, then start global proxy
            if CLIProxyManager.install_if_needed():
                if CLIProxyManager.start():
                    _proxy_log.info(
                        "CLIProxyAPI global proxy started on port %d", CLIProxyManager._port
                    )
                else:
                    _proxy_log.info("CLIProxyAPI not started (no config or not ready)")
                atexit.register(CLIProxyManager.stop)
            else:
                _proxy_log.info("CLIProxyAPI binary not available -- proxy streaming disabled")
        except Exception as proxy_init_err:
            import logging as _log

            _log.getLogger(__name__).warning(
                "CLIProxyManager initialization skipped: %s", proxy_init_err
            )

    # Register blueprints
    from .routes import register_blueprints

    register_blueprints(app)

    # Global JSON error handlers
    @app.errorhandler(404)
    def not_found(e):
        return {"error": "Not found"}, 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return {"error": "Method not allowed"}, 405

    @app.errorhandler(500)
    def internal_error(e):
        return {"error": "Internal server error"}, 500

    return app
