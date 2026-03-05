"""Execution log API endpoints with SSE streaming."""

from http import HTTPStatus
from typing import List, Optional

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import get_trigger
from ..services.execution_log_service import ExecutionLogService
from ..services.execution_queue_service import ExecutionQueueService

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

    SSE Protocol:
    - Event 'log': {"line": str, "stream": "stdout"|"stderr", "timestamp": str}
    - Event 'status': {"status": "running"|"completed"|"failed"|"cancelled"}
    - Event 'complete': {"exit_code": int, "duration_seconds": float}

    Supports Last-Event-ID for reconnection replay (up to 500 buffered lines).
    """
    execution = ExecutionLogService.get_execution(path.execution_id)
    if not execution:
        return {"error": "Execution not found"}, HTTPStatus.NOT_FOUND

    def generate():
        """Yield SSE events from the execution log subscription."""
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


# --- Pause / Resume / Bulk Cancel ---


class BulkCancelRequest(BaseModel):
    """Request body for bulk cancellation of executions."""

    trigger_id: Optional[str] = Field(None, description="Cancel executions for this trigger")
    status: str = Field("running", description="Status filter (default: running)")
    execution_ids: List[str] = Field(
        default_factory=list, description="Specific execution IDs to cancel"
    )


@executions_bp.post("/executions/<execution_id>/pause")
def pause_execution(path: ExecutionPath):
    """Pause a running execution via SIGSTOP."""
    from ..services.process_manager import ProcessManager

    execution = ExecutionLogService.get_execution(path.execution_id)
    if not execution:
        return {"error": "Execution not found"}, HTTPStatus.NOT_FOUND
    if execution["status"] != "running":
        return {
            "error": f'Can only pause running executions. Current status is "{execution["status"]}".'
        }, HTTPStatus.CONFLICT

    success = ProcessManager.pause(path.execution_id)
    if success:
        return {"status": "paused", "execution_id": path.execution_id}, HTTPStatus.OK

    return {"error": "Failed to pause execution"}, HTTPStatus.INTERNAL_SERVER_ERROR


@executions_bp.post("/executions/<execution_id>/resume")
def resume_execution(path: ExecutionPath):
    """Resume a paused execution via SIGCONT."""
    from ..services.process_manager import ProcessManager

    execution = ExecutionLogService.get_execution(path.execution_id)
    if not execution:
        return {"error": "Execution not found"}, HTTPStatus.NOT_FOUND
    if execution["status"] != "paused":
        return {
            "error": f'Can only resume paused executions. Current status is "{execution["status"]}".'
        }, HTTPStatus.CONFLICT

    success = ProcessManager.resume(path.execution_id)
    if success:
        return {"status": "running", "execution_id": path.execution_id}, HTTPStatus.OK

    return {"error": "Failed to resume execution"}, HTTPStatus.INTERNAL_SERVER_ERROR


@executions_bp.post("/executions/bulk-cancel")
def bulk_cancel_executions(body: BulkCancelRequest):
    """Bulk cancel multiple executions by filter or explicit IDs."""
    from ..database import get_execution_logs_filtered
    from ..services.process_manager import ProcessManager

    results = []
    cancelled = 0
    failed = 0

    if body.execution_ids:
        # Cancel by explicit IDs
        target_ids = body.execution_ids
    else:
        # Query by filters
        matching = get_execution_logs_filtered(
            status=body.status, trigger_id=body.trigger_id
        )
        target_ids = [ex["execution_id"] for ex in matching]

    for eid in target_ids:
        execution = ExecutionLogService.get_execution(eid)
        if not execution:
            results.append({"execution_id": eid, "success": False, "reason": "not found"})
            failed += 1
            continue

        current_status = execution["status"]
        if current_status == "paused":
            # Must resume before cancel: SIGCONT then cancel_graceful
            success = ProcessManager.resume(eid)
            if success:
                success = ProcessManager.cancel_graceful(eid)
            else:
                # Process might not be tracked; try direct cancel
                success = ProcessManager.cancel_graceful(eid)
        elif current_status == "running":
            success = ProcessManager.cancel_graceful(eid)
        else:
            results.append({
                "execution_id": eid,
                "success": False,
                "reason": f"status is {current_status}",
            })
            failed += 1
            continue

        if success:
            results.append({"execution_id": eid, "success": True})
            cancelled += 1
        else:
            results.append({"execution_id": eid, "success": False, "reason": "cancel failed"})
            failed += 1

    return {
        "cancelled": cancelled,
        "failed": failed,
        "details": results,
    }, HTTPStatus.OK


# --- Execution Queue API ---


@executions_bp.get("/executions/queue")
def get_queue_status():
    """Get execution queue summary with per-trigger pending/dispatching counts."""
    from ..db.execution_queue import get_queue_depth

    summary = ExecutionQueueService.get_queue_summary()
    total_pending = get_queue_depth()

    return {
        "queue": summary,
        "total_pending": total_pending,
    }, HTTPStatus.OK


class QueueTriggerPath(BaseModel):
    trigger_id: str = Field(..., description="Trigger ID")


@executions_bp.get("/executions/queue/<trigger_id>")
def get_queue_for_trigger(path: QueueTriggerPath):
    """Get queue depth for a specific trigger."""
    from ..db.execution_queue import get_queue_depth

    depth = get_queue_depth(path.trigger_id)
    return {
        "trigger_id": path.trigger_id,
        "pending": depth,
    }, HTTPStatus.OK


@executions_bp.delete("/executions/queue/<trigger_id>")
def cancel_queue_for_trigger(path: QueueTriggerPath):
    """Cancel all pending queue entries for a specific trigger."""
    from ..db.execution_queue import cancel_pending_entries

    cancelled = cancel_pending_entries(path.trigger_id)
    return {"cancelled": cancelled}, HTTPStatus.OK


# --- Pending Retries API ---


@executions_bp.get("/executions/retries")
def get_pending_retries():
    """Get pending rate-limit retries from the pending_retries table."""
    from ..db.monitoring import get_all_pending_retries

    retries = get_all_pending_retries()
    result = []
    for row in retries:
        result.append({
            "trigger_id": row["trigger_id"],
            "cooldown_seconds": row.get("cooldown_seconds", 0),
            "retry_at": row.get("retry_at", ""),
            "trigger_type": row.get("trigger_type", "webhook"),
            "created_at": row.get("created_at", ""),
        })

    return {
        "retries": result,
        "total": len(result),
    }, HTTPStatus.OK
