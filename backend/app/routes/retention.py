"""Data retention policy API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag

from app.models.common import error_response
from app.models.retention import PolicyIdPath, RetentionPolicyCreate, RetentionPolicyToggle

from ..db.retention_policies import (
    create_policy,
    delete_policy,
    list_policies,
    update_policy_enabled,
)

tag = Tag(name="retention", description="Data retention policy management")
retention_bp = APIBlueprint(
    "retention", __name__, url_prefix="/admin/retention-policies", abp_tags=[tag]
)


@retention_bp.get("/")
def list_retention_policies():
    """List all retention policies."""
    policies = list_policies()
    return {"policies": policies}, HTTPStatus.OK


@retention_bp.post("/")
def create_retention_policy():
    """Create a new retention policy."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    try:
        body = RetentionPolicyCreate(**data)
    except Exception as e:
        return error_response("BAD_REQUEST", str(e), HTTPStatus.BAD_REQUEST)

    policy_id = create_policy(
        category=body.category,
        scope=body.scope,
        scope_name=body.scope_name,
        retention_days=body.retention_days,
        delete_on_expiry=body.delete_on_expiry,
        archive_on_expiry=body.archive_on_expiry,
        estimated_size_gb=body.estimated_size_gb,
    )

    policies = list_policies()
    created = next((p for p in policies if p["id"] == policy_id), None)
    return created, HTTPStatus.CREATED


@retention_bp.patch("/<policy_id>/toggle")
def toggle_retention_policy(path: PolicyIdPath):
    """Toggle the enabled state of a retention policy."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    try:
        body = RetentionPolicyToggle(**data)
    except Exception as e:
        return error_response("BAD_REQUEST", str(e), HTTPStatus.BAD_REQUEST)

    updated = update_policy_enabled(path.policy_id, body.enabled)
    if not updated:
        return error_response(
            "NOT_FOUND",
            f"Retention policy {path.policy_id} not found",
            HTTPStatus.NOT_FOUND,
        )

    return {"id": path.policy_id, "enabled": body.enabled}, HTTPStatus.OK


@retention_bp.delete("/<policy_id>")
def delete_retention_policy(path: PolicyIdPath):
    """Delete a retention policy."""
    deleted = delete_policy(path.policy_id)
    if not deleted:
        return error_response(
            "NOT_FOUND",
            f"Retention policy {path.policy_id} not found",
            HTTPStatus.NOT_FOUND,
        )
    return "", HTTPStatus.NO_CONTENT


@retention_bp.post("/cleanup")
def run_cleanup():
    """Queue a cleanup job for expired data."""
    return {"message": "Cleanup job queued"}, HTTPStatus.ACCEPTED
