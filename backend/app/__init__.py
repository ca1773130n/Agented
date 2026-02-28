"""Flask application factory with OpenAPI/Swagger UI configuration."""

import atexit
import hmac
import os
import secrets
import sqlite3
from pathlib import Path

from flask import jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_openapi3 import Info, OpenAPI
from flask_talisman import Talisman

from . import config as app_config

# Accumulated non-fatal startup warnings, exposed via /health/readiness
_startup_warnings: list = []

# API Info for OpenAPI spec
API_INFO = Info(
    title="Agented API",
    version="1.0.0",
    description="Bot management and security audit API for webhook automation",
)


def _get_secret_key() -> str:
    """Load SECRET_KEY from env, persisted file, or generate and persist.

    Priority:
    1. SECRET_KEY environment variable (set in .env or shell)
    2. .secret_key file in backend/ directory (auto-generated on first run)
    3. Generate new key, persist to .secret_key, return it
    """
    # 1. Environment variable (highest priority)
    key = os.environ.get("SECRET_KEY")
    if key:
        return key

    # 2. Persisted file fallback
    key_file = Path(__file__).parent.parent / ".secret_key"
    if key_file.exists():
        stored = key_file.read_text().strip()
        if stored:
            return stored

    # 3. Generate and persist for future restarts
    key = secrets.token_hex(32)
    try:
        key_file.write_text(key)
        key_file.chmod(0o600)  # Owner-readable only
    except OSError:
        pass  # Fallback: ephemeral key (not ideal but won't crash)
    return key


def create_app(config=None):
    """Create and configure the Flask application."""
    app = OpenAPI(__name__, info=API_INFO, doc_prefix="/docs")
    app.url_map.strict_slashes = False

    # Load configuration
    app.config.from_mapping(
        SECRET_KEY=_get_secret_key(),
        DATABASE=app_config.DB_PATH,
    )

    if config:
        app.config.from_mapping(config)

    testing = app.config.get("TESTING", False)

    # Enable CORS (fail-closed: empty list blocks all cross-origin when unset)
    allowed_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    allowed_origins = [o.strip() for o in allowed_origins if o.strip()]
    cors_config = {"origins": allowed_origins} if allowed_origins else {"origins": []}
    CORS(
        app,
        resources={
            r"/api/*": cors_config,
            r"/admin/*": cors_config,
            r"/health/*": {"origins": "*"},
            r"/docs/*": {"origins": "*"},
        },
        allow_headers=["Content-Type", "X-API-Key"],
    )

    # Security headers (SEC-01) — OWASP-aligned via flask-talisman
    # Initialize AFTER CORS so CORS headers are set first (no conflict — different headers)
    Talisman(
        app,
        force_https=os.environ.get("FORCE_HTTPS", "false").lower() == "true",
        frame_options="DENY",
        strict_transport_security=True,
        strict_transport_security_max_age=31536000,  # 1 year
        strict_transport_security_include_subdomains=True,
        content_security_policy={
            "default-src": "'self'",
            "script-src": ["'self'", "'unsafe-inline'"],  # Swagger UI needs inline scripts
            "style-src": ["'self'", "'unsafe-inline'"],  # Swagger UI needs inline styles
            "img-src": ["'self'", "data:"],
            "connect-src": ["'self'"],
        },
        content_security_policy_report_only=False,
        referrer_policy="strict-origin-when-cross-origin",
    )

    # Rate limiting (SEC-02) — in-memory storage safe for workers=1 (see gunicorn.conf.py)
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[],  # No global default — limits applied per-blueprint in Plan 02
        storage_uri="memory://",
        strategy="fixed-window",
    )
    # Store on app.extensions for blueprint-level access in register_blueprints()
    app.extensions["limiter"] = limiter

    # API key authentication middleware
    api_key = os.environ.get("AGENTED_API_KEY", "")

    # Paths that bypass authentication (public endpoints)
    _AUTH_BYPASS_PREFIXES = ("/health", "/docs", "/openapi", "/api/webhooks/github")

    @app.before_request
    def _require_api_key():
        # Auth disabled when AGENTED_API_KEY is not set (backward compatibility)
        if not api_key:
            return None

        # Allow CORS preflight requests through
        if request.method == "OPTIONS":
            return None

        # Root path bypass
        if request.path == "/":
            return None

        # Bypass paths
        for prefix in _AUTH_BYPASS_PREFIXES:
            if request.path == prefix or request.path.startswith(prefix + "/"):
                return None

        # Validate X-API-Key header
        provided_key = request.headers.get("X-API-Key", "")
        if not provided_key or not hmac.compare_digest(provided_key, api_key):
            return jsonify({"error": "Unauthorized"}), 401

        return None

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

        # Schedule periodic stale conversation cleanup (every 5 minutes)
        from .services.agent_conversation_service import AgentConversationService

        if SchedulerService._scheduler:
            SchedulerService._scheduler.add_job(
                func=AgentConversationService.cleanup_stale_conversations,
                trigger="interval",
                minutes=5,
                id="stale_conversation_cleanup",
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

            _sess_log.getLogger(__name__).error(
                "Project session cleanup failed on startup: %s", _cleanup_err, exc_info=True
            )
            _startup_warnings.append(f"project_session_cleanup: {_cleanup_err}")

        # Mark any workflow executions left as 'running' from previous server run as failed
        try:
            from .services.workflow_execution_service import WorkflowExecutionService

            WorkflowExecutionService.cleanup_stale_executions()
        except Exception as _wf_cleanup_err:
            import logging as _wf_log

            _wf_log.getLogger(__name__).error(
                "Workflow stale execution cleanup failed on startup: %s",
                _wf_cleanup_err,
                exc_info=True,
            )
            _startup_warnings.append(f"workflow_stale_cleanup: {_wf_cleanup_err}")

        # Restore any rate-limit retries that were pending when the server last restarted
        try:
            from .services.execution_service import ExecutionService

            ExecutionService.restore_pending_retries()
        except Exception as _retry_restore_err:
            import logging as _retry_log

            _retry_log.getLogger(__name__).error(
                "Pending retry restore failed on startup: %s", _retry_restore_err, exc_info=True
            )
            _startup_warnings.append(f"pending_retry_restore: {_retry_restore_err}")

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

            _log.getLogger(__name__).error(
                "CLIProxyManager initialization failed; proxy streaming will be unavailable: %s",
                proxy_init_err,
                exc_info=True,
            )

    # Register blueprints
    from .routes import register_blueprints

    register_blueprints(app)

    # Request ID middleware — generates UUID per request, propagates via
    # contextvars for structured logging, returns X-Request-ID header.
    from .middleware import init_request_middleware

    init_request_middleware(app)

    # Global JSON error handlers
    @app.errorhandler(404)
    def not_found(e):
        return {"error": "Not found"}, 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return {"error": "Method not allowed"}, 405

    @app.errorhandler(413)
    def payload_too_large(e):
        return {"error": "Payload too large"}, 413

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return {"error": f"Rate limit exceeded: {e.description}"}, 429

    @app.errorhandler(500)
    def internal_error(e):
        return {"error": "Internal server error"}, 500

    @app.errorhandler(sqlite3.OperationalError)
    def db_operational_error(e):
        import logging as _db_log

        _db_log.getLogger(__name__).error("Database operational error: %s", e, exc_info=True)
        return {"error": "Service temporarily unavailable"}, 503

    return app
