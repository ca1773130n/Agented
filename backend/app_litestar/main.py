"""Litestar app factory.

The full Agented API surface — every route migrated from Flask in
waves 23–78 — plus the lifecycle hooks, middleware, CORS, and
exception handlers that took over from Flask in wave 80.
"""

from __future__ import annotations

import os

from litestar import Litestar
from litestar.config.cors import CORSConfig
from litestar.di import Provide

from .auth import provide_caller
from .exception_handlers import EXCEPTION_HANDLERS
from .lifecycle import on_shutdown, on_startup
from .middleware import (
    ApiKeyMiddleware,
    PerformanceMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    SlowRequestMiddleware,
)
from .routes.auth import auth_router
from .routes.metrics import metrics_router
from .routes.plugin_discovery import plugin_discovery_router
from .routes.bot_health import bot_health_router
from .routes.cliproxy_lifecycle import cliproxy_lifecycle_router
from .routes.health import health_router
from .routes.leaf_crud_a import (
    bookmarks_router,
    bot_memory_router,
    prompt_snippets_router,
    scope_filters_router,
    trigger_conditions_router,
)
from .routes.leaf_crud_b import (
    audit_router,
    integrations_router,
    marketplace_router,
    pr_reviews_router,
)
from .routes.leaf_crud_c import (
    analytics_router,
    config_export_router,
    findings_router,
    products_router,
    report_digests_router,
)
from .routes.leaf_crud_d import (
    campaigns_router,
    collaborative_router,
    execution_tagging_router,
    knowledge_graph_router,
    pr_assignment_router,
)
from .routes.leaf_crud_e import (
    bot_pipes_router,
    health_monitor_router,
    monitoring_router,
    onboarding_router,
    orchestration_router,
    project_instances_router,
    repo_bot_defaults_router,
)
from .routes.leaf_crud_f import (
    agent_memory_router,
    bulk_router,
    conversation_branches_router,
    replay_router,
)
from .routes.conversation_cluster import (
    command_conversations_router,
    hook_conversations_router,
    plugin_conversations_router,
    rule_conversations_router,
)
from .routes.leaf_crud_g import (
    agent_conversations_router,
    plugin_exports_router,
    sketches_router,
)
from .routes.executions import executions_router
from .routes.grd_routes import grd_router
from .routes.leaf_crud_i import (
    chunks_router,
    setup_router,
    super_agent_chat_router,
    super_agent_messages_router,
    team_generation_router,
)
from .routes.streams import (
    agent_conversation_stream_router,
    backends_stream_router,
    command_conversation_stream_router,
    execution_stream_router,
    hook_conversation_stream_router,
    plugin_conversation_stream_router,
    project_stream_router,
    rule_conversation_stream_router,
    setup_stream_router,
    super_agents_stream_router,
    teams_stream_router,
)
from .routes.webhooks import (
    github_webhook_router,
    oauth_callback_router,
    webhook_router,
)
from .routes.leaf_crud_h import (
    backends_router,
    utility_leftover_router,
)
from .routes.rbac import rbac_router
from .routes.admin_misc import admin_misc_router
from .routes.admin_tooling import (
    gitops_router,
    retention_router,
    secrets_router,
    settings_router,
    system_router,
    version_pins_router,
)
from .routes.agents_and_tracing import agents_router, tracing_router
from .routes.bot_templates import bot_templates_router
from .routes.budgets import budgets_router
from .routes.misc import misc_router
from .routes.mcp_servers import mcp_servers_router, project_mcp_router
from .routes.payload_transformers import payload_transformers_router
from .routes.product_owner import product_owner_router
from .routes.projects import projects_router
from .routes.quality_ratings import quality_ratings_router
from .routes.rules_plugins_hooks_commands import (
    commands_router,
    hooks_router,
    plugins_router,
    rules_router,
)
from .routes.model_cache import model_cache_router
from .routes.scheduler import scheduler_router
from .routes.super_agent_activity import super_agent_activity_router
from .routes.super_agents_cluster import (
    super_agent_exports_router,
    super_agents_router,
)
from .routes.skills import (
    skill_conversations_router,
    skill_sets_router,
    skills_router,
)
from .routes.teams import teams_router
from .routes.trigger_events import trigger_events_router
from .routes.triggers import triggers_router
from .routes.utility import utility_router
from .routes.auth_management import auth_management_router
from .routes.workflows import workflows_router


