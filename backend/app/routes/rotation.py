"""Rotation dashboard API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag

from ..models.common import PaginationQuery

tag = Tag(name="rotation", description="Rotation dashboard endpoints")
rotation_bp = APIBlueprint("rotation", __name__, url_prefix="/admin/rotation", abp_tags=[tag])


@rotation_bp.get("/status")
def get_rotation_status():
    """Get current rotation status: active sessions and evaluator state."""
    from ..services.execution_log_service import ExecutionLogService
    from ..services.process_manager import ProcessManager
    from ..services.rotation_evaluator import RotationEvaluator

    # Build sessions list from active executions
    active_ids = ProcessManager.get_active_executions()
    sessions = []
    for eid in active_ids:
        execution = ExecutionLogService.get_execution(eid)
        if execution:
            sessions.append(
                {
                    "execution_id": eid,
                    "account_id": execution.get("account_id"),
                    "trigger_id": execution.get("trigger_id"),
                    "backend_type": execution.get("backend_type"),
                    "started_at": execution.get("started_at"),
                }
            )

    # Get evaluator status
    evaluator = RotationEvaluator.get_evaluator_status()

    return {"sessions": sessions, "evaluator": evaluator}, HTTPStatus.OK


@rotation_bp.get("/history")
def get_rotation_history(query: PaginationQuery):
    """Get rotation event history with enriched account names.

    Query params:
        execution_id (optional): Filter by execution ID
        limit (optional): Max events to return, default 50
        offset (optional): Number of events to skip, default 0
    """
    from ..db.rotations import (
        count_rotation_events,
        get_rotation_events_enriched,
        get_rotation_events_enriched_by_execution,
    )

    execution_id = request.args.get("execution_id")
    limit = query.limit or 50
    offset = query.offset or 0

    if execution_id:
        events = get_rotation_events_enriched_by_execution(execution_id)
        total_count = len(events)
    else:
        events = get_rotation_events_enriched(limit, offset=offset)
        total_count = count_rotation_events()

    return {"events": events, "total_count": total_count}, HTTPStatus.OK
