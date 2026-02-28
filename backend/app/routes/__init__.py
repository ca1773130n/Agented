"""API route blueprints."""


def register_blueprints(app):
    """Register all route blueprints with the Flask app."""
    from .agent_conversations import agent_conversations_bp
    from .agents import agents_bp
    from .audit import audit_bp
    from .backends import backends_bp
    from .budgets import budgets_bp
    from .command_conversations import command_conversations_bp
    from .commands import commands_bp
    from .executions import executions_bp
    from .github_webhook import github_webhook_bp
    from .grd import grd_bp
    from .health import health_bp
    from .hook_conversations import hook_conversations_bp
    from .hooks import hooks_bp
    from .marketplace import marketplace_bp
    from .mcp_servers import mcp_servers_bp, project_mcp_bp
    from .monitoring import monitoring_bp
    from .orchestration import orchestration_bp
    from .plugin_conversations import plugin_conversations_bp
    from .plugin_exports import plugin_exports_bp
    from .plugins import plugins_bp
    from .pr_reviews import pr_reviews_bp
    from .product_owner import product_owner_bp
    from .products import products_bp
    from .projects import projects_bp
    from .rotation import rotation_bp
    from .rule_conversations import rule_conversations_bp
    from .rules import rules_bp
    from .scheduler import scheduler_bp
    from .settings import settings_bp
    from .setup import setup_bp
    from .sketches import sketches_bp
    from .skill_conversations import skill_conversations_bp
    from .skills import skills_bp
    from .spa import spa_bp
    from .super_agent_exports import super_agent_exports_bp
    from .super_agents import super_agents_bp
    from .teams import teams_bp
    from .triggers import triggers_bp
    from .utility import utility_bp
    from .webhook import webhook_bp
    from .workflows import workflows_bp

    # --- Rate limiting (SEC-02) ---
    # Apply rate limits BEFORE blueprint registration (flask-limiter official pattern).
    # Retrieve limiter from app extensions (initialized in create_app by Plan 01)
    limiter = app.extensions.get("limiter")
    if limiter:
        # Webhook ingestion: 20 requests per 10 seconds per IP
        # Success criteria: 21st request within 10s returns HTTP 429
        limiter.limit("20/10seconds")(webhook_bp)

        # GitHub webhook: 30 requests per minute per IP
        limiter.limit("30/minute")(github_webhook_bp)

        # Admin routes: 120 requests per minute per IP
        # Generous limit to accommodate SPA page loads, AJAX calls, and SSE reconnects
        # (See 04-RESEARCH.md Pitfall 4: tight limits break SSE EventSource reconnect)
        admin_blueprints = [
            triggers_bp,
            audit_bp,
            utility_bp,
            executions_bp,
            pr_reviews_bp,
            agents_bp,
            agent_conversations_bp,
            skills_bp,
            teams_bp,
            products_bp,
            projects_bp,
            plugins_bp,
            marketplace_bp,
            settings_bp,
            hooks_bp,
            commands_bp,
            rules_bp,
            skill_conversations_bp,
            plugin_conversations_bp,
            hook_conversations_bp,
            command_conversations_bp,
            rule_conversations_bp,
            backends_bp,
            orchestration_bp,
            budgets_bp,
            plugin_exports_bp,
            monitoring_bp,
            scheduler_bp,
            setup_bp,
            super_agents_bp,
            super_agent_exports_bp,
            workflows_bp,
            sketches_bp,
            grd_bp,
            rotation_bp,
            mcp_servers_bp,
            project_mcp_bp,
            product_owner_bp,
        ]
        for bp in admin_blueprints:
            limiter.limit("120/minute")(bp)

        # Exempt health from rate limiting
        # (04-RESEARCH.md: health probes must always respond)
        limiter.exempt(health_bp)

    # Register blueprints (AFTER rate limit decoration)
    app.register_api(health_bp)
    app.register_api(webhook_bp)
    app.register_api(github_webhook_bp)
    app.register_api(triggers_bp)
    app.register_api(audit_bp)
    app.register_api(utility_bp)
    app.register_api(executions_bp)
    app.register_api(pr_reviews_bp)
    app.register_api(agents_bp)
    app.register_api(agent_conversations_bp)
    app.register_api(skills_bp)
    app.register_api(teams_bp)
    app.register_api(products_bp)
    app.register_api(projects_bp)
    app.register_api(plugins_bp)
    app.register_api(marketplace_bp)
    app.register_api(settings_bp)
    app.register_api(hooks_bp)
    app.register_api(commands_bp)
    app.register_api(rules_bp)
    app.register_api(skill_conversations_bp)
    app.register_api(plugin_conversations_bp)
    app.register_api(hook_conversations_bp)
    app.register_api(command_conversations_bp)
    app.register_api(rule_conversations_bp)
    app.register_api(backends_bp)
    app.register_api(orchestration_bp)
    app.register_api(budgets_bp)
    app.register_api(plugin_exports_bp)
    app.register_api(monitoring_bp)
    app.register_api(scheduler_bp)
    app.register_api(setup_bp)
    app.register_api(super_agents_bp)
    app.register_api(super_agent_exports_bp)
    app.register_api(workflows_bp)
    app.register_api(sketches_bp)
    app.register_api(grd_bp)
    app.register_api(rotation_bp)
    app.register_api(mcp_servers_bp)
    app.register_api(project_mcp_bp)
    app.register_api(product_owner_bp)

    # SPA catch-all: MUST be registered LAST so API routes take priority
    app.register_blueprint(spa_bp)
