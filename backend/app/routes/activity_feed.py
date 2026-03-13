"""Activity feed API endpoint.

Provides a unified chronological feed of platform events mapped from
persistent audit events into a frontend-friendly Activity shape.
"""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="activity-feed", description="Unified activity feed")
activity_feed_bp = APIBlueprint("activity_feed", __name__, url_prefix="/api", abp_tags=[tag])


def _map_action_to_type(action: str, outcome: str) -> str:
    """Map an audit event action + outcome to an Activity type string."""
    if outcome in ("failure", "failed", "error", "timeout"):
        return "execution_failed"
    if action.startswith("execution."):
        return "bot_run"
    if action.startswith("trigger."):
        return "trigger_fired"
    if action.startswith("team."):
        return "team_action"
    # config change catch-all: update / create / delete on any entity
    for suffix in (".update", ".create", ".delete", ".updated", ".created", ".deleted"):
        if action.endswith(suffix):
            return "config_changed"
    return "config_changed"


def _map_event_to_activity(event: dict) -> dict:
    """Convert a raw audit event dict to the Activity shape expected by the frontend."""
    action: str = event.get("action", "")
    entity_type: str = event.get("entity_type", "")
    entity_id: str = event.get("entity_id", "")
    outcome: str = event.get("outcome", "")
    details: dict = event.get("details") or {}

    activity_type = _map_action_to_type(action, outcome)

    # Title: capitalize each word, replace dots/underscores with spaces
    title = action.replace(".", " ").replace("_", " ").title()

    # Description: best-effort human-readable summary
    description = (
        f"{entity_type} {entity_id} — {outcome}" if outcome else f"{entity_type} {entity_id}"
    )

    # Best-effort project id
    project_id = details.get("project_id", entity_id)

    return {
        "id": str(event.get("id", "")),
        "type": activity_type,
        "title": title,
        "description": description,
        "actor": event.get("actor", "system"),
        "timestamp": event.get("created_at", ""),
        "projectId": project_id,
        "metadata": details,
    }


@activity_feed_bp.get("/activity-feed")
def get_activity_feed():
    """Get a unified activity feed from persistent audit events.

    Query parameters:
    - limit: Max activities to return (default 100, max 500)
    - offset: Pagination offset (default 0)
    - entity_type: Filter by entity type
    - actor: Filter by actor
    - start_date: ISO date range start (inclusive)
    - end_date: ISO date range end (inclusive)
    """
    from ..db.audit_events import count_audit_events, query_audit_events

    entity_type = request.args.get("entity_type")
    actor = request.args.get("actor")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    limit = min(request.args.get("limit", 100, type=int), 500)
    offset = max(request.args.get("offset", 0, type=int), 0)

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

    activities = [_map_event_to_activity(e) for e in events]
    return {"activities": activities, "total": total}, HTTPStatus.OK
