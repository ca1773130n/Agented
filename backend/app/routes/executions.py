"""Execution log API endpoints with SSE streaming."""

from http import HTTPStatus

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import get_trigger
from ..services.execution_log_service import ExecutionLogService

tag = Tag(name="executions", description="Execution log operations")
executions_bp = APIBlueprint("executions", __name__, url_prefix="/admin", abp_tags=[tag])


class TriggerPath(BaseModel):
    trigger_id: str = Field(..., description="Trigger ID")


class ExecutionPath(BaseModel):
    execution_id: str = Field(..., description="Execution ID")


@executions_bp.get("/triggers/<trigger_id>/executions")
def list_trigger_executions(path: TriggerPath):
    """List execution history for a trigger."""
    trigger = get_trigger(path.trigger_id)
    if not trigger:
        return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

    limit = min(request.args.get("limit", 50, type=int), 500)  # Max 500
    offset = max(request.args.get("offset", 0, type=int), 0)  # Min 0
    status = request.args.get("status", None)

    executions = ExecutionLogService.get_history(
        trigger_id=path.trigger_id, limit=limit, offset=offset, status=status
    )

    # Get currently running execution if any
    running = ExecutionLogService.get_running_for_trigger(path.trigger_id)

    return {
        "executions": executions,
        "running_execution": running,
        "total": len(executions),
    }, HTTPStatus.OK


@executions_bp.get("/executions")
def list_all_executions():
    """List all execution history across all triggers."""
    limit = min(request.args.get("limit", 100, type=int), 500)  # Max 500
    offset = max(request.args.get("offset", 0, type=int), 0)  # Min 0

    executions = ExecutionLogService.get_history(limit=limit, offset=offset)

    return {"executions": executions, "total": len(executions)}, HTTPStatus.OK


@executions_bp.get("/executions/<execution_id>")
def get_execution(path: ExecutionPath):
    """Get a single execution with full logs."""
    execution = ExecutionLogService.get_execution(path.execution_id)
    if not execution:
        return {"error": "Execution not found"}, HTTPStatus.NOT_FOUND

    return execution, HTTPStatus.OK


@executions_bp.get("/executions/<execution_id>/stream")
def stream_execution(path: ExecutionPath):
    """SSE endpoint for real-time log streaming.

    Returns Server-Sent Events with the following event types:
    - log: A log line (stdout or stderr)
    - status: Execution status update
    - complete: Execution finished
    """
    execution = ExecutionLogService.get_execution(path.execution_id)
    if not execution:
        return {"error": "Execution not found"}, HTTPStatus.NOT_FOUND

    def generate():
        for event in ExecutionLogService.subscribe(path.execution_id):
            yield event

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@executions_bp.delete("/executions/<execution_id>")
def cancel_execution(path: ExecutionPath):
    """Cancel a running execution by killing its process group."""
    from ..services.process_manager import ProcessManager

    execution = ExecutionLogService.get_execution(path.execution_id)
    if not execution:
        return {"error": "Execution not found"}, HTTPStatus.NOT_FOUND
    if execution["status"] != "running":
        return {
            "error": f"Execution is not running (status: {execution['status']})"
        }, HTTPStatus.CONFLICT

    success = ProcessManager.cancel(path.execution_id)
    if success:
        return {"message": "Execution cancellation initiated"}, HTTPStatus.OK

    return {"error": "Failed to cancel execution"}, HTTPStatus.INTERNAL_SERVER_ERROR


@executions_bp.get("/triggers/<trigger_id>/executions/running")
def get_running_trigger_execution(path: TriggerPath):
    """Get the currently running execution for a trigger, if any."""
    trigger = get_trigger(path.trigger_id)
    if not trigger:
        return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

    running = ExecutionLogService.get_running_for_trigger(path.trigger_id)
    if not running:
        return {"running": False}, HTTPStatus.OK

    return {"running": True, "execution": running}, HTTPStatus.OK
