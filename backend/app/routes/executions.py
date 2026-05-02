"""Execution routes — SSE leftover (wave 75).

CRUD/cancel/pause/resume/queue/quotas migrated to Litestar :20002. Only
the per-execution SSE stream stays on Flask until the streaming wave.
"""

from http import HTTPStatus

from flask import Response
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response
from ..services.execution_log_service import ExecutionLogService

tag = Tag(name="executions", description="Execution streaming (Flask leftover)")
executions_bp = APIBlueprint("executions", __name__, url_prefix="/admin", abp_tags=[tag])


class ExecutionPath(BaseModel):
    execution_id: str = Field(..., description="Execution ID")


@executions_bp.get("/executions/<execution_id>/stream")
def stream_execution(path: ExecutionPath):
    """SSE endpoint for real-time log streaming."""
    execution = ExecutionLogService.get_execution(path.execution_id)
    if not execution:
        return error_response("NOT_FOUND", "Execution not found", HTTPStatus.NOT_FOUND)

    def generate():
        for event in ExecutionLogService.subscribe(path.execution_id):
            yield event

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
