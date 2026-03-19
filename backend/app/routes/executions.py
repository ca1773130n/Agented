"""Execution log API endpoints with SSE streaming."""

from http import HTTPStatus
from typing import List, Optional

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..database import get_trigger
from ..db.executions import count_filtered_executions, get_filtered_executions
from ..models.common import ExecutionFilterQuery
from ..services.execution_log_service import ExecutionLogService
from ..services.execution_queue_service import ExecutionQueueService

tag = Tag(name="executions", description="Execution log operations")
executions_bp = APIBlueprint("executions", __name__, url_prefix="/admin", abp_tags=[tag])


class TriggerPath(BaseModel):
    trigger_id: str = Field(..., description="Trigger ID")


class ExecutionPath(BaseModel):
    execution_id: str = Field(..., description="Execution ID")


@executions_bp.get("/triggers/<trigger_id>/executions")
def list_trigger_executions(path: TriggerPath, query: ExecutionFilterQuery):
    """List execution history for a trigger with optional filters."""
    trigger = get_trigger(path.trigger_id)
    if not trigger:
        return error_response("NOT_FOUND", "Trigger not found", HTTPStatus.NOT_FOUND)

    limit = min(query.limit or 50, 500)
    offset = query.offset or 0

    executions = get_filtered_executions(
        limit=limit,
        offset=offset,
        status=query.status,
        trigger_id=path.trigger_id,
        date_from=query.date_from,
        date_to=query.date_to,
        q=query.q,
    )
    total_count = count_filtered_executions(
        status=query.status,
        trigger_id=path.trigger_id,
        date_from=query.date_from,
        date_to=query.date_to,
        q=query.q,
    )

    # Get currently running execution if any
    running = ExecutionLogService.get_running_for_trigger(path.trigger_id)

    return {
        "executions": executions,
        "running_execution": running,
        "total": len(executions),
        "total_count": total_count,
    }, HTTPStatus.OK


@executions_bp.get("/executions")
def list_all_executions(query: ExecutionFilterQuery):
    """List all execution history across all triggers with optional filters."""
    limit = min(query.limit or 100, 500)
    offset = query.offset or 0

    executions = get_filtered_executions(
        limit=limit,
        offset=offset,
        status=query.status,
        trigger_id=query.trigger_id,
        date_from=query.date_from,
        date_to=query.date_to,
        q=query.q,
    )
    total_count = count_filtered_executions(
        status=query.status,
        trigger_id=query.trigger_id,
        date_from=query.date_from,
        date_to=query.date_to,
        q=query.q,
    )

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
        return error_response("NOT_FOUND", "Execution not found", HTTPStatus.NOT_FOUND)

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


