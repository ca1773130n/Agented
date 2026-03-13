"""Findings triage API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag

from app.models.common import error_response

from ..db.findings import create_finding, delete_finding, get_finding, list_findings, update_finding
from ..models.finding import FindingCreate, FindingPath, FindingUpdate

tag = Tag(name="Findings", description="Findings triage board CRUD")
findings_bp = APIBlueprint("findings", __name__, url_prefix="/api", abp_tags=[tag])


@findings_bp.get("/findings")
def list_findings_route():
    """List findings with optional filtering by status, bot_id, or owner."""
    status = request.args.get("status")
    bot_id = request.args.get("bot_id")
    owner = request.args.get("owner")

    items = list_findings(status=status, bot_id=bot_id, owner=owner)
    return {"findings": items}, HTTPStatus.OK


@findings_bp.post("/findings")
def create_finding_route(body: FindingCreate):
    """Create a new finding."""
    finding_id = create_finding(body.model_dump())
    finding = get_finding(finding_id)
    if not finding:
        return error_response(
            "INTERNAL_SERVER_ERROR", "Failed to create finding", HTTPStatus.INTERNAL_SERVER_ERROR
        )
    return finding, HTTPStatus.CREATED


@findings_bp.patch("/findings/<finding_id>")
def update_finding_route(path: FindingPath, body: FindingUpdate):
    """Partially update a finding's status or owner."""
    existing = get_finding(path.finding_id)
    if not existing:
        return error_response("NOT_FOUND", "Finding not found", HTTPStatus.NOT_FOUND)

    updated = update_finding(path.finding_id, body.model_dump(exclude_unset=True))
    if not updated:
        return error_response("BAD_REQUEST", "No changes applied", HTTPStatus.BAD_REQUEST)

    finding = get_finding(path.finding_id)
    return finding, HTTPStatus.OK


@findings_bp.delete("/findings/<finding_id>")
def delete_finding_route(path: FindingPath):
    """Delete a finding by ID."""
    deleted = delete_finding(path.finding_id)
    if not deleted:
        return error_response("NOT_FOUND", "Finding not found", HTTPStatus.NOT_FOUND)
    return "", HTTPStatus.NO_CONTENT
