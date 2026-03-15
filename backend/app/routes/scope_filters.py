"""API endpoints for repository scope filters."""

from http import HTTPStatus
from typing import Optional

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.scope_filters import (
    add_pattern,
    delete_pattern,
    get_scope_filter,
    list_scope_filters,
    update_scope_filter,
    upsert_scope_filter,
)
from ..services.rbac_service import require_role

tag = Tag(name="scope-filters", description="Repository scope filters for bots")
scope_filters_bp = APIBlueprint("scope_filters", __name__, url_prefix="/admin", abp_tags=[tag])


class FilterPath(BaseModel):
    filter_id: str = Field(..., description="Scope filter ID")


class PatternPath(BaseModel):
    filter_id: str = Field(..., description="Scope filter ID")
    pattern_id: str = Field(..., description="Pattern ID")


class UpsertFilterBody(BaseModel):
    trigger_id: str = Field(..., description="Trigger to create/update a filter for")
    mode: str = Field(default="denylist", description="allowlist or denylist")
    enabled: bool = Field(default=True, description="Whether the filter is active")


class UpdateFilterBody(BaseModel):
    mode: Optional[str] = Field(default=None, description="allowlist or denylist")
    enabled: Optional[bool] = Field(default=None, description="Whether the filter is active")


class AddPatternBody(BaseModel):
    type: str = Field(..., description="Pattern type: repo, branch, or author")
    pattern: str = Field(..., min_length=1, description="Regex pattern string")
    description: str = Field(default="", description="Human-readable description")


@scope_filters_bp.get("/scope-filters")
@require_role("viewer", "operator", "editor", "admin")
def list_filters():
    """List all scope filters (joined with trigger name)."""
    filters = list_scope_filters()
    return {"filters": filters, "total": len(filters)}, HTTPStatus.OK


@scope_filters_bp.get("/scope-filters/<filter_id>")
@require_role("viewer", "operator", "editor", "admin")
def get_filter(path: FilterPath):
    """Get a scope filter with its patterns."""
    sf = get_scope_filter(path.filter_id)
    if sf is None:
        return error_response("NOT_FOUND", "Scope filter not found", HTTPStatus.NOT_FOUND)
    return sf, HTTPStatus.OK


@scope_filters_bp.post("/scope-filters")
@require_role("editor", "admin")
def create_or_update_filter(body: UpsertFilterBody):
    """Create or update a scope filter for a trigger."""
    filter_id = upsert_scope_filter(
        trigger_id=body.trigger_id,
        mode=body.mode,
        enabled=body.enabled,
    )
    sf = get_scope_filter(filter_id)
    return {"message": "Scope filter saved", "filter": sf}, HTTPStatus.OK


@scope_filters_bp.put("/scope-filters/<filter_id>")
@require_role("editor", "admin")
def update_filter(path: FilterPath, body: UpdateFilterBody):
    """Update mode and/or enabled state of a scope filter."""
    updated = update_scope_filter(
        filter_id=path.filter_id,
        mode=body.mode,
        enabled=body.enabled,
    )
    if not updated:
        return error_response(
            "NOT_FOUND", "Scope filter not found or no changes", HTTPStatus.NOT_FOUND
        )
    sf = get_scope_filter(path.filter_id)
    return sf, HTTPStatus.OK


@scope_filters_bp.post("/scope-filters/<filter_id>/patterns")
@require_role("editor", "admin")
def add_filter_pattern(path: FilterPath, body: AddPatternBody):
    """Add a regex pattern to a scope filter."""
    sf = get_scope_filter(path.filter_id)
    if sf is None:
        return error_response("NOT_FOUND", "Scope filter not found", HTTPStatus.NOT_FOUND)
    pattern_id = add_pattern(
        filter_id=path.filter_id,
        type=body.type,
        pattern=body.pattern,
        description=body.description,
    )
    updated = get_scope_filter(path.filter_id)
    new_pattern = next((p for p in (updated or {}).get("patterns", []) if p["id"] == pattern_id), None)
    return {"message": "Pattern added", "pattern": new_pattern}, HTTPStatus.CREATED


@scope_filters_bp.delete("/scope-filters/<filter_id>/patterns/<pattern_id>")
@require_role("editor", "admin")
def delete_filter_pattern(path: PatternPath):
    """Delete a pattern from a scope filter."""
    deleted = delete_pattern(path.pattern_id)
    if not deleted:
        return error_response("NOT_FOUND", "Pattern not found", HTTPStatus.NOT_FOUND)
    return {"message": "Pattern deleted"}, HTTPStatus.OK
