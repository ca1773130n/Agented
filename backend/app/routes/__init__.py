"""API route blueprints."""


def register_blueprints(app):
    """Register all route blueprints with the Flask app."""
    from .activity_feed import activity_feed_bp
    from .agent_conversations import agent_conversations_bp
    from .agent_memory import agent_memory_bp
    from .agents import agents_bp
    from .analytics import analytics_bp
    from .cross_team_insights import cross_team_insights_bp
    from .audit import audit_bp
    from .backends import backends_bp
    from .bookmarks import bookmarks_bp
    from .bot_memory import bot_memory_bp
    from .bot_pipes import bot_pipes_bp
    from .bot_sla import bot_sla_bp
    from .bot_templates import bot_templates_bp
    from .payload_transformers import payload_transformers_bp
    from .budgets import budgets_bp
    from .bulk import bulk_bp
    from .campaigns import campaigns_bp
    from .chunks import chunks_bp
    from .collaborative import collaborative_bp
    from .command_conversations import command_conversations_bp
    from .commands import commands_bp
    from .config_export import config_export_bp
    from .conversation_branches import conversation_branches_bp
    from .execution_search import execution_search_bp
    from .execution_tagging import execution_tagging_bp
    from .executions import executions_bp
    from .findings import findings_bp
    from .github_webhook import github_webhook_bp
    from .oauth_callback import oauth_callback_bp
    from .onboarding import onboarding_bp
    from .trigger_conditions import trigger_conditions_bp
    from .gitops import gitops_bp
    from .grd import grd_bp
    from .health import health_bp
    from .health_monitor import health_monitor_bp
    from .hook_conversations import hook_conversations_bp
    from .hooks import hooks_bp
    from .integrations import integrations_bp, slack_command_bp
    from .marketplace import marketplace_bp
    from .mcp_servers import mcp_servers_bp, project_mcp_bp
    from .model_pricing import model_pricing_bp
    from .monitoring import monitoring_bp
    from .orchestration import orchestration_bp
    from .plugin_conversations import plugin_conversations_bp
    from .plugin_exports import plugin_exports_bp
    from .plugins import plugins_bp
    from .pr_assignment import pr_assignment_bp
    from .pr_reviews import pr_reviews_bp
    from .product_owner import product_owner_bp
    from .products import products_bp
    from .project_instances import project_instances_bp
    from .projects import projects_bp
    from .prompt_snippets import prompt_snippets_bp
    from .rbac import rbac_bp
    from .replay import replay_bp
    from .repo_bot_defaults import repo_bot_defaults_bp
    from .report_digests import report_digests_bp
    from .quality_ratings import quality_ratings_bp
    from .retention import retention_bp
    from .scope_filters import scope_filters_bp
    from .version_pins import version_pins_bp
    from .rotation import rotation_bp
    from .rule_conversations import rule_conversations_bp
    from .rules import rules_bp
    from .scheduler import scheduler_bp
    from .scheduling_suggestions import scheduling_bp
    from .secrets import secrets_bp
    from .settings import settings_bp
    from .setup import setup_bp
    from .sketches import sketches_bp
    from .skill_conversations import skill_conversations_bp
    from .skill_sets import skill_sets_bp
    from .skills import skills_bp
    from .spa import spa_bp
    from .specialized_bots import specialized_bots_bp
    from .system import system_bp
    from .super_agent_chat import super_agent_chat_bp
    from .super_agent_documents import super_agent_documents_bp
    from .super_agent_exports import super_agent_exports_bp
    from .super_agent_messages import super_agent_messages_bp
    from .super_agent_sessions import super_agent_sessions_bp
    from .super_agents import super_agents_bp
    from .team_assignments import team_assignments_bp
    from .team_connections import team_connections_bp
    from .team_edges import team_edges_bp
    from .team_generation import team_generation_bp
    from .team_members import team_members_bp
    from .teams import teams_bp
    from .tracing import tracing_bp
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

        # Slack slash commands: 30 requests per minute per IP
        limiter.limit("30/minute")(slack_command_bp)

        # Admin routes: 120 requests per minute per IP
        # Generous limit to accommodate SPA page loads, AJAX calls, and SSE reconnects
        # (See 04-RESEARCH.md Pitfall 4: tight limits break SSE EventSource reconnect)
        admin_blueprints = [
            triggers_bp,
            audit_bp,
            utility_bp,
            execution_search_bp,
            execution_tagging_bp,
            executions_bp,
            pr_assignment_bp,
            pr_reviews_bp,
            agents_bp,
            agent_conversations_bp,
            skills_bp,
            teams_bp,
            team_members_bp,
            team_connections_bp,
            team_assignments_bp,
            team_edges_bp,
            team_generation_bp,
            products_bp,
            project_instances_bp,
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
            analytics_bp,
            cross_team_insights_bp,
            plugin_exports_bp,
            monitoring_bp,
            scheduler_bp,
            setup_bp,
            super_agents_bp,
            super_agent_chat_bp,
            super_agent_documents_bp,
            super_agent_messages_bp,
            super_agent_sessions_bp,
            super_agent_exports_bp,
            workflows_bp,
            sketches_bp,
            gitops_bp,
            grd_bp,
            rotation_bp,
            mcp_servers_bp,
            project_mcp_bp,
            product_owner_bp,
            health_monitor_bp,
            scheduling_bp,
            rbac_bp,
            secrets_bp,
            config_export_bp,
            bookmarks_bp,
            integrations_bp,
            campaigns_bp,
            replay_bp,
            conversation_branches_bp,
            chunks_bp,
            collaborative_bp,
            bot_templates_bp,
            prompt_snippets_bp,
            specialized_bots_bp,
            bulk_bp,
            model_pricing_bp,
            activity_feed_bp,
            repo_bot_defaults_bp,
            findings_bp,
            bot_pipes_bp,
            bot_memory_bp,
            agent_memory_bp,
            bot_sla_bp,
            report_digests_bp,
            retention_bp,
            skill_sets_bp,
            onboarding_bp,
            scope_filters_bp,
            payload_transformers_bp,
            quality_ratings_bp,
            system_bp,
            tracing_bp,
        ]
        for bp in admin_blueprints:
            limiter.limit("120/minute")(bp)

        # Exempt health and oauth-callback from rate limiting
        # (04-RESEARCH.md: health probes must always respond)
        limiter.exempt(health_bp)
        limiter.exempt(oauth_callback_bp)

    # Register blueprints (AFTER rate limit decoration)
    app.register_api(health_bp)
    app.register_api(webhook_bp)
    app.register_api(github_webhook_bp)
    app.register_api(triggers_bp)
    app.register_api(audit_bp)
    app.register_api(utility_bp)
    app.register_api(execution_search_bp)
    app.register_api(execution_tagging_bp)
    app.register_api(executions_bp)
    app.register_api(pr_assignment_bp)
    app.register_api(pr_reviews_bp)
    app.register_api(trigger_conditions_bp)
    app.register_api(agents_bp)
    app.register_api(agent_conversations_bp)
    app.register_api(skills_bp)
    app.register_api(teams_bp)
    app.register_api(team_members_bp)
    app.register_api(team_connections_bp)
    app.register_api(team_assignments_bp)
    app.register_api(team_edges_bp)
    app.register_api(team_generation_bp)
    app.register_api(products_bp)
    app.register_api(projects_bp)
    app.register_api(project_instances_bp)
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
    app.register_api(analytics_bp)
    app.register_api(cross_team_insights_bp)
    app.register_api(plugin_exports_bp)
    app.register_api(monitoring_bp)
    app.register_api(scheduler_bp)
    app.register_api(setup_bp)
    app.register_api(super_agents_bp)
    app.register_api(super_agent_chat_bp)
    app.register_api(super_agent_documents_bp)
    app.register_api(super_agent_messages_bp)
    app.register_api(super_agent_sessions_bp)
    app.register_api(super_agent_exports_bp)
    app.register_api(workflows_bp)
    app.register_api(sketches_bp)
    app.register_api(gitops_bp)
    app.register_api(grd_bp)
    app.register_api(rotation_bp)
    app.register_api(mcp_servers_bp)
    app.register_api(project_mcp_bp)
    app.register_api(product_owner_bp)
    app.register_api(health_monitor_bp)
    app.register_api(scheduling_bp)
    app.register_api(rbac_bp)
    app.register_api(secrets_bp)
    app.register_api(config_export_bp)
    app.register_api(bookmarks_bp)
    app.register_api(integrations_bp)
    app.register_api(slack_command_bp)
    app.register_api(campaigns_bp)
    app.register_api(replay_bp)
    app.register_api(conversation_branches_bp)
    app.register_api(chunks_bp)
    app.register_api(collaborative_bp)
    app.register_api(bot_templates_bp)
    app.register_api(prompt_snippets_bp)
    app.register_api(specialized_bots_bp)
    app.register_api(bulk_bp)
    app.register_api(model_pricing_bp)
    app.register_api(activity_feed_bp)
    app.register_api(repo_bot_defaults_bp)
    app.register_api(quality_ratings_bp)
    app.register_api(scope_filters_bp)
    app.register_api(version_pins_bp)
    app.register_api(findings_bp)
    app.register_api(bot_pipes_bp)
    app.register_api(bot_memory_bp)
    app.register_api(agent_memory_bp)
    app.register_api(retention_bp)
    app.register_api(skill_sets_bp)
    app.register_api(onboarding_bp)
    app.register_api(payload_transformers_bp)
    app.register_api(system_bp)
    app.register_api(bot_sla_bp)
    app.register_api(report_digests_bp)
    app.register_api(tracing_bp)
    app.register_api(oauth_callback_bp)

    # SPA catch-all: MUST be registered LAST so API routes take priority
    app.register_blueprint(spa_bp)
