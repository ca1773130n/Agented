"""Command management API endpoints."""

from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    add_command,
    count_commands,
    delete_command,
    get_all_commands,
    get_command,
    get_commands_by_project,
    update_command,
)
from ..models.common import PaginationQuery

tag = Tag(name="commands", description="Command management operations")
commands_bp = APIBlueprint("commands", __name__, url_prefix="/admin/commands", abp_tags=[tag])


class CommandPath(BaseModel):
    command_id: int = Field(..., description="Command ID")


class ProjectCommandsPath(BaseModel):
    project_id: str = Field(..., description="Project ID")


@commands_bp.get("/")
def list_commands(query: PaginationQuery):
    """List all commands (global + per-project) with optional pagination."""
    project_id = request.args.get("project_id")
    total_count = count_commands(project_id)
    commands = get_all_commands(project_id, limit=query.limit, offset=query.offset or 0)
    return {"commands": commands, "total_count": total_count}, HTTPStatus.OK


@commands_bp.post("/")
def create_command():
    """Create a new command."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    name = data.get("name")
    if not name:
        return {"error": "name is required"}, HTTPStatus.BAD_REQUEST

    command_id = add_command(
        name=name,
        description=data.get("description"),
        content=data.get("content"),
        arguments=data.get("arguments"),
        enabled=data.get("enabled", True),
        project_id=data.get("project_id"),
        source_path=data.get("source_path"),
    )

    if not command_id:
        return {"error": "Failed to create command"}, HTTPStatus.INTERNAL_SERVER_ERROR

    command = get_command(command_id)
    return {"message": "Command created", "command": command}, HTTPStatus.CREATED


@commands_bp.get("/<int:command_id>")
def get_command_endpoint(path: CommandPath):
    """Get command details."""
    command = get_command(path.command_id)
    if not command:
        return {"error": "Command not found"}, HTTPStatus.NOT_FOUND
    return command, HTTPStatus.OK


@commands_bp.put("/<int:command_id>")
def update_command_endpoint(path: CommandPath):
    """Update a command."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    if not update_command(
        path.command_id,
        name=data.get("name"),
        description=data.get("description"),
        content=data.get("content"),
        arguments=data.get("arguments"),
        enabled=data.get("enabled"),
    ):
        return {"error": "Command not found or no changes made"}, HTTPStatus.NOT_FOUND

    command = get_command(path.command_id)
    return command, HTTPStatus.OK


@commands_bp.delete("/<int:command_id>")
def delete_command_endpoint(path: CommandPath):
    """Delete a command."""
    if not delete_command(path.command_id):
        return {"error": "Command not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Command deleted"}, HTTPStatus.OK


@commands_bp.get("/project/<project_id>")
def list_project_commands(path: ProjectCommandsPath):
    """List commands for a specific project."""
    commands = get_commands_by_project(path.project_id)
    return {"commands": commands, "project_id": path.project_id}, HTTPStatus.OK


@commands_bp.post("/generate/stream")
def generate_command_stream():
    """Generate a command configuration from a description using AI (streaming)."""
    from ..services.command_generation_service import CommandGenerationService

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    description = (data.get("description") or "").strip()
    if len(description) < 10:
        return {"error": "Description must be at least 10 characters"}, HTTPStatus.BAD_REQUEST

    return Response(
        CommandGenerationService.generate_streaming(description),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
