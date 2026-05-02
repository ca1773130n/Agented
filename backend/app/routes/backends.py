"""Backends CRUD migrated to Litestar :20002 in wave 73.

Two SSE streaming routes stay on Flask until the dedicated streaming wave:
- /admin/backends/{id}/connect/{session_id}/stream
- /admin/backends/test/{test_id}/stream
"""

from http import HTTPStatus

from flask import Response
from flask_openapi3 import APIBlueprint
from pydantic import BaseModel, Field

from app.models.common import error_response
from ..models.backend_cli import BackendConnectSessionPath, TestStreamPath
from ..services.backend_cli_service import BackendCLIService

backends_bp = APIBlueprint("backends", __name__, url_prefix="/admin/backends")


@backends_bp.get("/<backend_id>/connect/<session_id>/stream")
def stream_connect(path: BackendConnectSessionPath):
    """SSE endpoint for real-time CLI login streaming."""
    status = BackendCLIService.get_status(path.session_id)
    if not status:
        return error_response("NOT_FOUND", "Session not found", HTTPStatus.NOT_FOUND)

    def generate():
        for event in BackendCLIService.subscribe(path.session_id):
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


@backends_bp.get("/test/<test_id>/stream")
def stream_backend_test(path: TestStreamPath):
    """SSE endpoint for real-time backend test output streaming."""
    from ..services.backend_test_service import BackendTestService

    def generate():
        for event in BackendTestService.subscribe_test(path.test_id):
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
