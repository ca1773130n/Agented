"""Interactive plugin setup API endpoints with SSE streaming."""

from http import HTTPStatus

from flask import Response
from flask_openapi3 import APIBlueprint, Tag

from ..database import get_project
from ..models.setup import (
    SetupExecutionPath,
    SetupResponseRequest,
    StartSetupRequest,
    StartSetupResponse,
)
from ..services.setup_execution_service import SetupExecutionService
from ..services.setup_service import SetupBundleService

tag = Tag(name="setup", description="Interactive plugin setup operations")
setup_bp = APIBlueprint("setup", __name__, url_prefix="/api/setup", abp_tags=[tag])


@setup_bp.post("/start")
def start_setup(body: StartSetupRequest):
    """Start an interactive setup execution for a project."""
    project = get_project(body.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    try:
        execution_id = SetupExecutionService.start_setup(
            project_id=body.project_id,
            command=body.command,
        )
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.BAD_REQUEST
    except Exception as e:
        return {"error": f"Failed to start setup: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR

    return (
        StartSetupResponse(
            execution_id=execution_id,
            status="running",
        ).model_dump(),
        HTTPStatus.CREATED,
    )


@setup_bp.get("/<execution_id>/stream")
def stream_setup(path: SetupExecutionPath):
    """SSE endpoint for real-time setup streaming.

    Returns Server-Sent Events with the following event types:
    - log: A log line (stdout or stderr)
    - question: An interaction question requiring user input
    - status: Execution status update
    - complete: Execution finished
    - error: An error occurred
    """
    status = SetupExecutionService.get_status(path.execution_id)
    if not status:
        return {"error": "Setup execution not found"}, HTTPStatus.NOT_FOUND

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


@setup_bp.post("/<execution_id>/respond")
def respond_setup(path: SetupExecutionPath, body: SetupResponseRequest):
    """Submit a user response to an interactive setup question."""
    status = SetupExecutionService.get_status(path.execution_id)
    if not status:
        return {"error": "Setup execution not found"}, HTTPStatus.NOT_FOUND

    success = SetupExecutionService.submit_response(
        execution_id=path.execution_id,
        interaction_id=body.interaction_id,
        response=body.response,
    )

    if not success:
        return {"error": "No pending interaction found"}, HTTPStatus.NOT_FOUND

    return {"status": "ok"}, HTTPStatus.OK


@setup_bp.get("/<execution_id>/status")
def get_setup_status(path: SetupExecutionPath):
    """Get the current status of a setup execution."""
    status = SetupExecutionService.get_status(path.execution_id)
    if not status:
        return {"error": "Setup execution not found"}, HTTPStatus.NOT_FOUND

    return status, HTTPStatus.OK


@setup_bp.delete("/<execution_id>")
def cancel_setup(path: SetupExecutionPath):
    """Cancel a running setup execution."""
    status = SetupExecutionService.get_status(path.execution_id)
    if not status:
        return {"error": "Setup execution not found"}, HTTPStatus.NOT_FOUND

    SetupExecutionService.cancel_setup(path.execution_id)
    return {"message": "Setup cancelled"}, HTTPStatus.OK


@setup_bp.post("/bundle-install")
def bundle_install():
    """Auto-install bundled marketplace and plugins on first launch."""
    result, status = SetupBundleService.bundle_install()
    return result, status
