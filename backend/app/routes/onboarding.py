"""API endpoints for onboarding automation configuration and runs."""

from http import HTTPStatus
from typing import List, Optional

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.onboarding import get_steps, upsert_steps
from ..db.triggers import get_trigger, get_execution_logs_for_trigger, update_trigger
from ..services.rbac_service import require_role

tag = Tag(name="onboarding", description="Onboarding automation configuration and runs")
onboarding_bp = APIBlueprint("onboarding", __name__, url_prefix="/admin", abp_tags=[tag])

# The onboarding trigger ID — the first predefined trigger matching the onboarding use case.
# This can be overridden by passing trigger_id as a query parameter.
ONBOARDING_TRIGGER_ID = "bot-onboarding"


class OnboardingStepIn(BaseModel):
    id: Optional[str] = Field(default=None, description="Step ID (reuse existing or omit to generate)")
    step_order: int = Field(..., description="Execution order index")
    name: str = Field(..., min_length=1, description="Step name")
    description: str = Field(default="", description="Step description")
    type: str = Field(default="custom", description="Step type: github, slack, jira, email, custom")
    enabled: bool = Field(default=True, description="Whether the step is active")
    delay_minutes: int = Field(default=0, ge=0, description="Minutes to wait before executing this step")


class SaveOnboardingConfigBody(BaseModel):
    trigger_id: str = Field(..., description="Trigger ID to configure")
    trigger_event: Optional[str] = Field(
        default=None, description="Trigger event label (stored as trigger_source)"
    )
    enabled: Optional[bool] = Field(default=None, description="Enable or disable the trigger")
    steps: List[OnboardingStepIn] = Field(
        default_factory=list, description="Ordered list of onboarding steps"
    )


@onboarding_bp.get("/onboarding/config")
@require_role("viewer", "operator", "editor", "admin")
def get_onboarding_config():
    """Get the onboarding trigger config and its steps.

    Pass ?trigger_id=<id> to specify a trigger; defaults to bot-onboarding.
    """
    from flask import request

    trigger_id = request.args.get("trigger_id", ONBOARDING_TRIGGER_ID)
    trigger = get_trigger(trigger_id)
    if not trigger:
        # Return empty config when trigger doesn't exist yet
        return {
            "trigger": None,
            "steps": [],
        }, HTTPStatus.OK

    steps = get_steps(trigger_id)
    return {
        "trigger": trigger,
        "steps": steps,
    }, HTTPStatus.OK


@onboarding_bp.put("/onboarding/config")
@require_role("editor", "admin")
def save_onboarding_config(body: SaveOnboardingConfigBody):
    """Save the onboarding trigger configuration and replace its steps."""
    trigger_id = body.trigger_id

    trigger = get_trigger(trigger_id)
    if not trigger:
        return error_response("NOT_FOUND", f"Trigger '{trigger_id}' not found", HTTPStatus.NOT_FOUND)

    # Update the trigger's enabled flag and trigger_source if provided
    update_kwargs: dict = {}
    if body.enabled is not None:
        update_kwargs["enabled"] = 1 if body.enabled else 0
    if body.trigger_event is not None:
        update_kwargs["trigger_source"] = body.trigger_event

    if update_kwargs:
        update_trigger(trigger_id, **update_kwargs)

    # Replace steps
    steps_data = [s.model_dump() for s in body.steps]
    upsert_steps(trigger_id, steps_data)

    trigger = get_trigger(trigger_id)
    steps = get_steps(trigger_id)
    return {
        "message": "Onboarding configuration saved",
        "trigger": trigger,
        "steps": steps,
    }, HTTPStatus.OK


@onboarding_bp.get("/onboarding/runs")
@require_role("viewer", "operator", "editor", "admin")
def get_onboarding_runs():
    """Get the last 20 execution runs for an onboarding trigger.

    Pass ?trigger_id=<id> to specify a trigger; defaults to bot-onboarding.
    """
    from flask import request

    trigger_id = request.args.get("trigger_id", ONBOARDING_TRIGGER_ID)
    logs = get_execution_logs_for_trigger(trigger_id, limit=20)
    return {"runs": logs, "total": len(logs)}, HTTPStatus.OK
