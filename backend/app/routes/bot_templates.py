"""Bot template marketplace API endpoints."""

import json
from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.bot_templates import deploy_template, get_all_templates, get_template
from ..services.rbac_service import require_role

tag = Tag(name="Bot Templates", description="Curated bot template marketplace")
bot_templates_bp = APIBlueprint(
    "bot_templates", __name__, url_prefix="/admin/bot-templates", abp_tags=[tag]
)


class TemplatePath(BaseModel):
    template_id: str = Field(..., description="Bot template ID")


@bot_templates_bp.get("/")
@require_role("viewer", "operator", "editor", "admin")
def list_templates():
    """List all published bot templates sorted by sort_order."""
    templates = get_all_templates()
    return {"templates": templates}, HTTPStatus.OK


@bot_templates_bp.get("/<template_id>")
@require_role("viewer", "operator", "editor", "admin")
def get_template_detail(path: TemplatePath):
    """Get a single bot template by ID."""
    template = get_template(path.template_id)
    if not template:
        return error_response("NOT_FOUND", "Template not found", HTTPStatus.NOT_FOUND)
    return template, HTTPStatus.OK


@bot_templates_bp.post("/<template_id>/deploy")
@require_role("editor", "admin")
def deploy_template_endpoint(path: TemplatePath):
    """Deploy a bot template by creating a new trigger from its configuration."""
    template = get_template(path.template_id)
    if not template:
        return error_response("NOT_FOUND", "Template not found", HTTPStatus.NOT_FOUND)

    trigger_id = deploy_template(path.template_id)
    if not trigger_id:
        return error_response(
            "INTERNAL_SERVER_ERROR", "Failed to deploy template", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    # Determine the trigger name that was actually used
    try:
        config = json.loads(template["config_json"])
        trigger_name = config.get("name", template["name"])
    except (json.JSONDecodeError, TypeError):
        trigger_name = template["name"]

    # Check what name was actually assigned (may have suffix)
    from ..db.triggers import get_trigger

    trigger = get_trigger(trigger_id)
    if trigger:
        trigger_name = trigger["name"]

    return {
        "trigger_id": trigger_id,
        "template_id": path.template_id,
        "trigger_name": trigger_name,
        "message": f"Template '{template['name']}' deployed as trigger '{trigger_name}'",
    }, HTTPStatus.CREATED
