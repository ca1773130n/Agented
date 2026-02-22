"""Hook management API endpoints."""

from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    add_hook,
    count_hooks,
    delete_hook,
    get_all_hooks,
    get_hook,
    get_hooks_by_event,
    get_hooks_by_project,
    update_hook,
)
from ..models.common import PaginationQuery

tag = Tag(name="hooks", description="Hook management operations")
hooks_bp = APIBlueprint("hooks", __name__, url_prefix="/admin/hooks", abp_tags=[tag])


class HookPath(BaseModel):
    hook_id: int = Field(..., description="Hook ID")


class ProjectHooksPath(BaseModel):
    project_id: str = Field(..., description="Project ID")


# Valid hook event types
VALID_EVENTS = [
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "SubagentStop",
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "PreCompact",
    "Notification",
]


@hooks_bp.get("/")
def list_hooks(query: PaginationQuery):
    """List all hooks (global + per-project) with optional pagination."""
    project_id = request.args.get("project_id")
    total_count = count_hooks(project_id)
    hooks = get_all_hooks(project_id, limit=query.limit, offset=query.offset or 0)
    return {"hooks": hooks, "total_count": total_count}, HTTPStatus.OK


@hooks_bp.post("/")
def create_hook():
    """Create a new hook."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    name = data.get("name")
    event = data.get("event")

    if not name:
        return {"error": "name is required"}, HTTPStatus.BAD_REQUEST
    if not event:
        return {"error": "event is required"}, HTTPStatus.BAD_REQUEST
    if event not in VALID_EVENTS:
        return {
            "error": f"Invalid event type. Must be one of: {', '.join(VALID_EVENTS)}"
        }, HTTPStatus.BAD_REQUEST

    hook_id = add_hook(
        name=name,
        event=event,
        description=data.get("description"),
        content=data.get("content"),
        enabled=data.get("enabled", True),
        project_id=data.get("project_id"),
        source_path=data.get("source_path"),
    )

    if not hook_id:
        return {"error": "Failed to create hook"}, HTTPStatus.INTERNAL_SERVER_ERROR

    hook = get_hook(hook_id)
    return {"message": "Hook created", "hook": hook}, HTTPStatus.CREATED


@hooks_bp.get("/<int:hook_id>")
def get_hook_endpoint(path: HookPath):
    """Get hook details."""
    hook = get_hook(path.hook_id)
    if not hook:
        return {"error": "Hook not found"}, HTTPStatus.NOT_FOUND
    return hook, HTTPStatus.OK


@hooks_bp.put("/<int:hook_id>")
def update_hook_endpoint(path: HookPath):
    """Update a hook."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    event = data.get("event")
    if event and event not in VALID_EVENTS:
        return {
            "error": f"Invalid event type. Must be one of: {', '.join(VALID_EVENTS)}"
        }, HTTPStatus.BAD_REQUEST

    if not update_hook(
        path.hook_id,
        name=data.get("name"),
        event=event,
        description=data.get("description"),
        content=data.get("content"),
        enabled=data.get("enabled"),
    ):
        return {"error": "Hook not found or no changes made"}, HTTPStatus.NOT_FOUND

    hook = get_hook(path.hook_id)
    return hook, HTTPStatus.OK


@hooks_bp.delete("/<int:hook_id>")
def delete_hook_endpoint(path: HookPath):
    """Delete a hook."""
    if not delete_hook(path.hook_id):
        return {"error": "Hook not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Hook deleted"}, HTTPStatus.OK


@hooks_bp.get("/events")
def list_hook_events():
    """List all valid hook event types."""
    return {"events": VALID_EVENTS}, HTTPStatus.OK


@hooks_bp.get("/project/<project_id>")
def list_project_hooks(path: ProjectHooksPath):
    """List hooks for a specific project."""
    hooks = get_hooks_by_project(path.project_id)
    return {"hooks": hooks, "project_id": path.project_id}, HTTPStatus.OK


@hooks_bp.get("/event/<event>")
def list_hooks_by_event(event: str):
    """List enabled hooks for a specific event type."""
    if event not in VALID_EVENTS:
        return {
            "error": f"Invalid event type. Must be one of: {', '.join(VALID_EVENTS)}"
        }, HTTPStatus.BAD_REQUEST
    hooks = get_hooks_by_event(event)
    return {"hooks": hooks, "event": event}, HTTPStatus.OK


@hooks_bp.post("/generate/stream")
def generate_hook_stream():
    """Generate a hook configuration from a description using AI (streaming)."""
    from ..services.hook_generation_service import HookGenerationService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    description = (data.get("description") or "").strip()
    if len(description) < 10:
        return {"error": "Description must be at least 10 characters"}, HTTPStatus.BAD_REQUEST

    return Response(
        HookGenerationService.generate_streaming(description),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
