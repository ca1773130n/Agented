"""PR auto-assignment API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.pr_assignment import add_ownership_rule, delete_ownership_rule, get_ownership_rules
from ..db.settings import get_setting, set_setting
from ..db.triggers import get_pr_reviews_for_trigger

tag = Tag(name="pr-assignment", description="PR auto-assignment ownership rules and settings")
pr_assignment_bp = APIBlueprint(
    "pr_assignment", __name__, url_prefix="/api/pr-assignment", abp_tags=[tag]
)

_SETTINGS_KEYS = [
    "pr_assignment_enabled",
    "pr_assignment_min_confidence",
    "pr_assignment_max_reviewers",
]


class RuleIdPath(BaseModel):
    rule_id: str = Field(..., description="Ownership rule ID")


# --- Rules endpoints ---


@pr_assignment_bp.get("/rules")
def list_rules():
    """List all PR ownership rules."""
    rules = get_ownership_rules()
    return {"rules": rules}, HTTPStatus.OK


@pr_assignment_bp.post("/rules")
def create_rule():
    """Create a new PR ownership rule."""
    data = request.get_json(silent=True) or {}
    pattern = data.get("pattern", "").strip()
    team = data.get("team", "").strip()
    reviewers = data.get("reviewers", [])
    priority = int(data.get("priority", 0))

    if not pattern or not team:
        return error_response("pattern and team are required"), HTTPStatus.BAD_REQUEST

    if isinstance(reviewers, str):
        reviewers = [r.strip() for r in reviewers.split(",") if r.strip()]

    rule_id = add_ownership_rule(pattern=pattern, team=team, reviewers=reviewers, priority=priority)
    return {
        "id": rule_id,
        "pattern": pattern,
        "team": team,
        "reviewers": reviewers,
        "priority": priority,
    }, HTTPStatus.CREATED


@pr_assignment_bp.delete("/rules/<rule_id>")
def delete_rule(path: RuleIdPath):
    """Delete a PR ownership rule by ID."""
    deleted = delete_ownership_rule(path.rule_id)
    if not deleted:
        return error_response("Rule not found"), HTTPStatus.NOT_FOUND
    return {"deleted": True, "id": path.rule_id}, HTTPStatus.OK


# --- Settings endpoints ---


@pr_assignment_bp.get("/settings")
def get_settings():
    """Get PR assignment configuration settings."""
    result = {}
    for key in _SETTINGS_KEYS:
        result[key] = get_setting(key)
    # Provide defaults for unset keys
    if result["pr_assignment_enabled"] is None:
        result["pr_assignment_enabled"] = "true"
    if result["pr_assignment_min_confidence"] is None:
        result["pr_assignment_min_confidence"] = "70"
    if result["pr_assignment_max_reviewers"] is None:
        result["pr_assignment_max_reviewers"] = "2"
    return result, HTTPStatus.OK


@pr_assignment_bp.put("/settings")
def update_settings():
    """Update PR assignment configuration settings."""
    data = request.get_json(silent=True) or {}
    updated = {}
    for key in _SETTINGS_KEYS:
        if key in data:
            set_setting(key, str(data[key]))
            updated[key] = str(data[key])
    return {"updated": updated}, HTTPStatus.OK


# --- Recent assignments endpoint ---


@pr_assignment_bp.get("/recent")
def list_recent():
    """List recent PR assignment activity from the pr_reviews table."""
    limit = request.args.get("limit", 20, type=int)
    reviews = get_pr_reviews_for_trigger(limit=limit)
    assignments = []
    for r in reviews:
        assignments.append(
            {
                "id": str(r["id"]),
                "prNumber": r.get("pr_number"),
                "prTitle": r.get("pr_title", ""),
                "assignedTo": [r["pr_author"]] if r.get("pr_author") else [],
                "reason": r.get("review_comment") or "Matched ownership rule",
                "confidence": 80,
                "timestamp": r.get("created_at", ""),
            }
        )
    return {"assignments": assignments}, HTTPStatus.OK