@executions_bp.get("/executions/<execution_id>/diff")
def get_execution_diff(path: ExecutionPath):
    """Parse stdout_log for unified diff blocks and return structured file diffs."""
    import re

    execution = ExecutionLogService.get_execution(path.execution_id)
    if not execution:
        return error_response("NOT_FOUND", "Execution not found", HTTPStatus.NOT_FOUND)

    stdout_log = execution.get("stdout_log") or ""

    diffs = []
    try:
        import unidiff

        patch_set = unidiff.PatchSet(stdout_log)
        for patched_file in patch_set:
            file_path = patched_file.path
            additions = patched_file.added
            deletions = patched_file.removed

            if patched_file.is_added_file:
                status = "added"
            elif patched_file.is_removed_file:
                status = "deleted"
            else:
                status = "modified"

            chunks = []
            for hunk in patched_file:
                lines = []
                old_no = hunk.source_start
                new_no = hunk.target_start
                for hunk_line in hunk:
                    if hunk_line.is_context:
                        lines.append(
                            {
                                "type": "context",
                                "content": hunk_line.value.rstrip("\n"),
                                "oldLineNo": old_no,
                                "newLineNo": new_no,
                            }
                        )
                        old_no += 1
                        new_no += 1
                    elif hunk_line.is_added:
                        lines.append(
                            {
                                "type": "added",
                                "content": hunk_line.value.rstrip("\n"),
                                "oldLineNo": None,
                                "newLineNo": new_no,
                            }
                        )
                        new_no += 1
                    elif hunk_line.is_removed:
                        lines.append(
                            {
                                "type": "removed",
                                "content": hunk_line.value.rstrip("\n"),
                                "oldLineNo": old_no,
                                "newLineNo": None,
                            }
                        )
                        old_no += 1
                chunks.append(
                    {
                        "header": str(hunk.section_header).strip()
                        or f"@@ -{hunk.source_start},{hunk.source_length} +{hunk.target_start},{hunk.target_length} @@",
                        "lines": lines,
                    }
                )

            diffs.append(
                {
                    "path": file_path,
                    "status": status,
                    "additions": additions,
                    "deletions": deletions,
                    "chunks": chunks,
                }
            )
    except Exception:
        # Fallback: simple regex parsing
        diff_header_re = re.compile(r"^diff --git a/(.+) b/(.+)$", re.MULTILINE)
        hunk_header_re = re.compile(r"^(@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@[^\n]*)$", re.MULTILINE)

        raw_files = re.split(r"(?=^diff --git )", stdout_log, flags=re.MULTILINE)
        for raw_file in raw_files:
            if not raw_file.strip():
                continue
            m = diff_header_re.match(raw_file)
            if not m:
                continue
            file_path = m.group(2)

            is_new = bool(re.search(r"^new file mode", raw_file, re.MULTILINE))
            is_del = bool(re.search(r"^deleted file mode", raw_file, re.MULTILINE))
            status = "added" if is_new else "deleted" if is_del else "modified"

            additions = len(re.findall(r"^\+(?!\+\+)", raw_file, re.MULTILINE))
            deletions = len(re.findall(r"^-(?!--)", raw_file, re.MULTILINE))

            chunks = []
            hunk_parts = hunk_header_re.split(raw_file)
            # hunk_parts[0] is before first hunk; then alternating header, body
            i = 1
            while i < len(hunk_parts) - 1:
                header = hunk_parts[i]
                body = hunk_parts[i + 1]
                i += 2
                lines = []
                old_match = re.search(r"-(\d+)", header)
                new_match = re.search(r"\+(\d+)", header)
                old_no = int(old_match.group(1)) if old_match else 1
                new_no = int(new_match.group(1)) if new_match else 1
                for raw_line in body.splitlines():
                    if raw_line.startswith("+"):
                        lines.append(
                            {
                                "type": "added",
                                "content": raw_line,
                                "oldLineNo": None,
                                "newLineNo": new_no,
                            }
                        )
                        new_no += 1
                    elif raw_line.startswith("-"):
                        lines.append(
                            {
                                "type": "removed",
                                "content": raw_line,
                                "oldLineNo": old_no,
                                "newLineNo": None,
                            }
                        )
                        old_no += 1
                    elif raw_line.startswith(" "):
                        lines.append(
                            {
                                "type": "context",
                                "content": raw_line,
                                "oldLineNo": old_no,
                                "newLineNo": new_no,
                            }
                        )
                        old_no += 1
                        new_no += 1
                chunks.append({"header": header, "lines": lines})

            diffs.append(
                {
                    "path": file_path,
                    "status": status,
                    "additions": additions,
                    "deletions": deletions,
                    "chunks": chunks,
                }
            )

    return {"diffs": diffs}, HTTPStatus.OK


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
        return error_response("NOT_FOUND", "Execution not found", HTTPStatus.NOT_FOUND)

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
        return error_response("NOT_FOUND", "Execution not found", HTTPStatus.NOT_FOUND)
    if execution["status"] != "running":
        return error_response(
            "CONFLICT",
            f'Can only cancel running executions. Current status is "{execution["status"]}". Wait until execution starts.',
            HTTPStatus.CONFLICT,
        )

    grace = _get_sigterm_grace(execution)
    success = ProcessManager.cancel_graceful(path.execution_id, sigterm_timeout=grace)
    if success:
        return {"message": "Execution cancellation initiated"}, HTTPStatus.OK

    return error_response(
        "INTERNAL_SERVER_ERROR", "Failed to cancel execution", HTTPStatus.INTERNAL_SERVER_ERROR
    )


@executions_bp.post("/executions/<execution_id>/cancel")
def cancel_execution_graceful(path: ExecutionPath):
    """Cancel a running execution gracefully: sends SIGTERM then SIGKILL after configured grace period."""
    from ..services.process_manager import ProcessManager

    execution = ExecutionLogService.get_execution(path.execution_id)
    if not execution:
        return error_response("NOT_FOUND", "Execution not found", HTTPStatus.NOT_FOUND)
    if execution["status"] != "running":
        return error_response(
            "CONFLICT",
            f'Can only cancel running executions. Current status is "{execution["status"]}". Wait until execution starts.',
            HTTPStatus.CONFLICT,
        )

    grace = _get_sigterm_grace(execution)
    success = ProcessManager.cancel_graceful(path.execution_id, sigterm_timeout=grace)
    if success:
        return {"message": "Cancellation signal sent"}, HTTPStatus.OK

    return error_response(
        "INTERNAL_SERVER_ERROR", "Failed to cancel execution", HTTPStatus.INTERNAL_SERVER_ERROR
    )


