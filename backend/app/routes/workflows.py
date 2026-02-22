"""Workflow management API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    add_workflow,
    add_workflow_version_raw,
    delete_workflow,
    get_all_workflows,
    get_latest_workflow_version,
    get_workflow,
    get_workflow_execution,
    get_workflow_executions,
    get_workflow_node_executions,
    get_workflow_versions,
    update_workflow,
)

tag = Tag(name="workflows", description="Workflow management operations")
workflows_bp = APIBlueprint("workflows", __name__, url_prefix="/admin/workflows", abp_tags=[tag])


# --- Path models ---


class WorkflowPath(BaseModel):
    workflow_id: str = Field(..., description="Workflow ID")


class WorkflowVersionPath(BaseModel):
    workflow_id: str = Field(..., description="Workflow ID")
    version: int = Field(..., description="Version number")


class WorkflowExecutionPath(BaseModel):
    execution_id: str = Field(..., description="Workflow execution ID")


class WorkflowExecutionIdPath(BaseModel):
    workflow_id: str = Field(..., description="Workflow ID")
    execution_id: str = Field(..., description="Workflow execution ID")


# =============================================================================
# Workflow CRUD
# =============================================================================


@workflows_bp.get("/")
def list_workflows():
    """List all workflows with latest version numbers."""
    workflows = get_all_workflows()
    return {"workflows": workflows}, HTTPStatus.OK


@workflows_bp.post("/")
def create_workflow():
    """Create a new workflow."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    name = data.get("name")
    if not name:
        return {"error": "name is required"}, HTTPStatus.BAD_REQUEST

    workflow_id = add_workflow(
        name=name,
        description=data.get("description"),
        trigger_type=data.get("trigger_type", "manual"),
        trigger_config=data.get("trigger_config"),
    )
    if not workflow_id:
        return {"error": "Failed to create workflow"}, HTTPStatus.INTERNAL_SERVER_ERROR

    return {"message": "Workflow created", "workflow_id": workflow_id}, HTTPStatus.CREATED


@workflows_bp.get("/<workflow_id>")
def get_workflow_endpoint(path: WorkflowPath):
    """Get a single workflow by ID."""
    workflow = get_workflow(path.workflow_id)
    if not workflow:
        return {"error": "Workflow not found"}, HTTPStatus.NOT_FOUND
    return workflow, HTTPStatus.OK


@workflows_bp.put("/<workflow_id>")
def update_workflow_endpoint(path: WorkflowPath):
    """Update a workflow."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    if not update_workflow(
        path.workflow_id,
        name=data.get("name"),
        description=data.get("description"),
        trigger_type=data.get("trigger_type"),
        trigger_config=data.get("trigger_config"),
        enabled=data.get("enabled"),
    ):
        return {"error": "Workflow not found or no changes made"}, HTTPStatus.NOT_FOUND

    workflow = get_workflow(path.workflow_id)
    return workflow, HTTPStatus.OK


@workflows_bp.delete("/<workflow_id>")
def delete_workflow_endpoint(path: WorkflowPath):
    """Delete a workflow (cascades to versions and executions)."""
    if not delete_workflow(path.workflow_id):
        return {"error": "Workflow not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Workflow deleted"}, HTTPStatus.OK


# =============================================================================
# Version Endpoints
# =============================================================================


@workflows_bp.post("/<workflow_id>/versions")
def create_version(path: WorkflowPath):
    """Create a new version for a workflow with DAG validation."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    graph_json = data.get("graph_json")
    if not graph_json:
        return {"error": "graph_json is required"}, HTTPStatus.BAD_REQUEST

    # Check workflow exists
    workflow = get_workflow(path.workflow_id)
    if not workflow:
        return {"error": "Workflow not found"}, HTTPStatus.NOT_FOUND

    version, error = add_workflow_version_raw(path.workflow_id, graph_json)
    if version is None:
        return {"error": error}, HTTPStatus.BAD_REQUEST

    return {"message": "Version created", "version": version}, HTTPStatus.CREATED


@workflows_bp.get("/<workflow_id>/versions")
def list_versions(path: WorkflowPath):
    """List all versions for a workflow."""
    versions = get_workflow_versions(path.workflow_id)
    return {"versions": versions}, HTTPStatus.OK


@workflows_bp.get("/<workflow_id>/versions/latest")
def get_latest_version_endpoint(path: WorkflowPath):
    """Get the latest version for a workflow."""
    version = get_latest_workflow_version(path.workflow_id)
    if not version:
        return {"error": "No versions found"}, HTTPStatus.NOT_FOUND
    return version, HTTPStatus.OK


# =============================================================================
# Execution Endpoints
# =============================================================================


