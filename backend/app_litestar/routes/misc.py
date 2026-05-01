"""Single-route migrations batched into one router (track A, wave 48).

Each route is a thin wrapper around an existing service / db helper.
Grouping them here avoids the per-namespace ceremony cost — the
playbook says "batch by namespace" but for tiny single-route files
the right namespace is `misc`.
"""

from __future__ import annotations

from typing import Any, Optional

from litestar import Router, get
from litestar.exceptions import ClientException

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
        f"{entity_type} {entity_id} — {outcome}"
        if outcome
        else f"{entity_type} {entity_id}"
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


misc_router = Router(
    path="/",
    route_handlers=[
        activity_feed,
        bot_sla,
        cross_team_insights,
        model_pricing,
        scheduling_suggestions,
    ],
)
