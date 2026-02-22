"""Rule management API endpoints."""

from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    add_rule,
    count_rules,
    delete_rule,
    get_all_rules,
    get_rule,
    get_rules_by_project,
    get_rules_by_type,
    update_rule,
)
from ..models.common import PaginationQuery

tag = Tag(name="rules", description="Rule management operations")
rules_bp = APIBlueprint("rules", __name__, url_prefix="/admin/rules", abp_tags=[tag])


class RulePath(BaseModel):
    rule_id: int = Field(..., description="Rule ID")


class ProjectRulesPath(BaseModel):
    project_id: str = Field(..., description="Project ID")


# Valid rule types
VALID_RULE_TYPES = [
    "pre_check",
    "post_check",
    "validation",
]


@rules_bp.get("/")
def list_rules(query: PaginationQuery):
    """List all rules (global + per-project) with optional pagination."""
    project_id = request.args.get("project_id")
    total_count = count_rules(project_id)
    rules = get_all_rules(project_id, limit=query.limit, offset=query.offset or 0)
    return {"rules": rules, "total_count": total_count}, HTTPStatus.OK


@rules_bp.post("/")
def create_rule():
    """Create a new rule."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    name = data.get("name")
    rule_type = data.get("rule_type", "validation")

    if not name:
        return {"error": "name is required"}, HTTPStatus.BAD_REQUEST
    if rule_type not in VALID_RULE_TYPES:
        return {
            "error": f"Invalid rule type. Must be one of: {', '.join(VALID_RULE_TYPES)}"
        }, HTTPStatus.BAD_REQUEST

    rule_id = add_rule(
        name=name,
        rule_type=rule_type,
        description=data.get("description"),
        condition=data.get("condition"),
        action=data.get("action"),
        enabled=data.get("enabled", True),
        project_id=data.get("project_id"),
        source_path=data.get("source_path"),
    )

    if not rule_id:
        return {"error": "Failed to create rule"}, HTTPStatus.INTERNAL_SERVER_ERROR

    rule = get_rule(rule_id)
    return {"message": "Rule created", "rule": rule}, HTTPStatus.CREATED


@rules_bp.get("/<int:rule_id>")
def get_rule_endpoint(path: RulePath):
    """Get rule details."""
    rule = get_rule(path.rule_id)
    if not rule:
        return {"error": "Rule not found"}, HTTPStatus.NOT_FOUND
    return rule, HTTPStatus.OK


@rules_bp.put("/<int:rule_id>")
def update_rule_endpoint(path: RulePath):
    """Update a rule."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    rule_type = data.get("rule_type")
    if rule_type and rule_type not in VALID_RULE_TYPES:
        return {
            "error": f"Invalid rule type. Must be one of: {', '.join(VALID_RULE_TYPES)}"
        }, HTTPStatus.BAD_REQUEST

    if not update_rule(
        path.rule_id,
        name=data.get("name"),
        rule_type=rule_type,
        description=data.get("description"),
        condition=data.get("condition"),
        action=data.get("action"),
        enabled=data.get("enabled"),
    ):
        return {"error": "Rule not found or no changes made"}, HTTPStatus.NOT_FOUND

    rule = get_rule(path.rule_id)
    return rule, HTTPStatus.OK


@rules_bp.delete("/<int:rule_id>")
def delete_rule_endpoint(path: RulePath):
    """Delete a rule."""
    if not delete_rule(path.rule_id):
        return {"error": "Rule not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Rule deleted"}, HTTPStatus.OK


@rules_bp.get("/types")
def list_rule_types():
    """List all valid rule types."""
    return {"types": VALID_RULE_TYPES}, HTTPStatus.OK


@rules_bp.get("/project/<project_id>")
def list_project_rules(path: ProjectRulesPath):
    """List rules for a specific project."""
    rules = get_rules_by_project(path.project_id)
    return {"rules": rules, "project_id": path.project_id}, HTTPStatus.OK


@rules_bp.get("/type/<rule_type>")
def list_rules_by_type(rule_type: str):
    """List enabled rules for a specific type."""
    if rule_type not in VALID_RULE_TYPES:
        return {
            "error": f"Invalid rule type. Must be one of: {', '.join(VALID_RULE_TYPES)}"
        }, HTTPStatus.BAD_REQUEST
    rules = get_rules_by_type(rule_type)
    return {"rules": rules, "rule_type": rule_type}, HTTPStatus.OK


@rules_bp.get("/<int:rule_id>/export")
def export_rule(path: RulePath):
    """Export a rule as a deployable configuration."""
    rule = get_rule(path.rule_id)
    if not rule:
        return {"error": "Rule not found"}, HTTPStatus.NOT_FOUND

    # Generate export format
    export_data = {
        "name": rule["name"],
        "rule_type": rule["rule_type"],
        "description": rule.get("description"),
        "condition": rule.get("condition"),
        "action": rule.get("action"),
        "enabled": bool(rule.get("enabled", 1)),
    }

    return {"rule": export_data, "format": "json"}, HTTPStatus.OK


@rules_bp.post("/generate/stream")
def generate_rule_stream():
    """Generate a rule configuration from a description using AI (streaming)."""
    from ..services.rule_generation_service import RuleGenerationService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    description = (data.get("description") or "").strip()
    if len(description) < 10:
        return {"error": "Description must be at least 10 characters"}, HTTPStatus.BAD_REQUEST

    return Response(
        RuleGenerationService.generate_streaming(description),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
