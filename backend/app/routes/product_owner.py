"""Product owner API endpoints -- decisions, milestones, meetings, dashboard."""

import json
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    add_milestone_project,
    add_product_decision,
    add_product_milestone,
    delete_milestone_project,
    delete_product_decision,
    delete_product_milestone,
    get_decisions_by_product,
    get_milestones_by_product,
    get_product,
    get_product_decision,
    get_product_milestone,
    get_projects_for_milestone,
    update_product,
    update_product_decision,
    update_product_milestone,
)
from ..services.product_owner_service import ProductOwnerService

tag = Tag(name="product-owner", description="Product owner dashboard operations")
product_owner_bp = APIBlueprint(
    "product_owner", __name__, url_prefix="/admin/products", abp_tags=[tag]
)


# --- Path models ---


class ProductPath(BaseModel):
    product_id: str = Field(..., description="Product ID")


class DecisionPath(BaseModel):
    product_id: str = Field(..., description="Product ID")
    decision_id: str = Field(..., description="Decision ID")


class MilestonePath(BaseModel):
    product_id: str = Field(..., description="Product ID")
    milestone_id: str = Field(..., description="Milestone ID")


class MilestoneProjectPath(BaseModel):
    product_id: str = Field(..., description="Product ID")
    milestone_id: str = Field(..., description="Milestone ID")
    project_id: str = Field(..., description="Project ID")


# --- Helper ---


def _check_product(product_id: str):
    """Return product dict or None. Caller checks for None and returns 404."""
    return get_product(product_id)


# =============================================================================
# Decisions CRUD
# =============================================================================


@product_owner_bp.get("/<product_id>/decisions")
def list_product_decisions(path: ProductPath):
    """List decisions for a product with optional status and tag filters."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    status = request.args.get("status")
    tag_filter = request.args.get("tag")
    decisions = get_decisions_by_product(path.product_id, status=status, tag=tag_filter)
    return {"decisions": decisions}, HTTPStatus.OK


@product_owner_bp.post("/<product_id>/decisions")
def create_product_decision(path: ProductPath):
    """Create a new decision for a product."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    data = request.get_json()
    if not data or not data.get("title"):
        return {"error": "title is required"}, HTTPStatus.BAD_REQUEST

    tags = data.get("tags", [])
    tags_json = json.dumps(tags) if tags else None

    decision_id = add_product_decision(
        product_id=path.product_id,
        title=data["title"],
        description=data.get("description"),
        rationale=data.get("rationale"),
        decision_type=data.get("decision_type", "technical"),
        tags_json=tags_json,
    )
    if not decision_id:
        return {"error": "Failed to create decision"}, HTTPStatus.INTERNAL_SERVER_ERROR

    decision = get_product_decision(decision_id)
    return {"message": "Decision created", "decision": decision}, HTTPStatus.CREATED


@product_owner_bp.get("/<product_id>/decisions/<decision_id>")
def get_product_decision_endpoint(path: DecisionPath):
    """Get a single decision by ID."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    decision = get_product_decision(path.decision_id)
    if not decision:
        return {"error": "Decision not found"}, HTTPStatus.NOT_FOUND
    return {"decision": decision}, HTTPStatus.OK


@product_owner_bp.put("/<product_id>/decisions/<decision_id>")
def update_product_decision_endpoint(path: DecisionPath):
    """Update a decision."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    kwargs = {}
    for key in (
        "title",
        "description",
        "rationale",
        "tags_json",
        "status",
        "decided_by",
        "context_json",
        "decision_type",
    ):
        if key in data:
            kwargs[key] = data[key]

    if not update_product_decision(path.decision_id, **kwargs):
        return {"error": "Decision not found or no changes"}, HTTPStatus.NOT_FOUND

    decision = get_product_decision(path.decision_id)
    return {"message": "Decision updated", "decision": decision}, HTTPStatus.OK


@product_owner_bp.delete("/<product_id>/decisions/<decision_id>")
def delete_product_decision_endpoint(path: DecisionPath):
    """Delete a decision."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    if not delete_product_decision(path.decision_id):
        return {"error": "Decision not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Decision deleted"}, HTTPStatus.OK


# =============================================================================
# Milestones CRUD
# =============================================================================


@product_owner_bp.get("/<product_id>/milestones")
def list_product_milestones(path: ProductPath):
    """List milestones for a product with optional status filter."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    status = request.args.get("status")
    milestones = get_milestones_by_product(path.product_id, status=status)
    return {"milestones": milestones}, HTTPStatus.OK


