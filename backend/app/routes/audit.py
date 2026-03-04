"""Audit history API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..services.audit_log_service import AuditLogService
from ..services.audit_service import AuditService

tag = Tag(name="audit", description="Security audit operations")
audit_bp = APIBlueprint("audit", __name__, url_prefix="/api/audit", abp_tags=[tag])


class AuditIdPath(BaseModel):
    audit_id: str = Field(..., description="Audit ID")


class AuditWeekPath(BaseModel):
    audit_week: str = Field(..., description="Audit week identifier")


@audit_bp.get("/history")
def get_audit_history():
    """Get audit history with optional filters."""
    limit = request.args.get("limit", type=int)
    project_path = request.args.get("project_path", "")
    trigger_id = request.args.get("trigger_id", "")
    result, status = AuditService.get_history(
        limit=limit, project_path=project_path, trigger_id=trigger_id
    )
    return result, status


@audit_bp.get("/stats")
def get_audit_stats():
    """Get aggregate audit statistics."""
    project_path = request.args.get("project_path", "")
    trigger_id = request.args.get("trigger_id", "")
    result, status = AuditService.get_stats(project_path=project_path, trigger_id=trigger_id)
    return result, status


@audit_bp.get("/projects")
def get_audit_projects():
    """Get list of all unique project paths with audit info."""
    result, status = AuditService.get_projects()
    return result, status


@audit_bp.get("/<audit_id>")
def get_audit_detail(path: AuditIdPath):
    """Get detailed audit report by audit_id."""
    result, status = AuditService.get_detail(path.audit_id)
    return result, status


@audit_bp.post("/")
def add_audit():
    """Add a new audit result."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    result, status = AuditService.add_audit(data)
    return result, status


@audit_bp.get("/reports/<audit_week>")
def get_weekly_report(path: AuditWeekPath):
    """Get detailed report for a specific audit week."""
    result, status = AuditService.get_weekly_report(path.audit_week)
    return result, status


@audit_bp.get("/events")
def get_audit_events():
    """Return recent structured audit log events (in-memory, newest first).

    These events are emitted by AuditLogService.log() and reflect execution
    starts/completions, trigger/workflow updates, and other platform operations.
    """
    limit = min(request.args.get("limit", 100, type=int), 500)
    events = AuditLogService.get_recent_events(limit=limit)
    return {"events": events, "total": len(events)}, HTTPStatus.OK


@audit_bp.get("/events/persistent")
def get_persistent_audit_events():
    """Query persistent audit events from SQLite with optional filters.

    Query parameters:
    - entity_type: Filter by entity type (e.g. "trigger", "team")
    - entity_id: Filter by entity ID
    - actor: Filter by actor
    - start_date: ISO date for range start (inclusive)
    - end_date: ISO date for range end (inclusive)
    - limit: Max events (default 100, max 1000)
    - offset: Pagination offset (default 0)
    """
    from ..db.audit_events import count_audit_events, query_audit_events

    entity_type = request.args.get("entity_type")
    entity_id = request.args.get("entity_id")
    actor = request.args.get("actor")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    limit = min(request.args.get("limit", 100, type=int), 1000)
    offset = max(request.args.get("offset", 0, type=int), 0)

    events = query_audit_events(
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    total = count_audit_events(
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        start_date=start_date,
        end_date=end_date,
    )
    return {"events": events, "total": total}, HTTPStatus.OK
