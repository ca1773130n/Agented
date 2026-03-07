"""Command management API endpoints."""

from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.command import CreateCommandRequest, GenerateCommandRequest, UpdateCommandRequest
from app.models.common import error_response

from ..database import (
    count_commands,
    delete_command,
    get_all_commands,
    get_command,
    get_commands_by_project,
    update_command,
)
from ..database import (
    create_command as db_create_command,
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
def create_command(body: CreateCommandRequest):
    """Create a new command."""
    command_id = db_create_command(
        name=body.name,
        description=body.description,
        content=body.content,
        arguments=body.arguments,
        enabled=body.enabled,
        project_id=body.project_id,
        source_path=body.source_path,
    )

    if not command_id:
        return error_response(
            "INTERNAL_SERVER_ERROR", "Failed to create command", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    command = get_command(command_id)
    return {"message": "Command created", "command": command}, HTTPStatus.CREATED


@commands_bp.get("/<int:command_id>")
def get_command_endpoint(path: CommandPath):
    """Get command details."""
    command = get_command(path.command_id)
    if not command:
        return error_response("NOT_FOUND", "Command not found", HTTPStatus.NOT_FOUND)
    return command, HTTPStatus.OK


@commands_bp.put("/<int:command_id>")
def update_command_endpoint(path: CommandPath, body: UpdateCommandRequest):
    """Update a command."""
    if not update_command(
        path.command_id,
        name=body.name,
        description=body.description,
        content=body.content,
        arguments=body.arguments,
        enabled=body.enabled,
    ):
        return error_response(
            "NOT_FOUND", "Command not found or no changes made", HTTPStatus.NOT_FOUND
        )

    command = get_command(path.command_id)
    return command, HTTPStatus.OK


@commands_bp.delete("/<int:command_id>")
def delete_command_endpoint(path: CommandPath):
    """Delete a command."""
    if not delete_command(path.command_id):
        return error_response("NOT_FOUND", "Command not found", HTTPStatus.NOT_FOUND)
    return {"message": "Command deleted"}, HTTPStatus.OK


@commands_bp.get("/project/<project_id>")
def list_project_commands(path: ProjectCommandsPath):
    """List commands for a specific project."""
    commands = get_commands_by_project(path.project_id)
    return {"commands": commands, "project_id": path.project_id}, HTTPStatus.OK


@commands_bp.post("/generate/stream")
def generate_command_stream(body: GenerateCommandRequest):
    """Generate a command configuration from a description using AI (streaming)."""
    from ..services.command_generation_service import CommandGenerationService

    return Response(
        CommandGenerationService.generate_streaming(body.description),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
