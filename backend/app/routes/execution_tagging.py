"""Execution tagging API endpoints.

Provides routes for managing execution tags (create, list, delete) and
for assigning/removing tags from individual executions.
"""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.execution_tags import (
    add_tag_to_execution,
    create_tag,
    delete_tag,
    get_executions_with_tags,
    list_tags,
    remove_tag_from_execution,
)

tag = Tag(name="Execution Tagging", description="Tag executions for categorization and search")
execution_tagging_bp = APIBlueprint(
    "execution_tagging", __name__, url_prefix="/admin", abp_tags=[tag]
)


# --- Path models ---


class TagPath(BaseModel):
    tag_id: str = Field(..., description="Execution tag ID")


class ExecutionTagPath(BaseModel):
    execution_id: str = Field(..., description="Execution ID")
    tag_id: str = Field(..., description="Execution tag ID")


class ExecutionPath(BaseModel):
    execution_id: str = Field(..., description="Execution ID")


# --- Tag management ---


@execution_tagging_bp.get("/execution-tags")
def list_execution_tags():
    """List all execution tags with their assignment counts."""
    tags = list_tags()
    return {"tags": tags, "total": len(tags)}, HTTPStatus.OK


@execution_tagging_bp.post("/execution-tags")
def create_execution_tag():
    """Create a new execution tag."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    name = (data.get("name") or "").strip()
    color = (data.get("color") or "blue").strip()

    if not name:
        return error_response("BAD_REQUEST", "name is required", HTTPStatus.BAD_REQUEST)

    valid_colors = {"blue", "green", "amber", "red", "purple"}
    if color not in valid_colors:
        return error_response(
            "BAD_REQUEST",
            f"color must be one of: {', '.join(sorted(valid_colors))}",
            HTTPStatus.BAD_REQUEST,
        )

    result = create_tag(name=name, color=color)
    if result is None:
        return error_response(
            "CONFLICT",
            f"A tag named '{name}' already exists",
            HTTPStatus.CONFLICT,
        )

    return {"tag": result}, HTTPStatus.CREATED


@execution_tagging_bp.delete("/execution-tags/<tag_id>")
def delete_execution_tag(path: TagPath):
    """Delete an execution tag and all its assignments."""
    deleted = delete_tag(path.tag_id)
    if not deleted:
        return error_response("NOT_FOUND", "Tag not found", HTTPStatus.NOT_FOUND)
    return {"message": "Tag deleted"}, HTTPStatus.OK


# --- Execution tagging ---


@execution_tagging_bp.get("/execution-tagging")
def list_tagged_executions():
    """List executions with their tag arrays.

    Supports optional ``tag_ids`` query parameter (comma-separated) to filter
    by executions that have all of the specified tags applied.
    Pagination via ``limit`` and ``offset`` query params.
    """
    tag_ids_param = request.args.get("tag_ids")
    tag_ids = [t.strip() for t in tag_ids_param.split(",") if t.strip()] if tag_ids_param else None
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return error_response(
            "BAD_REQUEST", "limit and offset must be integers", HTTPStatus.BAD_REQUEST
        )

    executions = get_executions_with_tags(limit=limit, offset=offset, tag_ids=tag_ids)
    return {"executions": executions, "total": len(executions)}, HTTPStatus.OK


@execution_tagging_bp.post("/execution-tagging/<execution_id>/tags")
def add_tag_to_execution_route(path: ExecutionPath):
    """Add a tag to an execution."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    tag_id = (data.get("tag_id") or "").strip()
    if not tag_id:
        return error_response("BAD_REQUEST", "tag_id is required", HTTPStatus.BAD_REQUEST)

    success = add_tag_to_execution(tag_id=tag_id, execution_id=path.execution_id)
    if not success:
        return error_response(
            "BAD_REQUEST",
            "Failed to add tag — tag or execution may not exist, or tag already applied",
            HTTPStatus.BAD_REQUEST,
        )
    return {"message": "Tag added to execution"}, HTTPStatus.CREATED


@execution_tagging_bp.delete("/execution-tagging/<execution_id>/tags/<tag_id>")
def remove_tag_from_execution_route(path: ExecutionTagPath):
    """Remove a tag from an execution."""
    removed = remove_tag_from_execution(tag_id=path.tag_id, execution_id=path.execution_id)
    if not removed:
        return error_response(
            "NOT_FOUND",
            "Tag assignment not found for this execution",
            HTTPStatus.NOT_FOUND,
        )
    return {"message": "Tag removed from execution"}, HTTPStatus.OK
