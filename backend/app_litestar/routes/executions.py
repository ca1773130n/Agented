"""Wave 75 — execution log routes (~20 routes).

Everything except /admin/executions/{id}/stream (SSE — deferred to the
streaming wave) plus the queue, retries, anomaly stubs, and quota stubs.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)

from app.database import get_trigger
from app.db.executions import count_filtered_executions, get_filtered_executions
from app.services.execution_log_service import ExecutionLogService
from app.services.execution_queue_service import ExecutionQueueService


def _ensure_running(execution: dict, action: str) -> None:
    if execution["status"] != "running":
        raise HTTPException(
            status_code=409,
            detail=(
                f'Can only {action} running executions. Current status is "{execution["status"]}".'
            ),
        )


def _get_sigterm_grace(execution: dict, default: float = 10.0) -> float:
    trigger = get_trigger(execution.get("trigger_id", ""))
    if trigger and trigger.get("sigterm_grace_seconds"):
        return float(trigger["sigterm_grace_seconds"])
    return default


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------


@get("/triggers/{trigger_id:str}/executions", sync_to_thread=False)
def list_trigger_executions(
    trigger_id: str,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
) -> dict[str, Any]:
    if not get_trigger(trigger_id):
        raise NotFoundException(detail="Trigger not found")
    capped_limit = min(limit, 500)
    executions = get_filtered_executions(
        limit=capped_limit,
        offset=offset,
        status=status,
        trigger_id=trigger_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )
    total_count = count_filtered_executions(
        status=status,
        trigger_id=trigger_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )
    running = ExecutionLogService.get_running_for_trigger(trigger_id)
    return {
        "executions": executions,
        "running_execution": running,
        "total": len(executions),
        "total_count": total_count,
    }


@get("/executions", sync_to_thread=False)
def list_all_executions(
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
    trigger_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
) -> dict[str, Any]:
    capped_limit = min(limit, 500)
    executions = get_filtered_executions(
        limit=capped_limit,
        offset=offset,
        status=status,
        trigger_id=trigger_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )
    total_count = count_filtered_executions(
        status=status,
        trigger_id=trigger_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )
    return {
        "executions": executions,
        "total": len(executions),
        "total_count": total_count,
    }


@get("/executions/{execution_id:str}", sync_to_thread=False)
def get_execution(execution_id: str, q: Optional[str] = None) -> Any:
    execution = ExecutionLogService.get_execution(execution_id)
    if not execution:
        raise NotFoundException(detail="Execution not found")
    needle = (q or "").strip()
    if needle:
        execution = dict(execution)
        q_lower = needle.lower()
        for field in ("stdout_log", "stderr_log"):
            raw = execution.get(field) or ""
            matched_lines = [line for line in raw.splitlines() if q_lower in line.lower()]
            execution[field] = "\n".join(matched_lines)
        execution["log_search_query"] = needle
        execution["log_match_count"] = sum(
            len((execution.get(f) or "").splitlines()) for f in ("stdout_log", "stderr_log")
        )
    return execution


@get("/executions/{execution_id:str}/diff", sync_to_thread=False)
def get_execution_diff(execution_id: str) -> dict[str, Any]:
    execution = ExecutionLogService.get_execution(execution_id)
    if not execution:
        raise NotFoundException(detail="Execution not found")
    stdout_log = execution.get("stdout_log") or ""
    diffs: list[dict[str, Any]] = []
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
                lines: list[dict[str, Any]] = []
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
                        or (
                            f"@@ -{hunk.source_start},{hunk.source_length}"
                            f" +{hunk.target_start},{hunk.target_length} @@"
                        ),
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
    return {"diffs": diffs}


# ---------------------------------------------------------------------------
# Cancel / pause / resume
# ---------------------------------------------------------------------------


@delete("/executions/{execution_id:str}", status_code=200, sync_to_thread=False)
def cancel_execution(execution_id: str) -> dict[str, Any]:
    from app.services.process_manager import ProcessManager

    execution = ExecutionLogService.get_execution(execution_id)
    if not execution:
        raise NotFoundException(detail="Execution not found")
    _ensure_running(execution, "cancel")
    if not ProcessManager.cancel_graceful(
        execution_id, sigterm_timeout=_get_sigterm_grace(execution)
    ):
        raise HTTPException(status_code=500, detail="Failed to cancel execution")
    return {"message": "Execution cancellation initiated"}


@post("/executions/{execution_id:str}/cancel", sync_to_thread=False)
def cancel_execution_graceful(execution_id: str) -> dict[str, Any]:
    from app.services.process_manager import ProcessManager

    execution = ExecutionLogService.get_execution(execution_id)
    if not execution:
        raise NotFoundException(detail="Execution not found")
    _ensure_running(execution, "cancel")
    if not ProcessManager.cancel_graceful(
        execution_id, sigterm_timeout=_get_sigterm_grace(execution)
    ):
        raise HTTPException(status_code=500, detail="Failed to cancel execution")
    return {"message": "Cancellation signal sent"}


@get("/triggers/{trigger_id:str}/executions/running", sync_to_thread=False)
def get_running_for_trigger(trigger_id: str) -> dict[str, Any]:
    if not get_trigger(trigger_id):
        raise NotFoundException(detail="Trigger not found")
    running = ExecutionLogService.get_running_for_trigger(trigger_id)
    if not running:
        return {"running": False}
    return {"running": True, "execution": running}


@post("/executions/{execution_id:str}/pause", sync_to_thread=False)
def pause_execution(execution_id: str) -> dict[str, Any]:
    from app.services.process_manager import ProcessManager

    execution = ExecutionLogService.get_execution(execution_id)
    if not execution:
        raise NotFoundException(detail="Execution not found")
    _ensure_running(execution, "pause")
    if not ProcessManager.pause(execution_id):
        raise HTTPException(status_code=500, detail="Failed to pause execution")
    return {"status": "paused", "execution_id": execution_id}


@post("/executions/{execution_id:str}/resume", sync_to_thread=False)
def resume_execution(execution_id: str) -> dict[str, Any]:
    from app.services.process_manager import ProcessManager

    execution = ExecutionLogService.get_execution(execution_id)
    if not execution:
        raise NotFoundException(detail="Execution not found")
    if execution["status"] != "paused":
        raise HTTPException(
            status_code=409,
            detail=(
                f'Can only resume paused executions. Current status is "{execution["status"]}".'
            ),
        )
    if not ProcessManager.resume(execution_id):
        raise HTTPException(status_code=500, detail="Failed to resume execution")
    return {"status": "running", "execution_id": execution_id}


@post("/executions/bulk-cancel", status_code=200, sync_to_thread=False)
def bulk_cancel_executions(data: dict) -> dict[str, Any]:
    from app.database import get_execution_logs_filtered
    from app.services.process_manager import ProcessManager

    body = data or {}
    execution_ids: List[str] = body.get("execution_ids") or []
    target_status = body.get("status", "running")
    trigger_id = body.get("trigger_id")
    if execution_ids:
        target_ids = execution_ids
    else:
        matching = get_execution_logs_filtered(status=target_status, trigger_id=trigger_id)
        target_ids = [ex["execution_id"] for ex in matching]

    results: list[dict[str, Any]] = []
    cancelled = failed = 0
    for eid in target_ids:
        execution = ExecutionLogService.get_execution(eid)
        if not execution:
            results.append({"execution_id": eid, "success": False, "reason": "not found"})
            failed += 1
            continue
        current_status = execution["status"]
        if current_status == "paused":
            success = ProcessManager.resume(eid)
            success = (
                ProcessManager.cancel_graceful(eid)
                if success
                else (ProcessManager.cancel_graceful(eid))
            )
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
    return {"cancelled": cancelled, "failed": failed, "details": results}


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


@get("/executions/queue", sync_to_thread=False)
def queue_status() -> dict[str, Any]:
    from app.db.execution_queue import get_queue_depth

    return {
        "queue": ExecutionQueueService.get_queue_summary(),
        "total_pending": get_queue_depth(),
    }


@get("/executions/queue/{trigger_id:str}", sync_to_thread=False)
def queue_for_trigger(trigger_id: str) -> dict[str, Any]:
    from app.db.execution_queue import get_queue_depth

    return {"trigger_id": trigger_id, "pending": get_queue_depth(trigger_id)}


@delete("/executions/queue/{trigger_id:str}", status_code=200, sync_to_thread=False)
def cancel_queue_for_trigger(trigger_id: str) -> dict[str, Any]:
    from app.db.execution_queue import cancel_pending_entries

    return {"cancelled": cancel_pending_entries(trigger_id)}


# ---------------------------------------------------------------------------
# Retries / anomalies / quotas
# ---------------------------------------------------------------------------


@get("/executions/retries", sync_to_thread=False)
def pending_retries() -> dict[str, Any]:
    from app.db.monitoring import get_all_pending_retries

    retries = get_all_pending_retries()
    result = [
        {
            "trigger_id": row["trigger_id"],
            "cooldown_seconds": row.get("cooldown_seconds", 0),
            "retry_at": row.get("retry_at", ""),
            "trigger_type": row.get("trigger_type", "webhook"),
            "created_at": row.get("created_at", ""),
        }
        for row in retries
    ]
    return {"retries": result, "total": len(result)}


@get("/executions/anomalies", sync_to_thread=False)
def execution_anomalies() -> dict[str, Any]:
    # PR-G: silent-success stub flipped to 501. Anomaly detection is not yet
    # implemented; returning an empty list misled the UI into rendering a
    # "no active anomalies — all executions look normal" green state.
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@post("/executions/anomalies/{anomaly_id:str}/acknowledge", sync_to_thread=False)
def acknowledge_anomaly(anomaly_id: str) -> dict[str, Any]:
    del anomaly_id
    # PR-G: silent-success stub flipped to 501.
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@get("/executions/quotas", sync_to_thread=False)
def execution_quotas() -> dict[str, Any]:
    # Honest empty read kept as-is (PR-G): UI renders an empty-state when the
    # list is empty, which is truthful for an un-shipped feature. Only the
    # mutating quota handlers below return 501.
    return {"rules": []}


@post("/executions/quotas", sync_to_thread=False)
def create_execution_quota(data: dict) -> dict[str, Any]:
    del data
    # PR-G: silent-success stub flipped to 501.
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@put("/executions/quotas/{quota_id:str}", sync_to_thread=False)
def update_execution_quota(quota_id: str, data: dict) -> dict[str, Any]:
    del quota_id, data
    # PR-G: silent-success stub flipped to 501.
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@delete("/executions/quotas/{quota_id:str}", status_code=200, sync_to_thread=False)
def delete_execution_quota(quota_id: str) -> dict[str, Any]:
    del quota_id
    # PR-G: silent-success stub flipped to 501.
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


executions_router = Router(
    path="/admin",
    route_handlers=[
        list_trigger_executions,
        list_all_executions,
        get_execution,
        get_execution_diff,
        cancel_execution,
        cancel_execution_graceful,
        get_running_for_trigger,
        pause_execution,
        resume_execution,
        bulk_cancel_executions,
        queue_status,
        queue_for_trigger,
        cancel_queue_for_trigger,
        pending_retries,
        execution_anomalies,
        acknowledge_anomaly,
        execution_quotas,
        create_execution_quota,
        update_execution_quota,
        delete_execution_quota,
    ],
)
