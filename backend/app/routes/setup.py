"""Setup CRUD migrated to Litestar :20002 in wave 76.

Only /api/setup/{id}/stream stays on Flask until the streaming wave.
"""

from http import HTTPStatus

from flask import Response
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response
from ..services.setup_execution_service import SetupExecutionService

tag = Tag(name="setup", description="Setup streaming (Flask leftover)")
setup_bp = APIBlueprint("setup", __name__, url_prefix="/api/setup", abp_tags=[tag])


class SetupExecutionPath(BaseModel):
    execution_id: str = Field(..., description="Setup execution ID")


@setup_bp.get("/<execution_id>/stream")
def stream_setup(path: SetupExecutionPath):
    status = SetupExecutionService.get_status(path.execution_id)
    if not status:
        return error_response("NOT_FOUND", "Setup execution not found", HTTPStatus.NOT_FOUND)

    def generate():
        for event in SetupExecutionService.subscribe(path.execution_id):
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
