"""Single-route migrations batched into one router (track A, wave 48).

Each route is a thin wrapper around an existing service / db helper.
Grouping them here avoids the per-namespace ceremony cost — the
playbook says "batch by namespace" but for tiny single-route files
the right namespace is `misc`.
"""

from __future__ import annotations

from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import ClientException, HTTPException

from app.db.audit_events import count_audit_events, query_audit_events
from app.db.cross_team_insights import get_cross_team_insights
from app.services.scheduling_suggestion_service import SchedulingSuggestionService
from app.services.session_cost_service import _PRICING


def _map_action_to_type(action: str, outcome: str) -> str:
    if outcome in ("failure", "failed", "error", "timeout"):
        return "execution_failed"
    if action.startswith("execution."):
        return "bot_run"
    if action.startswith("trigger."):
        return "trigger_fired"
    if action.startswith("team."):
        return "team_action"
    for suffix in (".update", ".create", ".delete", ".updated", ".created", ".deleted"):
        if action.endswith(suffix):
            return "config_changed"
    return "config_changed"


def _map_event_to_activity(event: dict) -> dict:
    action: str = event.get("action", "")
    entity_type: str = event.get("entity_type", "")
    entity_id: str = event.get("entity_id", "")
    outcome: str = event.get("outcome", "")
    details: dict = event.get("details") or {}
    description = (
        f"{entity_type} {entity_id} — {outcome}" if outcome else f"{entity_type} {entity_id}"
    )
    return {
        "id": str(event.get("id", "")),
        "type": _map_action_to_type(action, outcome),
        "title": action.replace(".", " ").replace("_", " ").title(),
        "description": description,
        "actor": event.get("actor", "system"),
        "timestamp": event.get("created_at", ""),
        "projectId": details.get("project_id", entity_id),
        "metadata": details,
    }


