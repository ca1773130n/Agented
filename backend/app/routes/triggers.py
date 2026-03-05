"""Trigger management API endpoints (primary routes)."""

from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..database import get_trigger
from ..models.common import PaginationQuery
from ..services.budget_service import BudgetService
from ..services.execution_service import ExecutionService
from ..services.rbac_service import require_role
from ..services.trigger_service import TriggerService

tag = Tag(name="Triggers", description="Trigger management")
triggers_bp = APIBlueprint("triggers", __name__, url_prefix="/admin/triggers", abp_tags=[tag])


class TriggerPath(BaseModel):
    trigger_id: str = Field(..., description="Trigger ID")


@triggers_bp.get("/")
@require_role("viewer", "operator", "editor", "admin")
def list_triggers(query: PaginationQuery):
    """List all triggers with path counts and execution status."""
    result, status = TriggerService.list_triggers(limit=query.limit, offset=query.offset or 0)
    return result, status


@triggers_bp.post("/")
@require_role("editor", "admin")
def create_trigger():
    """Create a new trigger."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)
    result, status = TriggerService.create_trigger(data)
    return result, status


@triggers_bp.get("/<trigger_id>")
@require_role("viewer", "operator", "editor", "admin")
def get_trigger_detail(path: TriggerPath):
    """Get trigger details with paths."""
    result, status = TriggerService.get_trigger_detail(path.trigger_id)
    return result, status


@triggers_bp.put("/<trigger_id>")
@require_role("editor", "admin")
def update_trigger(path: TriggerPath):
    """Update a trigger."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)
    result, status = TriggerService.update_trigger(path.trigger_id, data)
    return result, status


@triggers_bp.delete("/<trigger_id>")
@require_role("editor", "admin")
def delete_trigger(path: TriggerPath):
    """Delete a trigger (non-predefined only)."""
    result, status = TriggerService.delete_trigger(path.trigger_id)
    return result, status


@triggers_bp.get("/<trigger_id>/paths")
@require_role("viewer", "operator", "editor", "admin")
def list_trigger_paths(path: TriggerPath, query: PaginationQuery):
    """List all project paths for a trigger."""
    result, status = TriggerService.list_paths(
        path.trigger_id, limit=query.limit, offset=query.offset or 0
    )
    return result, status


@triggers_bp.post("/<trigger_id>/paths")
@require_role("editor", "admin")
def add_trigger_path(path: TriggerPath):
    """Add a project path to a trigger."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)
    result, status = TriggerService.add_path(path.trigger_id, data)
    return result, status


@triggers_bp.delete("/<trigger_id>/paths")
@require_role("editor", "admin")
def remove_trigger_path(path: TriggerPath):
    """Remove a project path from a trigger."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)
    result, status = TriggerService.remove_path(path.trigger_id, data)
    return result, status


class TriggerProjectPath(BaseModel):
    trigger_id: str = Field(..., description="Trigger ID")
    project_id: str = Field(..., description="Project ID")


@triggers_bp.post("/<trigger_id>/projects")
@require_role("editor", "admin")
def add_trigger_project(path: TriggerPath):
    """Add a project reference to a trigger."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)
    project_id = data.get("project_id")
    if not project_id:
        return error_response("BAD_REQUEST", "project_id is required", HTTPStatus.BAD_REQUEST)
    result, status = TriggerService.add_project(path.trigger_id, project_id)
    return result, status


@triggers_bp.delete("/<trigger_id>/projects/<project_id>")
@require_role("editor", "admin")
def remove_trigger_project(path: TriggerProjectPath):
    """Remove a project reference from a trigger."""
    result, status = TriggerService.remove_project(path.trigger_id, path.project_id)
    return result, status


@triggers_bp.put("/<trigger_id>/auto-resolve")
@require_role("editor", "admin")
def set_auto_resolve(path: TriggerPath):
    """Enable/disable auto-resolve and PR creation for the security trigger."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)
    auto_resolve = bool(data.get("auto_resolve", False))
    result, status = TriggerService.update_auto_resolve(path.trigger_id, auto_resolve)
    return result, status


