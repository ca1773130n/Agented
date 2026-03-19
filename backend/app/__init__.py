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


def _configure_cors(app) -> None:
    """Configure CORS — fail-closed: empty list blocks all cross-origin when unset."""
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


def _init_database(app) -> None:  # noqa: ARG001 — app reserved for future config reads
    """Initialize database tables, run migrations, and seed preset data."""
    from .database import (
        auto_register_project_root,
        init_db,
        migrate_existing_paths,
        seed_bot_templates,
        seed_predefined_triggers,
        seed_preset_mcp_servers,
    )
    from .db.bundle_seeds import seed_bundled_teams_and_agents

    from .services.instance_service import InstanceService
    from .services.super_agent_session_service import SuperAgentSessionService

    init_db()
    seed_predefined_triggers()
    seed_preset_mcp_servers()
    seed_bot_templates()
    seed_bundled_teams_and_agents()
    _seed_system_agent()
    migrate_existing_paths()
    auto_register_project_root()
    InstanceService.ensure_worktrees()
    SuperAgentSessionService.restore_active_sessions()


def _seed_system_agent():
    """Seed the sa-system super agent for automated error diagnosis."""
    from .db.connection import get_connection

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


def _detect_backends() -> None:
    """Detect backend CLIs and log warnings for any that are missing."""
    from .services.backend_detection_service import BACKEND_CAPABILITIES, detect_backend

    for _bt in BACKEND_CAPABILITIES:
        _inst, _ver, _ = detect_backend(_bt)
        if not _inst:
            _startup_warnings.append(f"cli_missing:{_bt}")

    import logging as _grd_log

    from .services.grd_cli_service import GrdCliService

    _log = _grd_log.getLogger(__name__)
    grd_path = GrdCliService.detect_binary()
    if grd_path:
        _log.info(f"GRD binary detected: {grd_path}")
    else:
        _log.warning(
            "GRD binary not found — GRD CLI write operations will be unavailable. "
            "Configure grd_binary_path in Agented settings or set CLAUDE_PLUGIN_ROOT env var."
        )


def _setup_scheduler(app) -> None:
    """Initialize the APScheduler and register all periodic jobs."""
    from .services.scheduler_service import SchedulerService

    SchedulerService.init(app)

    _init_monitoring_services()
    _register_periodic_jobs(SchedulerService)
    _init_auxiliary_schedulers()


def _init_monitoring_services() -> None:
    """Initialize monitoring and health check services."""
    from .services.health_monitor_service import HealthMonitorService
    from .services.monitoring_service import MonitoringService

    MonitoringService.init()
    HealthMonitorService.init()


def _register_periodic_jobs(scheduler_service) -> None:
    """Register interval-based background jobs with the scheduler.

    Each entry is (callable, trigger_kwargs, job_id).  Jobs are only registered
    when the underlying APScheduler instance is available.
    """
    if not scheduler_service._scheduler:
        return

    from .db.webhook_dedup import cleanup_expired_keys
    from .services.agent_conversation_service import AgentConversationService
    from .services.project_workspace_service import ProjectWorkspaceService
    from .services.session_collection_service import SessionCollectionService

    periodic_jobs = [
        (SessionCollectionService.collect_all, {"minutes": 10}, "session_usage_collection"),
        (ProjectWorkspaceService.sync_all_repos, {"minutes": 30}, "project_repo_sync"),
        (
            AgentConversationService.cleanup_stale_conversations,
            {"minutes": 5},
            "stale_conversation_cleanup",
        ),
        (cleanup_expired_keys, {"seconds": 60}, "webhook_dedup_cleanup"),
    ]

    for func, interval_kwargs, job_id in periodic_jobs:
        scheduler_service._scheduler.add_job(
            func=func,
            trigger="interval",
            id=job_id,
            replace_existing=True,
            **interval_kwargs,
        )


def _init_auxiliary_schedulers() -> None:
    """Initialize agent scheduler and rotation evaluator services."""
    from .services.agent_scheduler_service import AgentSchedulerService
    from .services.rotation_evaluator import RotationEvaluator

    AgentSchedulerService.init()
    RotationEvaluator.init()