def _cors_config() -> CORSConfig:
    """Mirror Flask CORS: dev-localhost always allowed, env CSV widens."""
    allowed = [
        o.strip()
        for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
        if o.strip()
    ]
    for dev_origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
        if dev_origin not in allowed:
            allowed.append(dev_origin)
    return CORSConfig(
        allow_origins=allowed,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "X-Request-ID", "Authorization"],
        allow_credentials=True,
    )


def create_app() -> Litestar:
    """Build the Litestar application instance."""
    return Litestar(
        cors_config=_cors_config(),
        # Middleware order matters — outermost runs first on ingress and
        # last on egress. The choice below ensures:
        #   - RequestContext sets request_id BEFORE RateLimit/ApiKey can
        #     short-circuit, so 401/429 responses still carry an X-Request-ID
        #     header (and the helper body field).
        #   - RequestLogging wraps the inner middleware so 401/429 still get
        #     logged.
        #   - SecurityHeaders is innermost-of-the-cross-cutting layer so its
        #     header injection runs on every response (incl. handler 200s,
        #     401s, 429s) on the way back out.
        #   - v0.5.14: ApiKeyMiddleware runs BEFORE RateLimitMiddleware so
        #     scope["state"]["principal"] is populated when rate-limit
        #     resolves the per-user budget. Otherwise authed traffic
        #     silently falls back to per-IP keying.
        middleware=[
            RequestContextMiddleware(),
            RequestLoggingMiddleware(),
            SecurityHeadersMiddleware(),
            ApiKeyMiddleware(),
            RateLimitMiddleware(),
            # v0.6.0: emit Server-Timing on every response. Innermost so
            # the timing reflects the actual handler cost, not middleware
            # overhead.
            PerformanceMiddleware(),
            # v0.6.2: log WARN if a request exceeds the threshold.
            # Innermost-after-Performance so its timing matches.
            SlowRequestMiddleware(),
        ],
        exception_handlers=EXCEPTION_HANDLERS,
        on_startup=[on_startup],
        on_shutdown=[on_shutdown],
        route_handlers=[
            health_router,
            rbac_router,
            auth_router,
            auth_management_router,
            metrics_router,
            plugin_discovery_router,
            bot_health_router,
            cliproxy_lifecycle_router,
            utility_router,
            misc_router,
            admin_misc_router,
            bot_templates_router,
            budgets_router,
            quality_ratings_router,
            scheduler_router,
            triggers_router,
            trigger_events_router,
            payload_transformers_router,
            teams_router,
            projects_router,
            product_owner_router,
            mcp_servers_router,
            project_mcp_router,
            skill_conversations_router,
            skills_router,
            skill_sets_router,
            agents_router,
            tracing_router,
            rules_router,
            plugins_router,
            hooks_router,
            commands_router,
            workflows_router,
            super_agents_router,
            super_agent_activity_router,
            model_cache_router,
            super_agent_exports_router,
            settings_router,
            system_router,
            secrets_router,
            gitops_router,
            version_pins_router,
            retention_router,
            bookmarks_router,
            prompt_snippets_router,
            scope_filters_router,
            trigger_conditions_router,
            bot_memory_router,
            marketplace_router,
            integrations_router,
            audit_router,
            pr_reviews_router,
            products_router,
            analytics_router,
            findings_router,
            report_digests_router,
            config_export_router,
            knowledge_graph_router,
            collaborative_router,
            campaigns_router,
            execution_tagging_router,
            pr_assignment_router,
            monitoring_router,
            health_monitor_router,
            orchestration_router,
            onboarding_router,
            project_instances_router,
            repo_bot_defaults_router,
            bot_pipes_router,
            agent_memory_router,
            bulk_router,
            replay_router,
            conversation_branches_router,
            sketches_router,
            agent_conversations_router,
            plugin_exports_router,
            plugin_conversations_router,
            command_conversations_router,
            hook_conversations_router,
            rule_conversations_router,
            utility_leftover_router,
            backends_router,
            grd_router,
            executions_router,
            setup_router,
            super_agent_messages_router,
            team_generation_router,
            chunks_router,
            super_agent_chat_router,
            github_webhook_router,
            oauth_callback_router,
            webhook_router,
            execution_stream_router,
            plugin_conversation_stream_router,
            command_conversation_stream_router,
            hook_conversation_stream_router,
            rule_conversation_stream_router,
            agent_conversation_stream_router,
            project_stream_router,
            backends_stream_router,
            setup_stream_router,
            super_agents_stream_router,
            teams_stream_router,
        ],
        # provide_caller hits SQLite synchronously; tag it as non-blocking so
        # Litestar doesn't push it onto a thread pool every request.
        dependencies={"caller": Provide(provide_caller, sync_to_thread=False)},
    )
