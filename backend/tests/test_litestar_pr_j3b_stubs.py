"""PR-J3b: 501 stubs for the 17 STUB-DEFER frontend views shipped in PR-J3.

Each test asserts the backend returns 501 ("Feature not yet enabled") on the
path the view calls. The frontend banner reads from a `FEATURE_ENABLED=false`
constant; flipping the constant once the real handler ships is the
single-line follow-up.
"""

from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.agents_and_tracing import agents_router
from app_litestar.routes.bot_templates import bot_stubs_router
from app_litestar.routes.executions import executions_router
from app_litestar.routes.integrations import integrations_github_router
from app_litestar.routes.leaf_crud_b import integrations_router
from app_litestar.routes.misc import misc_router
from app_litestar.routes.rules_plugins_hooks_commands import plugins_router
from app_litestar.routes.skills import skill_composer_router


def _client(*handlers):
    return create_test_client(
        route_handlers=list(handlers),
        dependencies={"caller": provide_caller},
    )


# AgentCapabilityMatrix.vue --------------------------------------------------


def test_agent_capabilities_returns_501(isolated_db):
    with _client(agents_router) as c:
        assert c.get("/admin/agents/capabilities").status_code == 501


# BotSandboxPage.vue ---------------------------------------------------------


def test_list_sandboxes_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.get("/admin/sandboxes").status_code == 501


def test_create_sandbox_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.post("/admin/sandboxes", json={}).status_code == 501


# CodeExplanationBotPage.vue -------------------------------------------------


def test_list_code_explanations_returns_501(isolated_db):
    with _client(bot_stubs_router) as c:
        assert c.get("/admin/bots/code-explanations").status_code == 501


def test_create_code_explanation_returns_501(isolated_db):
    with _client(bot_stubs_router) as c:
        assert c.post("/admin/bots/code-explanations", json={}).status_code == 501


# CrossRepoImpactBotPage.vue -------------------------------------------------


def test_list_cross_repo_impact_returns_501(isolated_db):
    with _client(bot_stubs_router) as c:
        assert c.get("/admin/bots/cross-repo-impact").status_code == 501


def test_create_cross_repo_impact_returns_501(isolated_db):
    with _client(bot_stubs_router) as c:
        assert c.post("/admin/bots/cross-repo-impact", json={}).status_code == 501


# TestCoverageBot.vue --------------------------------------------------------


def test_get_test_coverage_config_returns_501(isolated_db):
    with _client(bot_stubs_router) as c:
        assert c.get("/admin/bots/test-coverage/config").status_code == 501


def test_set_test_coverage_config_returns_501(isolated_db):
    with _client(bot_stubs_router) as c:
        assert c.post("/admin/bots/test-coverage/config", json={}).status_code == 501


# DataRetentionPoliciesPage.vue ---------------------------------------------


def test_retention_stub_get_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.get("/admin/retention").status_code == 501


def test_retention_stub_post_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.post("/admin/retention", json={}).status_code == 501


# ExecutionArtifactsPage.vue -------------------------------------------------


def test_execution_artifacts_returns_501(isolated_db):
    with _client(executions_router) as c:
        assert c.get("/admin/executions/artifacts").status_code == 501


# GitHubAppInstallPage.vue ---------------------------------------------------


def test_github_installations_returns_501(isolated_db):
    with _client(integrations_github_router) as c:
        assert c.get("/admin/integrations/github/installations").status_code == 501


def test_github_install_returns_501(isolated_db):
    with _client(integrations_github_router) as c:
        assert c.post("/admin/integrations/github/install", json={}).status_code == 501


# NotificationHubPage.vue ----------------------------------------------------


def test_notifications_get_config_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.get("/admin/notifications/config").status_code == 501


def test_notifications_put_config_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.put("/admin/notifications/config", json={}).status_code == 501


def test_notifications_test_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.post("/admin/notifications/test", json={}).status_code == 501


# OnboardingAutomationPage.vue (real /admin/onboarding/* exists; only the
# higher-level "automate" endpoint is stubbed) ------------------------------


def test_onboarding_automate_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.post("/admin/onboarding/automate", json={}).status_code == 501


# PluginSandboxPage.vue ------------------------------------------------------


def test_plugin_sandbox_runs_returns_501(isolated_db):
    with _client(plugins_router) as c:
        assert c.get("/admin/plugins/sandbox/runs").status_code == 501


def test_plugin_sandbox_run_returns_501(isolated_db):
    with _client(plugins_router) as c:
        assert c.post("/admin/plugins/sandbox/run", json={}).status_code == 501


# PromptLocalizationPage.vue -------------------------------------------------


def test_prompt_localization_list_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.get("/admin/prompt-localization").status_code == 501


def test_prompt_localization_create_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.post("/admin/prompt-localization", json={}).status_code == 501


def test_prompt_localization_translate_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.post("/admin/prompt-localization/translate", json={}).status_code == 501


# SlackCommandGatewayPage.vue ------------------------------------------------


def test_slack_commands_list_returns_501(isolated_db):
    with _client(integrations_router) as c:
        assert c.get("/admin/integrations/slack/commands").status_code == 501


def test_slack_commands_create_returns_501(isolated_db):
    with _client(integrations_router) as c:
        assert c.post("/admin/integrations/slack/commands", json={}).status_code == 501


def test_slack_commands_update_returns_501(isolated_db):
    with _client(integrations_router) as c:
        assert c.put("/admin/integrations/slack/commands/abc", json={}).status_code == 501


def test_slack_commands_delete_returns_501(isolated_db):
    with _client(integrations_router) as c:
        assert c.delete("/admin/integrations/slack/commands/abc").status_code == 501


# SmartAlertRulesPage.vue ----------------------------------------------------


def test_alert_rules_list_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.get("/admin/alerts/rules").status_code == 501


def test_alert_rules_create_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.post("/admin/alerts/rules", json={}).status_code == 501


def test_alert_rules_update_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.put("/admin/alerts/rules/r-x", json={}).status_code == 501


def test_alert_rules_delete_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.delete("/admin/alerts/rules/r-x").status_code == 501


# SmartScheduleOptimizerPage.vue ---------------------------------------------


def test_schedule_optimizer_get_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.get("/admin/schedule-optimizer").status_code == 501


def test_schedule_optimizer_optimize_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.post("/admin/schedule-optimizer/optimize", json={}).status_code == 501


# TeamActivityFeedPage.vue ---------------------------------------------------


def test_team_activity_feed_returns_501(isolated_db):
    with _client(misc_router) as c:
        assert c.get("/admin/activity-feed?team=t-x").status_code == 501


# VisualSkillComposerPage.vue ------------------------------------------------


def test_skill_composer_list_returns_501(isolated_db):
    with _client(skill_composer_router) as c:
        assert c.get("/admin/skills/composer/").status_code == 501


def test_skill_composer_create_returns_501(isolated_db):
    with _client(skill_composer_router) as c:
        assert c.post("/admin/skills/composer/", json={}).status_code == 501


def test_skill_composer_update_returns_501(isolated_db):
    with _client(skill_composer_router) as c:
        assert c.put("/admin/skills/composer/sc-1", json={}).status_code == 501


def test_skill_composer_delete_returns_501(isolated_db):
    with _client(skill_composer_router) as c:
        assert c.delete("/admin/skills/composer/sc-1").status_code == 501
