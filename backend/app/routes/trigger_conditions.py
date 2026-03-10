"""API endpoints for trigger condition rules (conditional trigger filtering)."""

from http import HTTPStatus
from typing import List, Optional

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.trigger_conditions import (
    create_trigger_condition,
    delete_trigger_condition,
    get_trigger_condition,
    list_trigger_conditions,
    update_trigger_condition,
)
from ..services.rbac_service import require_role

tag = Tag(name="trigger-conditions", description="Conditional filter rules for triggers")
trigger_conditions_bp = APIBlueprint(
    "trigger_conditions", __name__, url_prefix="/admin", abp_tags=[tag]
)


class TriggerPath(BaseModel):
    trigger_id: str = Field(..., description="Trigger ID")


class ConditionPath(BaseModel):
    condition_id: str = Field(..., description="Trigger condition rule ID")


class ConditionItem(BaseModel):
    id: str = Field(..., description="Condition item ID (client-generated)")
    field: str = Field(..., description="Field path to evaluate (e.g. pr.lines_changed)")
    operator: str = Field(
        ...,
        description="Comparison operator: equals, not_equals, contains, greater_than, less_than, matches",
    )
    value: str = Field(..., description="Value to compare against")


class TriggerConditionCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Rule name")
    description: str = Field(default="", description="Rule description")
    enabled: bool = Field(default=True, description="Whether the rule is active")
    logic: str = Field(default="AND", description="How conditions combine: AND or OR")
    conditions: List[ConditionItem] = Field(
        default_factory=list, description="List of individual conditions"
    )


class TriggerConditionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, description="Rule name")
    description: Optional[str] = Field(default=None, description="Rule description")
    enabled: Optional[bool] = Field(default=None, description="Whether the rule is active")
    logic: Optional[str] = Field(default=None, description="AND or OR")
    conditions: Optional[List[ConditionItem]] = Field(
        default=None, description="List of individual conditions"
    )


@trigger_conditions_bp.get("/triggers/<trigger_id>/conditions")
@require_role("viewer", "operator", "editor", "admin")
def list_conditions(path: TriggerPath):
    """List all condition rules for a trigger."""
    rules = list_trigger_conditions(path.trigger_id)
    return {"rules": rules, "total": len(rules)}, HTTPStatus.OK


@trigger_conditions_bp.post("/triggers/<trigger_id>/conditions")
@require_role("editor", "admin")
def create_condition(path: TriggerPath, body: TriggerConditionCreate):
    """Create a new condition rule for a trigger."""
    condition_id = create_trigger_condition(
        trigger_id=path.trigger_id,
        name=body.name,
        description=body.description,
        enabled=body.enabled,
        logic=body.logic,
        conditions=[c.model_dump() for c in body.conditions],
    )
    if not condition_id:
        return error_response(
            "INTERNAL_ERROR", "Failed to create condition rule", HTTPStatus.INTERNAL_SERVER_ERROR
        )
    rule = get_trigger_condition(condition_id)
    return {"message": "Condition rule created", "rule": rule}, HTTPStatus.CREATED


@trigger_conditions_bp.get("/trigger-conditions/<condition_id>")
@require_role("viewer", "operator", "editor", "admin")
def get_condition(path: ConditionPath):
    """Get a single condition rule by ID."""
    rule = get_trigger_condition(path.condition_id)
    if not rule:
        return error_response("NOT_FOUND", "Condition rule not found", HTTPStatus.NOT_FOUND)
    return rule, HTTPStatus.OK


@trigger_conditions_bp.put("/trigger-conditions/<condition_id>")
@require_role("editor", "admin")
def update_condition(path: ConditionPath, body: TriggerConditionUpdate):
    """Update a condition rule."""
    conditions = [c.model_dump() for c in body.conditions] if body.conditions is not None else None
    updated = update_trigger_condition(
        condition_id=path.condition_id,
        name=body.name,
        description=body.description,
        enabled=body.enabled,
        logic=body.logic,
        conditions=conditions,
    )
    if not updated:
        return error_response(
            "NOT_FOUND", "Condition rule not found or no changes", HTTPStatus.NOT_FOUND
        )
    rule = get_trigger_condition(path.condition_id)
    return rule, HTTPStatus.OK


@trigger_conditions_bp.delete("/trigger-conditions/<condition_id>")
@require_role("editor", "admin")
def delete_condition(path: ConditionPath):
    """Delete a condition rule."""
    deleted = delete_trigger_condition(path.condition_id)
    if not deleted:
        return error_response("NOT_FOUND", "Condition rule not found", HTTPStatus.NOT_FOUND)
    return {"message": "Condition rule deleted"}, HTTPStatus.OK
