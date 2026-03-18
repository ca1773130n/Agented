"""System error logging and monitoring API endpoints."""

import os
from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.db.system_errors import (
    count_errors_by_status,
    get_system_error_with_fixes,
    list_system_errors,
    update_system_error_status,
)
from app.models.common import error_response
from app.models.system import (
    LogsQuery,
    ReportErrorRequest,
    SystemErrorListQuery,
    UpdateErrorStatusRequest,
)
from app.services.error_capture import capture_error

tag = Tag(name="system", description="System error logging and monitoring")
system_bp = APIBlueprint("system", __name__, url_prefix="/admin/system", abp_tags=[tag])


class ErrorPath(BaseModel):
    error_id: str = Field(..., description="System error ID")


@system_bp.get("/errors")
def list_errors(query: SystemErrorListQuery):
    """List system errors with filters."""
    errors, total_count = list_system_errors(
        status=query.status,
        category=query.category,
        source=query.source,
        since=query.since,
        search=query.search,
        limit=query.limit or 50,
        offset=query.offset or 0,
    )
    return {"errors": errors, "total_count": total_count}, 200


@system_bp.post("/errors")
def report_error(body: ReportErrorRequest):
    """Report a frontend error."""
    error_id = capture_error(
        category=body.category,
        message=body.message,
        stack_trace=body.stack_trace,
        context={"raw": body.context_json} if body.context_json else None,
        source=body.source.value if hasattr(body.source, "value") else body.source,
    )
    if not error_id:
        return error_response(
            "CAPTURE_FAILED", "Failed to capture error", HTTPStatus.INTERNAL_SERVER_ERROR
        )
    return {"error_id": error_id}, 201


@system_bp.get("/errors/<error_id>")
def get_error_detail(path: ErrorPath):
    """Get a single error with fix attempts."""
    error = get_system_error_with_fixes(path.error_id)
    if not error:
        return error_response("NOT_FOUND", "Error not found", HTTPStatus.NOT_FOUND)
    return error, 200


@system_bp.patch("/errors/<error_id>")
def update_error(path: ErrorPath, body: UpdateErrorStatusRequest):
    """Update error status."""
    updated = update_system_error_status(path.error_id, body.status.value)
    if not updated:
        return error_response("NOT_FOUND", "Error not found", HTTPStatus.NOT_FOUND)
    return {"message": "Status updated"}, 200


@system_bp.post("/errors/<error_id>/retry-fix")
def retry_fix(path: ErrorPath):
    """Re-trigger autofix for an error."""
    from app.db.system_errors import get_system_error
    from app.services.autofix_service import trigger_autofix

    error = get_system_error(path.error_id)
    if not error:
        return error_response("NOT_FOUND", "Error not found", HTTPStatus.NOT_FOUND)

    trigger_autofix(
        error_id=error["id"],
        category=error["category"],
        message=error["message"],
        stack_trace=error.get("stack_trace"),
        context_json=error.get("context_json"),
    )
    return {"message": "Autofix triggered"}, 200


@system_bp.get("/logs")
def get_logs(query: LogsQuery):
    """Tail recent log file."""
    log_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "logs", "agented.log"
    )

    if not os.path.exists(log_file):
        return {"lines": []}, 200

    lines_count = min(query.lines or 100, 1000)

    # Read from end of file efficiently
    try:
        with open(log_file, "rb") as f:
            f.seek(0, 2)  # Seek to end
            file_size = f.tell()

            if file_size == 0:
                return {"lines": []}, 200

            # Read last chunk (estimate ~200 bytes per line)
            chunk_size = min(file_size, lines_count * 200)
            f.seek(max(0, file_size - chunk_size))
            content = f.read().decode("utf-8", errors="replace")

            all_lines = content.splitlines()
            result_lines = all_lines[-lines_count:]

        return {"lines": result_lines}, 200
    except Exception:
        return {"lines": []}, 200


@system_bp.get("/errors/counts")
def get_error_counts():
    """Get error counts by status."""
    counts = count_errors_by_status()
    return {"counts": counts}, 200
