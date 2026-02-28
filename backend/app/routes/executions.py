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
    total_count = ExecutionLogService.count_history(trigger_id=path.trigger_id, status=status)

    # Get currently running execution if any
    running = ExecutionLogService.get_running_for_trigger(path.trigger_id)

    return {
        "executions": executions,
        "running_execution": running,
        "total": len(executions),
        "total_count": total_count,
    }, HTTPStatus.OK


@executions_bp.get("/executions")
def list_all_executions():
    """List all execution history across all triggers."""
    limit = min(request.args.get("limit", 100, type=int), 500)  # Max 500
    offset = max(request.args.get("offset", 0, type=int), 0)  # Min 0

    executions = ExecutionLogService.get_history(limit=limit, offset=offset)
    total_count = ExecutionLogService.count_history()

    return {
        "executions": executions,
        "total": len(executions),
        "total_count": total_count,
    }, HTTPStatus.OK


@executions_bp.get("/executions/<execution_id>")
def get_execution(path: ExecutionPath):
    """Get a single execution with full logs.

    Query params:
    - ``q``: optional search string. When provided, only log lines containing
      ``q`` (case-insensitive) are returned. Adds ``log_search_query`` and
      ``log_match_count`` fields to the response.
    """
    execution = ExecutionLogService.get_execution(path.execution_id)
    if not execution:
        return {"error": "Execution not found"}, HTTPStatus.NOT_FOUND

    q = request.args.get("q", "").strip()
    if q:
        execution = dict(execution)  # shallow copy — avoid mutating the cached dict
        q_lower = q.lower()
        for field in ("stdout_log", "stderr_log"):
            raw = execution.get(field) or ""
            matched_lines = [line for line in raw.splitlines() if q_lower in line.lower()]
            execution[field] = "\n".join(matched_lines)
        execution["log_search_query"] = q
        execution["log_match_count"] = sum(
            len((execution.get(f) or "").splitlines()) for f in ("stdout_log", "stderr_log")
        )

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


def _get_sigterm_grace(execution: dict, default: float = 10.0) -> float:
    """Return the SIGTERM grace period for an execution's trigger (seconds)."""
    trigger = get_trigger(execution.get("trigger_id", ""))
    if trigger and trigger.get("sigterm_grace_seconds"):
        return float(trigger["sigterm_grace_seconds"])
    return default


@executions_bp.delete("/executions/<execution_id>")
def cancel_execution(path: ExecutionPath):
    """Cancel a running execution gracefully (SIGTERM, then SIGKILL after configured grace period)."""
    from ..services.process_manager import ProcessManager

    execution = ExecutionLogService.get_execution(path.execution_id)
    if not execution:
        return {"error": "Execution not found"}, HTTPStatus.NOT_FOUND
    if execution["status"] != "running":
        return {
            "error": f'Can only cancel running executions. Current status is "{execution["status"]}". Wait until execution starts.'
        }, HTTPStatus.CONFLICT

    grace = _get_sigterm_grace(execution)
    success = ProcessManager.cancel_graceful(path.execution_id, sigterm_timeout=grace)
    if success:
        return {"message": "Execution cancellation initiated"}, HTTPStatus.OK

    return {"error": "Failed to cancel execution"}, HTTPStatus.INTERNAL_SERVER_ERROR


@executions_bp.post("/executions/<execution_id>/cancel")
def cancel_execution_graceful(path: ExecutionPath):
    """Cancel a running execution gracefully: sends SIGTERM then SIGKILL after configured grace period."""
    from ..services.process_manager import ProcessManager

    execution = ExecutionLogService.get_execution(path.execution_id)
    if not execution:
        return {"error": "Execution not found"}, HTTPStatus.NOT_FOUND
    if execution["status"] != "running":
        return {
            "error": f'Can only cancel running executions. Current status is "{execution["status"]}". Wait until execution starts.'
        }, HTTPStatus.CONFLICT

    grace = _get_sigterm_grace(execution)
    success = ProcessManager.cancel_graceful(path.execution_id, sigterm_timeout=grace)
    if success:
        return {"message": "Cancellation signal sent"}, HTTPStatus.OK

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