@triggers_bp.get("/<trigger_id>/status")
@require_role("viewer", "operator", "editor", "admin")
def get_trigger_status(path: TriggerPath):
    """Get execution status for a trigger."""
    trigger = get_trigger(path.trigger_id)
    if not trigger:
        return error_response("NOT_FOUND", "Trigger not found", HTTPStatus.NOT_FOUND)

    status = ExecutionService.get_status(path.trigger_id)
    return status, HTTPStatus.OK


@triggers_bp.post("/<trigger_id>/run")
@require_role("operator", "editor", "admin")
def run_trigger(path: TriggerPath):
    """Manually trigger a trigger to run.

    Request body (JSON):
    - message (str, optional): Custom message for the bot prompt.

    Prompt Placeholder Syntax:
    Trigger prompt templates support curly-brace placeholders that are
    resolved at execution time. Known placeholders:
    - {trigger_id}: The trigger's unique ID (e.g., "trg-abc123")
    - {bot_id}: The associated bot's unique ID
    - {paths}: Newline-separated list of file paths from the trigger config
    - {message}: The message text (from request body or webhook payload)
    - {pr_url}: Full URL to the pull request (GitHub trigger only)
    - {pr_number}: PR number (GitHub trigger only)
    - {pr_title}: PR title text (GitHub trigger only)
    - {pr_author}: PR author username (GitHub trigger only)
    - {repo_url}: Repository clone URL (GitHub trigger only)
    - {repo_full_name}: Repository full name, e.g. "owner/repo" (GitHub trigger only)

    Placeholders not applicable to the trigger type are left empty (not
    replaced). Unknown placeholders (not in the list above) trigger a
    warning log but are left as-is in the rendered prompt.
    """
    data = request.get_json() or {}
    message = data.get("message", "")
    result, status = TriggerService.run(path.trigger_id, message)
    return result, status


@triggers_bp.post("/<trigger_id>/preview-prompt")
@require_role("viewer", "operator", "editor", "admin")
def preview_trigger_prompt(path: TriggerPath):
    """Dry-run preview: render the prompt template with sample data.

    Accepts an optional JSON body with sample placeholder values:
      paths, message, pr_url, pr_number, pr_title, pr_author, repo_url, repo_full_name
    """
    sample_data = request.get_json() or {}
    result, status = TriggerService.preview_prompt(path.trigger_id, sample_data)
    return result, status


@triggers_bp.get("/<trigger_id>/prompt-history")
@require_role("viewer", "operator", "editor", "admin")
def get_prompt_history(path: TriggerPath):
    """Get prompt template change history for a trigger."""
    from ..database import get_prompt_template_history

    trigger = get_trigger(path.trigger_id)
    if not trigger:
        return error_response("NOT_FOUND", "Trigger not found", HTTPStatus.NOT_FOUND)

    history = get_prompt_template_history(path.trigger_id, limit=50)
    return {"history": history}, HTTPStatus.OK


@triggers_bp.post("/<trigger_id>/rollback-prompt")
@require_role("editor", "admin")
def rollback_prompt(path: TriggerPath):
    """Rollback prompt template to a previous version.

    Request body (JSON):
    - version_id (int): The history entry ID to rollback to.
    """
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    version_id = data.get("version_id")
    if version_id is None:
        return error_response("BAD_REQUEST", "version_id is required", HTTPStatus.BAD_REQUEST)

    try:
        version_id = int(version_id)
    except (ValueError, TypeError):
        return error_response(
            "BAD_REQUEST", "version_id must be an integer", HTTPStatus.BAD_REQUEST
        )

    result, status = TriggerService.rollback_prompt_template(path.trigger_id, version_id)
    return result, status