def _register_cleanup_handlers() -> None:
    """Register startup cleanup handlers and background service shutdown hooks."""
    import logging as _log

    _sess_log = _log.getLogger(__name__)

    try:
        from .services.project_session_manager import ProjectSessionManager

        ProjectSessionManager.cleanup_dead_sessions()
    except Exception as _cleanup_err:
        _sess_log.error(
            "Project session cleanup failed on startup: %s", _cleanup_err, exc_info=True
        )
        _startup_warnings.append(f"project_session_cleanup: {_cleanup_err}")

    try:
        from .services.workflow_execution_service import WorkflowExecutionService

        WorkflowExecutionService.cleanup_stale_executions()
    except Exception as _wf_cleanup_err:
        _sess_log.error(
            "Workflow stale execution cleanup failed on startup: %s",
            _wf_cleanup_err,
            exc_info=True,
        )
        _startup_warnings.append(f"workflow_stale_cleanup: {_wf_cleanup_err}")

    try:
        from .services.execution_service import ExecutionService

        ExecutionService.restore_pending_retries()
    except Exception as _retry_restore_err:
        _sess_log.error(
            "Pending retry restore failed on startup: %s", _retry_restore_err, exc_info=True
        )
        _startup_warnings.append(f"pending_retry_restore: {_retry_restore_err}")

    from .services.execution_queue_service import ExecutionQueueService

    ExecutionQueueService.start_dispatcher()
    atexit.register(ExecutionQueueService.stop_dispatcher)

    from .services.agent_message_bus_service import AgentMessageBusService

    AgentMessageBusService.start()
    atexit.register(AgentMessageBusService.stop)

    _proxy_log = _log.getLogger(__name__)
    try:
        from .services.cliproxy_manager import CLIProxyManager

        CLIProxyManager.kill_orphans()

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
        _proxy_log.error(
            "CLIProxyManager initialization failed; proxy streaming will be unavailable: %s",
            proxy_init_err,
            exc_info=True,
        )


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

    _configure_cors(app)

    # Paths that bypass authentication (public endpoints)
    _AUTH_BYPASS_PREFIXES = ("/health", "/docs", "/openapi", "/api/webhooks/github")

    @app.before_request
    def _require_api_key():
        # Read API key per-request so changes take effect without restart
        api_key = os.environ.get("AGENTED_API_KEY", "")

        # Auth disabled when AGENTED_API_KEY is not set (backward compatibility)
        if not api_key:
            return None

        # Allow CORS preflight requests through
        if request.method == "OPTIONS":
            return None

        # Only enforce auth on /admin and /api routes
        if not (request.path.startswith("/admin") or request.path.startswith("/api")):
            return None

        # Bypass paths (specific /api sub-paths that are public)
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
        _init_database(app)
        _detect_backends()
        _setup_scheduler(app)
        _register_cleanup_handlers()

    # Register blueprints
    from .routes import register_blueprints

    register_blueprints(app)

    # Request ID middleware — generates UUID per request, propagates via
    # contextvars for structured logging, returns X-Request-ID header.
    from .middleware import init_request_middleware

    init_request_middleware(app)

    # Global JSON error handlers — unified ErrorResponse shape (API-02)
    from http import HTTPStatus

    from .models.common import error_response

    @app.errorhandler(404)
    def not_found(e):
        return error_response("NOT_FOUND", "Not found", HTTPStatus.NOT_FOUND)

    @app.errorhandler(405)
    def method_not_allowed(e):
        return error_response(
            "METHOD_NOT_ALLOWED", "Method not allowed", HTTPStatus.METHOD_NOT_ALLOWED
        )

    @app.errorhandler(413)
    def payload_too_large(e):
        return error_response(
            "PAYLOAD_TOO_LARGE", "Payload too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        )

    @app.errorhandler(429)
    def ratelimit_handler(e):
        body, status = error_response(
            "RATE_LIMITED",
            f"Rate limit exceeded: {e.description}",
            HTTPStatus.TOO_MANY_REQUESTS,
        )
        response = jsonify(body)
        response.status_code = status
        # Extract Retry-After from the rate limit window.
        # Flask-Limiter's RateLimitExceeded carries the limit info; we use the
        # window expiry as the Retry-After value so clients know when to retry.
        retry_seconds = None
        limit_obj = getattr(e, "limit", None)
        if limit_obj is not None:
            # RuntimeLimit wraps the parsed limit; .limit is the limits.RateLimitItem
            inner = getattr(limit_obj, "limit", None)
            if inner and hasattr(inner, "get_expiry"):
                retry_seconds = inner.get_expiry()
        if retry_seconds:
            response.headers["Retry-After"] = str(int(retry_seconds))
        return response

    @app.errorhandler(500)
    def internal_error(e):
        # Inspect the original exception for more specific error codes.
        # Flask wraps unhandled exceptions in an HTTPException; unwrap if possible.
        original = getattr(e, "original_exception", e)

        # Capture all 500 errors
        try:
            import traceback as _tb

            from app.services.error_capture import capture_error

            tb_str = (
                "".join(_tb.format_exception(type(original), original, original.__traceback__))
                if hasattr(original, "__traceback__") and original.__traceback__
                else None
            )
            capture_error(category="runtime_error", message=str(original), stack_trace=tb_str)
        except Exception:
            pass  # Never let error capture break error handling

        if isinstance(original, ValueError):
            return error_response(
                "VALIDATION_ERROR",
                f"Validation failed: {original}",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        if isinstance(original, PermissionError):
            return error_response(
                "FORBIDDEN",
                "Permission denied",
                HTTPStatus.FORBIDDEN,
            )
        if isinstance(original, sqlite3.IntegrityError):
            return error_response(
                "CONFLICT",
                "Resource conflict: a record with this identifier already exists",
                HTTPStatus.CONFLICT,
            )
        if isinstance(original, sqlite3.OperationalError):
            return error_response(
                "SERVICE_UNAVAILABLE",
                "Database unavailable, please retry",
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        return error_response(
            "INTERNAL_SERVER_ERROR", "Internal server error", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    @app.errorhandler(sqlite3.OperationalError)
    def db_operational_error(e):
        import logging as _db_log

        _db_log.getLogger(__name__).error("Database operational error: %s", e, exc_info=True)
        try:
            from app.services.error_capture import capture_error

            capture_error(category="db_error", message=str(e))
        except Exception:
            pass
        return error_response(
            "SERVICE_UNAVAILABLE",
            "Service temporarily unavailable",
            HTTPStatus.SERVICE_UNAVAILABLE,
        )

    return app