@product_owner_bp.post("/<product_id>/milestones")
def create_product_milestone(path: ProductPath):
    """Create a new milestone for a product."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    data = request.get_json()
    if not data or not data.get("version") or not data.get("title"):
        return {"error": "version and title are required"}, HTTPStatus.BAD_REQUEST

    milestone_id = add_product_milestone(
        product_id=path.product_id,
        version=data["version"],
        title=data["title"],
        description=data.get("description"),
        target_date=data.get("target_date"),
        sort_order=data.get("sort_order", 0),
        progress_pct=data.get("progress_pct", 0),
    )
    if not milestone_id:
        return {"error": "Failed to create milestone"}, HTTPStatus.INTERNAL_SERVER_ERROR

    milestone = get_product_milestone(milestone_id)
    return {"message": "Milestone created", "milestone": milestone}, HTTPStatus.CREATED


@product_owner_bp.get("/<product_id>/milestones/<milestone_id>")
def get_product_milestone_endpoint(path: MilestonePath):
    """Get a single milestone with linked projects."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    milestone = get_product_milestone(path.milestone_id)
    if not milestone:
        return {"error": "Milestone not found"}, HTTPStatus.NOT_FOUND

    milestone["projects"] = get_projects_for_milestone(path.milestone_id)
    return {"milestone": milestone}, HTTPStatus.OK


@product_owner_bp.put("/<product_id>/milestones/<milestone_id>")
def update_product_milestone_endpoint(path: MilestonePath):
    """Update a milestone."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    kwargs = {}
    for key in (
        "version",
        "title",
        "description",
        "status",
        "target_date",
        "sort_order",
        "progress_pct",
        "completed_date",
    ):
        if key in data:
            kwargs[key] = data[key]

    if not update_product_milestone(path.milestone_id, **kwargs):
        return {"error": "Milestone not found or no changes"}, HTTPStatus.NOT_FOUND

    milestone = get_product_milestone(path.milestone_id)
    return {"message": "Milestone updated", "milestone": milestone}, HTTPStatus.OK


@product_owner_bp.delete("/<product_id>/milestones/<milestone_id>")
def delete_product_milestone_endpoint(path: MilestonePath):
    """Delete a milestone."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    if not delete_product_milestone(path.milestone_id):
        return {"error": "Milestone not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Milestone deleted"}, HTTPStatus.OK


# =============================================================================
# Milestone-Project Junction
# =============================================================================


@product_owner_bp.get("/<product_id>/milestones/<milestone_id>/projects")
def list_milestone_projects(path: MilestonePath):
    """List projects linked to a milestone."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    projects = get_projects_for_milestone(path.milestone_id)
    return {"projects": projects}, HTTPStatus.OK


@product_owner_bp.post("/<product_id>/milestones/<milestone_id>/projects")
def link_milestone_project(path: MilestonePath):
    """Link a project to a milestone."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    data = request.get_json()
    if not data or not data.get("project_id"):
        return {"error": "project_id is required"}, HTTPStatus.BAD_REQUEST

    result = add_milestone_project(
        milestone_id=path.milestone_id,
        project_id=data["project_id"],
        contribution=data.get("contribution"),
    )
    if result is None:
        return {
            "error": "Failed to link project (already linked or invalid IDs)"
        }, HTTPStatus.BAD_REQUEST

    return {"message": "Project linked to milestone"}, HTTPStatus.CREATED


@product_owner_bp.delete("/<product_id>/milestones/<milestone_id>/projects/<project_id>")
def unlink_milestone_project(path: MilestoneProjectPath):
    """Unlink a project from a milestone."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    if not delete_milestone_project(path.milestone_id, path.project_id):
        return {"error": "Link not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Project unlinked from milestone"}, HTTPStatus.OK


# =============================================================================
# Owner Assignment
# =============================================================================


@product_owner_bp.put("/<product_id>/owner")
def assign_product_owner(path: ProductPath):
    """Assign a super_agent as the product owner.

    The owner_agent_id must reference a super_agents.id (not agents.id)
    because agent_messages.from_agent_id has FOREIGN KEY to super_agents(id).
    """
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    data = request.get_json()
    if not data or "owner_agent_id" not in data:
        return {"error": "owner_agent_id is required"}, HTTPStatus.BAD_REQUEST

    update_product(path.product_id, owner_agent_id=data["owner_agent_id"])
    product = get_product(path.product_id)
    return {"message": "Owner assigned", "product": product}, HTTPStatus.OK


# =============================================================================
# Meeting Protocol
# =============================================================================


@product_owner_bp.post("/<product_id>/meetings/standup")
def trigger_standup(path: ProductPath):
    """Trigger a standup meeting with project leader agents."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    try:
        result = ProductOwnerService.trigger_standup_meeting(path.product_id)
        return result, HTTPStatus.OK
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.BAD_REQUEST


@product_owner_bp.get("/<product_id>/meetings/history")
def meeting_history(path: ProductPath):
    """Get standup meeting history for a product."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    history = ProductOwnerService.get_meeting_history(path.product_id)
    return {"meetings": history}, HTTPStatus.OK


# =============================================================================
# Dashboard Aggregation
# =============================================================================


@product_owner_bp.get("/<product_id>/dashboard")
def get_dashboard(path: ProductPath):
    """Get aggregated dashboard data for a product."""
    if not _check_product(path.product_id):
        return {"error": "Product not found"}, HTTPStatus.NOT_FOUND

    data = ProductOwnerService.get_dashboard_data(path.product_id)
    return data, HTTPStatus.OK
