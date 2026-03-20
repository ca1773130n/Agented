"""Hook management API endpoints."""

from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response
from app.models.hook import VALID_EVENTS, CreateHookRequest, GenerateHookRequest, UpdateHookRequest

from ..database import (
    count_hooks,
    delete_hook,
    get_all_hooks,
    get_hook,
    get_hooks_by_event,
    get_hooks_by_project,
    update_hook,
)
from ..database import (
    create_hook as db_create_hook,
)
from ..models.common import PaginationQuery

tag = Tag(name="hooks", description="Hook management operations")
hooks_bp = APIBlueprint("hooks", __name__, url_prefix="/admin/hooks", abp_tags=[tag])


class HookPath(BaseModel):
    hook_id: int = Field(..., description="Hook ID")


class ProjectHooksPath(BaseModel):
    project_id: str = Field(..., description="Project ID")


class EventPath(BaseModel):
    event: str = Field(..., description="Event type")


@hooks_bp.get("/")
def list_hooks(query: PaginationQuery):
    """List all hooks (global + per-project) with optional pagination."""
    project_id = request.args.get("project_id")
    total_count = count_hooks(project_id)
    hooks = get_all_hooks(project_id, limit=query.limit, offset=query.offset or 0)
    return {"hooks": hooks, "total_count": total_count}, HTTPStatus.OK


@hooks_bp.post("/")
def create_hook(body: CreateHookRequest):
    """Create a new hook."""
    hook_id = db_create_hook(
        name=body.name,
        event=body.event,
        description=body.description,
        content=body.content,
        enabled=body.enabled,
        project_id=body.project_id,
        source_path=body.source_path,
    )

    if not hook_id:
        return error_response(
            "INTERNAL_SERVER_ERROR", "Failed to create hook", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    hook = get_hook(hook_id)
    return {"message": "Hook created", "hook": hook}, HTTPStatus.CREATED


@hooks_bp.get("/<int:hook_id>")
def get_hook_endpoint(path: HookPath):
    """Get hook details."""
    hook = get_hook(path.hook_id)
    if not hook:
        return error_response("NOT_FOUND", "Hook not found", HTTPStatus.NOT_FOUND)
    return hook, HTTPStatus.OK


@hooks_bp.put("/<int:hook_id>")
def update_hook_endpoint(path: HookPath, body: UpdateHookRequest):
    """Update a hook."""
    if not update_hook(
        path.hook_id,
        name=body.name,
        event=body.event,
        description=body.description,
        content=body.content,
        enabled=body.enabled,
    ):
        return error_response(
            "NOT_FOUND", "Hook not found or no changes made", HTTPStatus.NOT_FOUND
        )

    hook = get_hook(path.hook_id)
    return hook, HTTPStatus.OK


@hooks_bp.delete("/<int:hook_id>")
def delete_hook_endpoint(path: HookPath):
    """Delete a hook."""
    if not delete_hook(path.hook_id):
        return error_response("NOT_FOUND", "Hook not found", HTTPStatus.NOT_FOUND)
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
def list_hooks_by_event(path: EventPath):
    """List enabled hooks for a specific event type."""
    event = path.event
    if event not in VALID_EVENTS:
        return error_response(
            "BAD_REQUEST",
            f"Invalid event type. Must be one of: {', '.join(VALID_EVENTS)}",
            HTTPStatus.BAD_REQUEST,
        )
    hooks = get_hooks_by_event(event)
    return {"hooks": hooks, "event": event}, HTTPStatus.OK


@hooks_bp.post("/generate/stream")
def generate_hook_stream(body: GenerateHookRequest):
    """Generate a hook configuration from a description using AI (streaming)."""
    from ..services.hook_generation_service import HookGenerationService

    return Response(
        HookGenerationService.generate_streaming(body.description),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