@triggers_bp.post("/<trigger_id>/preview-prompt-full")
@require_role("viewer", "operator", "editor", "admin")
def preview_trigger_prompt_full(path: TriggerPath):
    """Full dry-run preview: render prompt with snippets, placeholders, and CLI command.

    Accepts a JSON body with custom payload values for substitution.
    Does NOT spawn any subprocess -- read-only operation.
    """
    payload = request.get_json() or {}
    result, status = TriggerService.preview_prompt_full(path.trigger_id, payload)
    return result, status


@triggers_bp.post("/validate-cron")
@require_role("viewer", "operator", "editor", "admin")
def validate_cron_expression():
    """Validate a standard 5-field cron expression (API-10)."""
    from ..models.common import error_response
    from ..utils.timezone import get_local_timezone

    try:
        import pytz
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        return error_response(
            "SCHEDULER_UNAVAILABLE",
            "APScheduler not installed",
            HTTPStatus.SERVICE_UNAVAILABLE,
        )

    data = request.get_json()
    if not data or "expression" not in data:
        return error_response(
            "INVALID_REQUEST", "Missing 'expression' field", HTTPStatus.BAD_REQUEST
        )

    expr = data["expression"]
    timezone_str = data.get("timezone") or get_local_timezone()

    try:
        tz = pytz.timezone(timezone_str)
    except Exception:
        return error_response(
            "INVALID_TIMEZONE",
            f"Unknown timezone: {timezone_str}",
            HTTPStatus.BAD_REQUEST,
        )

    try:
        from datetime import datetime

        trigger = CronTrigger.from_crontab(expr, timezone=tz)
        # Calculate next 5 fire times for preview
        next_fires = []
        fire_time = datetime.now(tz)
        for _ in range(5):
            fire_time = trigger.get_next_fire_time(None, fire_time)
            if fire_time:
                next_fires.append(fire_time.isoformat())
                # Advance slightly so we get the next distinct fire time
                from datetime import timedelta

                fire_time = fire_time + timedelta(seconds=1)
            else:
                break
        return {
            "valid": True,
            "expression": expr,
            "timezone": timezone_str,
            "next_fires": next_fires,
        }, HTTPStatus.OK
    except (ValueError, TypeError) as e:
        return error_response(
            "INVALID_CRON",
            f"Invalid cron expression: {str(e)}",
            HTTPStatus.BAD_REQUEST,
            details={"expression": expr},
        )


@triggers_bp.post("/<trigger_id>/dry-run")
@require_role("viewer", "operator", "editor", "admin")
def dry_run_trigger(path: TriggerPath):
    """Dry-run: render prompt, show CLI command, estimate cost -- no subprocess (API-01)."""
    data = request.get_json() or {}
    result, status = TriggerService.dry_run(path.trigger_id, data)
    return result, status


@triggers_bp.post("/<trigger_id>/estimate-cost")
@require_role("viewer", "operator", "editor", "admin")
def estimate_trigger_cost(path: TriggerPath):
    """Estimate token count and cost for a trigger execution (API-08)."""
    data = request.get_json() or {}
    preview, status = TriggerService.preview_prompt(path.trigger_id, data)
    if status != HTTPStatus.OK:
        return preview, status
    prompt = preview["rendered_prompt"]
    trigger = get_trigger(path.trigger_id)
    model = trigger.get("model") or "claude-sonnet-4"
    estimate = BudgetService.estimate_cost(prompt, model, "trigger", path.trigger_id)
    return {"trigger_id": path.trigger_id, "model": model, "estimate": estimate}, HTTPStatus.OK


@triggers_bp.post("/generate/stream")
@require_role("editor", "admin")
def generate_trigger_stream():
    """Generate a trigger configuration from a natural language description using AI (streaming)."""
    from ..services.trigger_generation_service import TriggerGenerationService

    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    description = (data.get("description") or "").strip()
    if len(description) < 10:
        return error_response(
            "BAD_REQUEST", "Description must be at least 10 characters", HTTPStatus.BAD_REQUEST
        )

    return Response(
        TriggerGenerationService.generate_streaming(description),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