@get("/api/activity-feed", sync_to_thread=False)
def activity_feed(
    limit: int = 100,
    offset: int = 0,
    entity_type: Optional[str] = None,
    actor: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    """Unified activity feed mapped from audit events."""
    if limit > 500:
        limit = 500
    if offset < 0:
        offset = 0
    events = query_audit_events(
        entity_type=entity_type,
        actor=actor,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    total = count_audit_events(
        entity_type=entity_type,
        actor=actor,
        start_date=start_date,
        end_date=end_date,
    )
    return {"activities": [_map_event_to_activity(e) for e in events], "total": total}


@get("/admin/bots/sla", sync_to_thread=False)
def bot_sla() -> dict[str, list]:
    """Stub — bot SLA / uptime is not yet tracked."""
    return {"entries": []}


@get("/admin/analytics/cross-team-insights", sync_to_thread=False)
def cross_team_insights() -> dict[str, Any]:
    """Per-team execution stats + org-level findings."""
    return get_cross_team_insights()


_MODEL_META = {
    "claude-opus-4-6": {"name": "Claude Opus 4.6", "contextWindow": 200000, "speed": "slow"},
    "claude-opus-4-5": {"name": "Claude Opus 4.5", "contextWindow": 200000, "speed": "slow"},
    "claude-opus-4": {"name": "Claude Opus 4", "contextWindow": 200000, "speed": "slow"},
    "claude-sonnet-4-5": {"name": "Claude Sonnet 4.5", "contextWindow": 200000, "speed": "medium"},
    "claude-sonnet-4": {"name": "Claude Sonnet 4", "contextWindow": 200000, "speed": "medium"},
    "claude-haiku-4-5": {"name": "Claude Haiku 4.5", "contextWindow": 200000, "speed": "fast"},
    "claude-haiku-3-5": {"name": "Claude Haiku 3.5", "contextWindow": 200000, "speed": "fast"},
    "gpt-5.3-codex": {"name": "GPT-5.3 Codex", "contextWindow": 128000, "speed": "medium"},
    "gpt-5-codex-mini": {"name": "GPT-5 Codex Mini", "contextWindow": 128000, "speed": "fast"},
    "codex-mini-latest": {"name": "Codex Mini Latest", "contextWindow": 128000, "speed": "fast"},
}


@get("/api/models/pricing", sync_to_thread=False)
def model_pricing() -> dict[str, list[dict[str, Any]]]:
    """Pricing info for known models."""
    models = []
    for model_id, pricing in _PRICING.items():
        meta = _MODEL_META.get(model_id, {})
        models.append(
            {
                "id": model_id,
                "name": meta.get("name", model_id),
                "inputPricePer1M": pricing.get("input", 0.0),
                "outputPricePer1M": pricing.get("output", 0.0),
                "contextWindow": meta.get("contextWindow", 200000),
                "speed": meta.get("speed", "medium"),
            }
        )
    return {"models": models}


@get("/admin/analytics/scheduling-suggestions", sync_to_thread=False)
def scheduling_suggestions(trigger_id: Optional[str] = None) -> dict[str, Any]:
    """Suggested trigger times based on execution history."""
    try:
        result = SchedulingSuggestionService.get_suggestions(trigger_id=trigger_id)
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None
    return result.model_dump()


# ===========================================================================
# PR-J3b: 501 stubs for STUB-DEFER frontend views (PR-J3). Each view ships a
# "Not yet enabled" banner; these handlers replace the previous 404s so the
# UI sees an explicit contract.
# ===========================================================================


# BotSandboxPage.vue → /admin/sandboxes
@get("/admin/sandboxes", sync_to_thread=False)
def list_sandboxes() -> dict[str, Any]:
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@post("/admin/sandboxes", sync_to_thread=False)
def create_sandbox(data: dict) -> dict[str, Any]:
    del data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


# DataRetentionPoliciesPage.vue → /admin/retention/* (distinct from real
# /admin/retention-policies/*). The view's banner is gated by FEATURE_ENABLED;
# this handler matches the path referenced in the PR-J3 commit message.
@get("/admin/retention", sync_to_thread=False)
def list_retention_stub() -> dict[str, Any]:
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@post("/admin/retention", sync_to_thread=False)
def create_retention_stub(data: dict) -> dict[str, Any]:
    del data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


# NotificationHubPage.vue → /admin/notifications/{config,test}
@get("/admin/notifications/config", sync_to_thread=False)
def get_notifications_config() -> dict[str, Any]:
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@put("/admin/notifications/config", sync_to_thread=False)
def update_notifications_config(data: dict) -> dict[str, Any]:
    del data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@post("/admin/notifications/test", sync_to_thread=False)
def test_notifications(data: dict) -> dict[str, Any]:
    del data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


# PromptLocalizationPage.vue → /admin/prompt-localization/*
@get("/admin/prompt-localization", sync_to_thread=False)
def list_prompt_localizations() -> dict[str, Any]:
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@post("/admin/prompt-localization", sync_to_thread=False)
def create_prompt_localization(data: dict) -> dict[str, Any]:
    del data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@post("/admin/prompt-localization/translate", sync_to_thread=False)
def translate_prompt(data: dict) -> dict[str, Any]:
    del data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


# SmartAlertRulesPage.vue → /admin/alerts/rules
@get("/admin/alerts/rules", sync_to_thread=False)
def list_alert_rules() -> dict[str, Any]:
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@post("/admin/alerts/rules", sync_to_thread=False)
def create_alert_rule(data: dict) -> dict[str, Any]:
    del data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@put("/admin/alerts/rules/{rule_id:str}", sync_to_thread=False)
def update_alert_rule(rule_id: str, data: dict) -> dict[str, Any]:
    del rule_id, data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@delete("/admin/alerts/rules/{rule_id:str}", status_code=200, sync_to_thread=False)
def delete_alert_rule(rule_id: str) -> dict[str, Any]:
    del rule_id
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


# SmartScheduleOptimizerPage.vue → /admin/schedule-optimizer/*
@get("/admin/schedule-optimizer", sync_to_thread=False)
def get_schedule_optimizer() -> dict[str, Any]:
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@post("/admin/schedule-optimizer/optimize", sync_to_thread=False)
def run_schedule_optimizer(data: dict) -> dict[str, Any]:
    del data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


# TeamActivityFeedPage.vue → /admin/activity-feed?team= (team-scoped variant of
# the existing /api/activity-feed). View itself reads from auditApi; this stub
# fills in the missing team-scoped endpoint named in the PR-J3 commit.
@get("/admin/activity-feed", sync_to_thread=False)
def team_activity_feed(team: Optional[str] = None) -> dict[str, Any]:
    del team
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


# OnboardingAutomationPage.vue extra: the existing /admin/onboarding/* router
# already covers config + runs. PR-J3 lists onboarding-automation among the
# STUB-DEFER set because the view assumes higher-level automation that isn't
# wired up; the trigger-specific stub below sits alongside the real handlers.
@post("/admin/onboarding/automate", sync_to_thread=False)
def onboarding_automate(data: dict) -> dict[str, Any]:
    del data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


misc_router = Router(
    path="/",
    route_handlers=[
        activity_feed,
        bot_sla,
        cross_team_insights,
        model_pricing,
        scheduling_suggestions,
        list_sandboxes,
        create_sandbox,
        list_retention_stub,
        create_retention_stub,
        get_notifications_config,
        update_notifications_config,
        test_notifications,
        list_prompt_localizations,
        create_prompt_localization,
        translate_prompt,
        list_alert_rules,
        create_alert_rule,
        update_alert_rule,
        delete_alert_rule,
        get_schedule_optimizer,
        run_schedule_optimizer,
        team_activity_feed,
        onboarding_automate,
    ],
)
