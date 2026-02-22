"""Trigger management API endpoints (primary routes)."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import get_trigger
from ..services.execution_service import ExecutionService
from ..services.trigger_service import TriggerService

tag = Tag(name="Triggers", description="Trigger management")
triggers_bp = APIBlueprint("triggers", __name__, url_prefix="/admin/triggers", abp_tags=[tag])


class TriggerPath(BaseModel):
    trigger_id: str = Field(..., description="Trigger ID")


@triggers_bp.get("/")
def list_triggers():
    """List all triggers with path counts and execution status."""
    result, status = TriggerService.list_triggers()
    return result, status


@triggers_bp.post("/")
def create_trigger():
    """Create a new trigger."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    result, status = TriggerService.create_trigger(data)
    return result, status


@triggers_bp.get("/<trigger_id>")
def get_trigger_detail(path: TriggerPath):
    """Get trigger details with paths."""
    result, status = TriggerService.get_trigger_detail(path.trigger_id)
    return result, status


@triggers_bp.put("/<trigger_id>")
def update_trigger(path: TriggerPath):
    """Update a trigger."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    result, status = TriggerService.update_trigger(path.trigger_id, data)
    return result, status


@triggers_bp.delete("/<trigger_id>")
def delete_trigger(path: TriggerPath):
    """Delete a trigger (non-predefined only)."""
    result, status = TriggerService.delete_trigger(path.trigger_id)
    return result, status


@triggers_bp.get("/<trigger_id>/paths")
def list_trigger_paths(path: TriggerPath):
    """List all project paths for a trigger."""
    result, status = TriggerService.list_paths(path.trigger_id)
    return result, status


@triggers_bp.post("/<trigger_id>/paths")
def add_trigger_path(path: TriggerPath):
    """Add a project path to a trigger."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    result, status = TriggerService.add_path(path.trigger_id, data)
    return result, status


@triggers_bp.delete("/<trigger_id>/paths")
def remove_trigger_path(path: TriggerPath):
    """Remove a project path from a trigger."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    result, status = TriggerService.remove_path(path.trigger_id, data)
    return result, status


class TriggerProjectPath(BaseModel):
    trigger_id: str = Field(..., description="Trigger ID")
    project_id: str = Field(..., description="Project ID")


@triggers_bp.post("/<trigger_id>/projects")
def add_trigger_project(path: TriggerPath):
    """Add a project reference to a trigger."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    project_id = data.get("project_id")
    if not project_id:
        return {"error": "project_id is required"}, HTTPStatus.BAD_REQUEST
    result, status = TriggerService.add_project(path.trigger_id, project_id)
    return result, status


@triggers_bp.delete("/<trigger_id>/projects/<project_id>")
def remove_trigger_project(path: TriggerProjectPath):
    """Remove a project reference from a trigger."""
    result, status = TriggerService.remove_project(path.trigger_id, path.project_id)
    return result, status


@triggers_bp.put("/<trigger_id>/auto-resolve")
def set_auto_resolve(path: TriggerPath):
    """Enable/disable auto-resolve and PR creation for the security trigger."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    auto_resolve = bool(data.get("auto_resolve", False))
    result, status = TriggerService.update_auto_resolve(path.trigger_id, auto_resolve)
    return result, status


@triggers_bp.get("/<trigger_id>/status")
def get_trigger_status(path: TriggerPath):
    """Get execution status for a trigger."""
    trigger = get_trigger(path.trigger_id)
    if not trigger:
        return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

    status = ExecutionService.get_status(path.trigger_id)
    return status, HTTPStatus.OK


@triggers_bp.post("/<trigger_id>/run")
def run_trigger(path: TriggerPath):
    """Manually trigger a trigger to run."""
    data = request.get_json() or {}
    message = data.get("message", "")
    result, status = TriggerService.run(path.trigger_id, message)
    return result, status