@executions_bp.get("/triggers/<trigger_id>/executions/running")
def get_running_trigger_execution(path: TriggerPath):
    """Get the currently running execution for a trigger, if any."""
    trigger = get_trigger(path.trigger_id)
    if not trigger:
        return error_response("NOT_FOUND", "Trigger not found", HTTPStatus.NOT_FOUND)

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
        return error_response("NOT_FOUND", "Execution not found", HTTPStatus.NOT_FOUND)
    if execution["status"] != "running":
        return error_response(
            "CONFLICT",
            f'Can only pause running executions. Current status is "{execution["status"]}".',
            HTTPStatus.CONFLICT,
        )

    success = ProcessManager.pause(path.execution_id)
    if success:
        return {"status": "paused", "execution_id": path.execution_id}, HTTPStatus.OK

    return error_response(
        "INTERNAL_SERVER_ERROR", "Failed to pause execution", HTTPStatus.INTERNAL_SERVER_ERROR
    )


@executions_bp.post("/executions/<execution_id>/resume")
def resume_execution(path: ExecutionPath):
    """Resume a paused execution via SIGCONT."""
    from ..services.process_manager import ProcessManager

    execution = ExecutionLogService.get_execution(path.execution_id)
    if not execution:
        return error_response("NOT_FOUND", "Execution not found", HTTPStatus.NOT_FOUND)
    if execution["status"] != "paused":
        return error_response(
            "CONFLICT",
            f'Can only resume paused executions. Current status is "{execution["status"]}".',
            HTTPStatus.CONFLICT,
        )

    success = ProcessManager.resume(path.execution_id)
    if success:
        return {"status": "running", "execution_id": path.execution_id}, HTTPStatus.OK

    return error_response(
        "INTERNAL_SERVER_ERROR", "Failed to resume execution", HTTPStatus.INTERNAL_SERVER_ERROR
    )


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
        matching = get_execution_logs_filtered(status=body.status, trigger_id=body.trigger_id)
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
            results.append(
                {
                    "execution_id": eid,
                    "success": False,
                    "reason": f"status is {current_status}",
                }
            )
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
        result.append(
            {
                "trigger_id": row["trigger_id"],
                "cooldown_seconds": row.get("cooldown_seconds", 0),
                "retry_at": row.get("retry_at", ""),
                "trigger_type": row.get("trigger_type", "webhook"),
                "created_at": row.get("created_at", ""),
            }
        )

    return {
        "retries": result,
        "total": len(result),
    }, HTTPStatus.OK


# --- Anomaly Detection Stubs ---


@executions_bp.get("/executions/anomalies")
def get_execution_anomalies():
    """Stub: execution anomaly detection data."""
    return {"anomalies": [], "baselines": []}, HTTPStatus.OK


class AnomalyPath(BaseModel):
    anomaly_id: str = Field(..., description="Anomaly ID")


@executions_bp.post("/executions/anomalies/<anomaly_id>/acknowledge")
def acknowledge_anomaly(path: AnomalyPath):
    """Stub: acknowledge an execution anomaly."""
    return {"ok": True}, HTTPStatus.OK


# --- Quota Control Stubs ---


@executions_bp.get("/executions/quotas")
def get_execution_quotas():
    """Stub: execution quota rules."""
    return {"rules": []}, HTTPStatus.OK


@executions_bp.post("/executions/quotas")
def create_execution_quota():
    """Stub: create a new execution quota rule."""
    return {"id": "q-stub", "message": "created"}, HTTPStatus.OK


class QuotaPath(BaseModel):
    quota_id: str = Field(..., description="Quota rule ID")


@executions_bp.put("/executions/quotas/<quota_id>")
def update_execution_quota(path: QuotaPath):
    """Stub: update an execution quota rule."""
    return {"ok": True}, HTTPStatus.OK


@executions_bp.delete("/executions/quotas/<quota_id>")
def delete_execution_quota(path: QuotaPath):
    """Stub: delete an execution quota rule."""
    return {"ok": True}, HTTPStatus.OK
