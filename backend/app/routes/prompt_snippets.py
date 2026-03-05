"""Prompt snippet library API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..db.prompt_snippets import (
    add_snippet,
    delete_snippet,
    get_all_snippets,
    get_snippet,
    get_snippet_by_name,
    update_snippet,
)
from ..services.prompt_snippet_service import SnippetService
from ..services.rbac_service import require_role

tag = Tag(name="Prompt Snippets", description="Reusable prompt fragment library")
prompt_snippets_bp = APIBlueprint(
    "prompt_snippets", __name__, url_prefix="/admin/prompt-snippets", abp_tags=[tag]
)


class SnippetPath(BaseModel):
    snippet_id: str = Field(..., description="Snippet ID")


@prompt_snippets_bp.get("/")
@require_role("viewer", "operator", "editor", "admin")
def list_snippets():
    """List all prompt snippets."""
    snippets = get_all_snippets()
    return {"snippets": snippets}, HTTPStatus.OK


@prompt_snippets_bp.post("/")
@require_role("editor", "admin")
def create_snippet():
    """Create a new prompt snippet."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    name = data.get("name", "").strip()
    content = data.get("content", "").strip()
    description = data.get("description", "")

    if not name:
        return {"error": "name is required"}, HTTPStatus.BAD_REQUEST
    if not content:
        return {"error": "content is required"}, HTTPStatus.BAD_REQUEST

    # Validate name format
    import re

    if not re.match(r"^[\w][\w-]*$", name):
        return {
            "error": "name must start with a word character and contain only word characters and hyphens"
        }, HTTPStatus.BAD_REQUEST

    # Check uniqueness
    existing = get_snippet_by_name(name)
    if existing:
        return {"error": f"A snippet named '{name}' already exists"}, HTTPStatus.CONFLICT

    snippet_id = add_snippet(name=name, content=content, description=description)
    if snippet_id:
        snippet = get_snippet(snippet_id)
        return {"message": "Snippet created", "snippet": snippet}, HTTPStatus.CREATED
    else:
        return {"error": "Failed to create snippet"}, HTTPStatus.INTERNAL_SERVER_ERROR


@prompt_snippets_bp.get("/<snippet_id>")
@require_role("viewer", "operator", "editor", "admin")
def get_snippet_detail(path: SnippetPath):
    """Get a single prompt snippet."""
    snippet = get_snippet(path.snippet_id)
    if not snippet:
        return {"error": "Snippet not found"}, HTTPStatus.NOT_FOUND
    return snippet, HTTPStatus.OK


@prompt_snippets_bp.put("/<snippet_id>")
@require_role("editor", "admin")
def update_snippet_endpoint(path: SnippetPath):
    """Update a prompt snippet."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    snippet = get_snippet(path.snippet_id)
    if not snippet:
        return {"error": "Snippet not found"}, HTTPStatus.NOT_FOUND

    name = data.get("name")
    if name is not None:
        import re

        name = name.strip()
        if not re.match(r"^[\w][\w-]*$", name):
            return {
                "error": "name must start with a word character and contain only word characters and hyphens"
            }, HTTPStatus.BAD_REQUEST
        # Check uniqueness if name changed
        if name != snippet["name"]:
            existing = get_snippet_by_name(name)
            if existing:
                return {
                    "error": f"A snippet named '{name}' already exists"
                }, HTTPStatus.CONFLICT

    success = update_snippet(
        path.snippet_id,
        name=data.get("name"),
        content=data.get("content"),
        description=data.get("description"),
    )
    if success:
        updated = get_snippet(path.snippet_id)
        return {"message": "Snippet updated", "snippet": updated}, HTTPStatus.OK
    else:
        return {"error": "No changes made"}, HTTPStatus.BAD_REQUEST


@prompt_snippets_bp.delete("/<snippet_id>")
@require_role("editor", "admin")
def delete_snippet_endpoint(path: SnippetPath):
    """Delete a prompt snippet."""
    snippet = get_snippet(path.snippet_id)
    if not snippet:
        return {"error": "Snippet not found"}, HTTPStatus.NOT_FOUND

    success = delete_snippet(path.snippet_id)
    if success:
        return {"message": "Snippet deleted"}, HTTPStatus.OK
    else:
        return {"error": "Failed to delete snippet"}, HTTPStatus.INTERNAL_SERVER_ERROR


@prompt_snippets_bp.post("/resolve")
@require_role("viewer", "operator", "editor", "admin")
def resolve_snippets():
    """Resolve {{snippet}} references in text (for debugging/testing)."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    text = data.get("text", "")
    if not text:
        return {"error": "text is required"}, HTTPStatus.BAD_REQUEST

    resolved = SnippetService.resolve_snippets(text)
    return {"original": text, "resolved": resolved}, HTTPStatus.OK