@workflows_bp.post("/<workflow_id>/run")
def run_workflow(path: WorkflowPath):
    """Run a workflow — dispatches to WorkflowExecutionService for DAG execution."""
    from ..services.workflow_execution_service import WorkflowExecutionService

    data = request.get_json(silent=True) or {}
    input_json = data.get("input_json")

    try:
        execution_id = WorkflowExecutionService.execute_workflow(
            workflow_id=path.workflow_id,
            input_json=input_json,
            trigger_type="manual",
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            return {"error": error_msg}, HTTPStatus.NOT_FOUND
        return {"error": error_msg}, HTTPStatus.BAD_REQUEST

    return (
        {"message": "Workflow execution started", "execution_id": execution_id},
        HTTPStatus.ACCEPTED,
    )


@workflows_bp.get("/<workflow_id>/executions")
def list_executions(path: WorkflowPath):
    """List all executions for a workflow."""
    executions = get_workflow_executions(path.workflow_id)
    return {"executions": executions}, HTTPStatus.OK


@workflows_bp.get("/executions/<execution_id>")
def get_execution_detail(path: WorkflowExecutionPath):
    """Get execution details including node executions."""
    execution = get_workflow_execution(path.execution_id)
    if not execution:
        return {"error": "Execution not found"}, HTTPStatus.NOT_FOUND

    node_executions = get_workflow_node_executions(path.execution_id)
    return {
        "execution": execution,
        "node_executions": node_executions,
    }, HTTPStatus.OK


@workflows_bp.post("/<workflow_id>/executions/<execution_id>/cancel")
def cancel_workflow_execution(path: WorkflowExecutionIdPath):
    """Cancel a running workflow execution."""
    from ..services.workflow_execution_service import WorkflowExecutionService

    success = WorkflowExecutionService.cancel_execution(path.execution_id)
    if not success:
        return {"error": "Execution not found or not running"}, HTTPStatus.NOT_FOUND

    return {"message": "Execution cancelled"}, HTTPStatus.OK


@workflows_bp.get("/<workflow_id>/executions/<execution_id>/stream")
def stream_workflow_execution(path: WorkflowExecutionIdPath):
    """SSE endpoint for real-time workflow execution monitoring.

    Returns Server-Sent Events with the following event types:
    - status: Initial execution status with node_states
    - node_start: A node transitioned to running
    - node_complete: A node transitioned to completed
    - node_failed: A node transitioned to failed
    - execution_complete: Execution finished (completed/failed/cancelled)
    - error: Execution not found
    """
    import json
    import time

    from flask import Response

    from ..services.workflow_execution_service import WorkflowExecutionService

    def generate():
        # Get initial status
        status = WorkflowExecutionService.get_execution_status(path.execution_id)
        if status is None:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Execution not found'})}\n\n"
            return

        # Emit initial status event
        yield (
            f"data: {json.dumps({'type': 'status', 'execution_id': status['execution_id'], 'status': status['status'], 'node_states': status.get('node_states', {})})}\n\n"
        )

        # Check if already terminal
        if status["status"] in ("completed", "failed", "cancelled"):
            yield f"data: {json.dumps({'type': 'execution_complete', 'status': status['status']})}\n\n"
            return

        prev_node_states = dict(status.get("node_states", {}))

        # Poll loop
        for _ in range(600):  # 600 iterations * 0.5s = 5 min max
            time.sleep(0.5)

            current = WorkflowExecutionService.get_execution_status(path.execution_id)
            if current is None:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Execution lost'})}\n\n"
                return

            current_node_states = current.get("node_states", {})

            # Detect node state changes
            for node_id, node_status in current_node_states.items():
                prev_status = prev_node_states.get(node_id)
                if node_status != prev_status:
                    if node_status == "running":
                        event_type = "node_start"
                    elif node_status == "completed":
                        event_type = "node_complete"
                    elif node_status == "failed":
                        event_type = "node_failed"
                    else:
                        event_type = "node_start"  # default for other transitions
                    yield f"data: {json.dumps({'type': event_type, 'node_id': node_id, 'status': node_status})}\n\n"

            prev_node_states = dict(current_node_states)

            # Check for terminal state
            if current["status"] in ("completed", "failed", "cancelled"):
                yield f"data: {json.dumps({'type': 'execution_complete', 'status': current['status']})}\n\n"
                return

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# =============================================================================
# Trigger Management Endpoints
# =============================================================================


@workflows_bp.post("/<workflow_id>/triggers/register")
def register_trigger(path: WorkflowPath):
    """Register an active trigger for a workflow based on its trigger_type and trigger_config."""
    import json

    from ..services.workflow_trigger_service import WorkflowTriggerService

    workflow = get_workflow(path.workflow_id)
    if not workflow:
        return {"error": "Workflow not found"}, HTTPStatus.NOT_FOUND

    trigger_type = workflow.get("trigger_type", "manual")
    if trigger_type == "manual":
        return {
            "error": "Manual workflows do not have registerable triggers"
        }, HTTPStatus.BAD_REQUEST

    config_str = workflow.get("trigger_config")
    if not config_str:
        return {"error": "Workflow has no trigger_config"}, HTTPStatus.BAD_REQUEST

    try:
        config = json.loads(config_str)
    except (json.JSONDecodeError, TypeError):
        return {"error": "Invalid trigger_config JSON"}, HTTPStatus.BAD_REQUEST

    try:
        WorkflowTriggerService.register_trigger(path.workflow_id, trigger_type, config)
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.BAD_REQUEST

    return {"message": f"Trigger registered for workflow {path.workflow_id}"}, HTTPStatus.OK


@workflows_bp.delete("/<workflow_id>/triggers/unregister")
def unregister_trigger(path: WorkflowPath):
    """Unregister an active trigger for a workflow."""
    from ..services.workflow_trigger_service import WorkflowTriggerService

    workflow = get_workflow(path.workflow_id)
    if not workflow:
        return {"error": "Workflow not found"}, HTTPStatus.NOT_FOUND

    trigger_type = workflow.get("trigger_type", "manual")
    if trigger_type == "manual":
        return {
            "error": "Manual workflows do not have registerable triggers"
        }, HTTPStatus.BAD_REQUEST

    try:
        WorkflowTriggerService.unregister_trigger(path.workflow_id, trigger_type)
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.BAD_REQUEST

    return {"message": f"Trigger unregistered for workflow {path.workflow_id}"}, HTTPStatus.OK
