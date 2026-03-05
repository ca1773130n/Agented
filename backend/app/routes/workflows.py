"""Workflow management API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..database import (
    add_workflow_version_raw,
    delete_workflow,
    get_all_workflows,
    get_latest_workflow_version,
    get_pending_approval_states,
    get_workflow,
    get_workflow_execution,
    get_workflow_execution_analytics,
    get_workflow_execution_timeline,
    get_workflow_executions,
    get_workflow_node_analytics,
    get_workflow_node_executions,
    get_workflow_versions,
    update_workflow,
)
from ..database import (
    create_workflow as db_create_workflow,
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


class ApprovalNodePath(BaseModel):
    execution_id: str = Field(..., description="Workflow execution ID")
    node_id: str = Field(..., description="Node ID within the workflow")


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
    """Create a new workflow with optional DAG validation."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    name = data.get("name")
    if not name:
        return error_response("BAD_REQUEST", "name is required", HTTPStatus.BAD_REQUEST)

    # Validate graph if provided at creation time
    graph = data.get("graph")
    if graph:
        from ..services.workflow_validation_service import validate_workflow_dag

        is_valid, errors = validate_workflow_dag(graph)
        if not is_valid:
            return error_response(
                "BAD_REQUEST",
                "DAG validation failed",
                HTTPStatus.BAD_REQUEST,
                details={"errors": errors},
            )

    workflow_id = db_create_workflow(
        name=name,
        description=data.get("description"),
        trigger_type=data.get("trigger_type", "manual"),
        trigger_config=data.get("trigger_config"),
    )
    if not workflow_id:
        return error_response(
            "INTERNAL_SERVER_ERROR", "Failed to create workflow", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    return {"message": "Workflow created", "workflow_id": workflow_id}, HTTPStatus.CREATED


@workflows_bp.get("/<workflow_id>")
def get_workflow_endpoint(path: WorkflowPath):
    """Get a single workflow by ID."""
    workflow = get_workflow(path.workflow_id)
    if not workflow:
        return error_response("NOT_FOUND", "Workflow not found", HTTPStatus.NOT_FOUND)
    return workflow, HTTPStatus.OK


@workflows_bp.put("/<workflow_id>")
def update_workflow_endpoint(path: WorkflowPath):
    """Update a workflow with optional DAG validation."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    # Validate graph if provided during update
    graph = data.get("graph")
    if graph:
        from ..services.workflow_validation_service import validate_workflow_dag

        is_valid, errors = validate_workflow_dag(graph)
        if not is_valid:
            return error_response(
                "BAD_REQUEST",
                "DAG validation failed",
                HTTPStatus.BAD_REQUEST,
                details={"errors": errors},
            )

    if not update_workflow(
        path.workflow_id,
        name=data.get("name"),
        description=data.get("description"),
        trigger_type=data.get("trigger_type"),
        trigger_config=data.get("trigger_config"),
        enabled=data.get("enabled"),
    ):
        return error_response(
            "NOT_FOUND", "Workflow not found or no changes made", HTTPStatus.NOT_FOUND
        )

    workflow = get_workflow(path.workflow_id)
    return workflow, HTTPStatus.OK


@workflows_bp.delete("/<workflow_id>")
def delete_workflow_endpoint(path: WorkflowPath):
    """Delete a workflow (cascades to versions and executions)."""
    if not delete_workflow(path.workflow_id):
        return error_response("NOT_FOUND", "Workflow not found", HTTPStatus.NOT_FOUND)
    return {"message": "Workflow deleted"}, HTTPStatus.OK


# =============================================================================
# Version Endpoints
# =============================================================================


@workflows_bp.post("/<workflow_id>/versions")
def create_version(path: WorkflowPath):
    """Create a new version for a workflow with DAG validation."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    graph_json = data.get("graph_json")
    if not graph_json:
        return error_response("BAD_REQUEST", "graph_json is required", HTTPStatus.BAD_REQUEST)

    # Check workflow exists
    workflow = get_workflow(path.workflow_id)
    if not workflow:
        return error_response("NOT_FOUND", "Workflow not found", HTTPStatus.NOT_FOUND)

    version, error = add_workflow_version_raw(path.workflow_id, graph_json)
    if version is None:
        return error_response("BAD_REQUEST", error, HTTPStatus.BAD_REQUEST)

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
        return error_response("NOT_FOUND", "No versions found", HTTPStatus.NOT_FOUND)
    return version, HTTPStatus.OK


# =============================================================================
# Execution Endpoints
# =============================================================================


@workflows_bp.post("/<workflow_id>/run")
def run_workflow(path: WorkflowPath):
    """Run a workflow -- dispatches to WorkflowExecutionService for DAG execution.

    Request body (JSON):
    - input_json (str, optional): Initial input data for the workflow as a
      JSON string. This value is passed as the input to the first node(s) in
      the DAG. The format of input_json depends on the entry node's expected
      input schema -- typically a JSON object with keys matching the node's
      declared input parameters.
    - timeout_seconds (int, optional): Per-run timeout override in seconds.
      Overrides the timeout set in the workflow graph settings for this
      execution only. Default: uses the workflow's configured timeout.

    Response: {"execution_id": str, "status": "started"|"error", ...}
    """
    from ..services.workflow_execution_service import WorkflowExecutionService

    data = request.get_json(silent=True) or {}
    input_json = data.get("input_json")
    timeout_seconds = data.get("timeout_seconds")
    if timeout_seconds is not None:
        try:
            timeout_seconds = int(timeout_seconds)
            if timeout_seconds <= 0:
                return error_response(
                    "BAD_REQUEST",
                    "timeout_seconds must be a positive integer",
                    HTTPStatus.BAD_REQUEST,
                )
        except (TypeError, ValueError):
            return error_response(
                "BAD_REQUEST", "timeout_seconds must be an integer", HTTPStatus.BAD_REQUEST
            )

    try:
        execution_id = WorkflowExecutionService.execute_workflow(
            workflow_id=path.workflow_id,
            input_json=input_json,
            trigger_type="manual",
            timeout_seconds=timeout_seconds,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            return error_response("NOT_FOUND", error_msg, HTTPStatus.NOT_FOUND)
        return error_response("BAD_REQUEST", error_msg, HTTPStatus.BAD_REQUEST)

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
        return error_response("NOT_FOUND", "Execution not found", HTTPStatus.NOT_FOUND)

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
        return error_response(
            "NOT_FOUND", "Execution not found or not running", HTTPStatus.NOT_FOUND
        )

    return {"message": "Execution cancelled"}, HTTPStatus.OK


@workflows_bp.get("/<workflow_id>/executions/<execution_id>/stream")
def stream_workflow_execution(path: WorkflowExecutionIdPath):
    """SSE endpoint for real-time workflow execution monitoring.

    SSE Protocol:
    - Event 'status': {"execution_id": str, "status": str, "node_states": dict}
    - Event 'node_start': {"node_id": str, "status": "running"}
    - Event 'node_complete': {"node_id": str, "status": "completed"}
    - Event 'node_failed': {"node_id": str, "status": "failed"}
    - Event 'execution_complete': {"status": "completed"|"failed"|"cancelled"}
    - Event 'error': {"message": str}

    Polls every 0.5 seconds for up to 5 minutes. Emits node state transitions
    as they occur and terminates with execution_complete when the workflow
    reaches a terminal state.
    """
    import json
    import time

    from flask import Response

    from ..services.workflow_execution_service import WorkflowExecutionService

    def generate():
        """Yield SSE events polling workflow execution status until completion."""
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
# Analytics Endpoints
# =============================================================================


@workflows_bp.get("/<workflow_id>/analytics")
def workflow_analytics(path: WorkflowPath):
    """Get per-node success/failure rates and aggregate stats for a workflow."""
    workflow = get_workflow(path.workflow_id)
    if not workflow:
        return error_response("NOT_FOUND", "Workflow not found", HTTPStatus.NOT_FOUND)

    days = request.args.get("days", 30, type=int)
    nodes = get_workflow_node_analytics(path.workflow_id)
    summary = get_workflow_execution_analytics(path.workflow_id, days=days)

    return {"nodes": nodes, "summary": summary}, HTTPStatus.OK


@workflows_bp.get("/executions/<execution_id>/timeline")
def workflow_execution_timeline(path: WorkflowExecutionPath):
    """Get ordered node execution timeline for debugging a workflow execution."""
    execution = get_workflow_execution(path.execution_id)
    if not execution:
        return error_response("NOT_FOUND", "Execution not found", HTTPStatus.NOT_FOUND)

    nodes = get_workflow_execution_timeline(path.execution_id)
    return {
        "nodes": nodes,
        "workflow_id": execution.get("workflow_id"),
        "status": execution.get("status"),
    }, HTTPStatus.OK


# =============================================================================
# DAG Validation Endpoint
# =============================================================================


@workflows_bp.post("/validate")
def validate_workflow():
    """Validate a workflow DAG without saving (API-09)."""
    from ..services.workflow_validation_service import validate_workflow_dag

    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    graph = data.get("graph", {})
    is_valid, errors = validate_workflow_dag(graph)
    status = HTTPStatus.OK if is_valid else HTTPStatus.BAD_REQUEST
    return {"valid": is_valid, "errors": errors}, status


# =============================================================================
# Approval Gate Endpoints
# =============================================================================


@workflows_bp.post("/executions/<execution_id>/nodes/<node_id>/approve")
def approve_workflow_node(path: ApprovalNodePath):
    """Approve a pending approval gate node to resume workflow execution."""
    from ..services.workflow_execution_service import WorkflowExecutionService

    data = request.get_json(silent=True) or {}
    resolved_by = data.get("resolved_by")

    success = WorkflowExecutionService.approve_node(
        path.execution_id, path.node_id, resolved_by=resolved_by
    )
    if not success:
        return error_response(
            "NOT_FOUND", "Approval not found or node is not pending approval", HTTPStatus.NOT_FOUND
        )

    return {"message": "Node approved", "execution_id": path.execution_id}, HTTPStatus.OK


@workflows_bp.post("/executions/<execution_id>/nodes/<node_id>/reject")
def reject_workflow_node(path: ApprovalNodePath):
    """Reject a pending approval gate node to abort downstream execution."""
    from ..services.workflow_execution_service import WorkflowExecutionService

    data = request.get_json(silent=True) or {}
    resolved_by = data.get("resolved_by")

    success = WorkflowExecutionService.reject_node(
        path.execution_id, path.node_id, resolved_by=resolved_by
    )
    if not success:
        return error_response(
            "NOT_FOUND", "Approval not found or node is not pending approval", HTTPStatus.NOT_FOUND
        )

    return {"message": "Node rejected", "execution_id": path.execution_id}, HTTPStatus.OK


@workflows_bp.get("/pending-approvals")
def list_pending_approvals():
    """List all pending approval gate states across all workflow executions."""
    approvals = get_pending_approval_states()
    return {"pending_approvals": approvals}, HTTPStatus.OK


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
        return error_response("NOT_FOUND", "Workflow not found", HTTPStatus.NOT_FOUND)

    trigger_type = workflow.get("trigger_type", "manual")
    if trigger_type == "manual":
        return error_response(
            "BAD_REQUEST",
            "Manual workflows do not have registerable triggers",
            HTTPStatus.BAD_REQUEST,
        )

    config_str = workflow.get("trigger_config")
    if not config_str:
        return error_response(
            "BAD_REQUEST", "Workflow has no trigger_config", HTTPStatus.BAD_REQUEST
        )

    try:
        config = json.loads(config_str)
    except (json.JSONDecodeError, TypeError):
        return error_response("BAD_REQUEST", "Invalid trigger_config JSON", HTTPStatus.BAD_REQUEST)

    try:
        WorkflowTriggerService.register_trigger(path.workflow_id, trigger_type, config)
    except ValueError as e:
        return error_response("BAD_REQUEST", str(e), HTTPStatus.BAD_REQUEST)

    return {"message": f"Trigger registered for workflow {path.workflow_id}"}, HTTPStatus.OK


@workflows_bp.delete("/<workflow_id>/triggers/unregister")
def unregister_trigger(path: WorkflowPath):
    """Unregister an active trigger for a workflow."""
    from ..services.workflow_trigger_service import WorkflowTriggerService

    workflow = get_workflow(path.workflow_id)
    if not workflow:
        return error_response("NOT_FOUND", "Workflow not found", HTTPStatus.NOT_FOUND)

    trigger_type = workflow.get("trigger_type", "manual")
    if trigger_type == "manual":
        return error_response(
            "BAD_REQUEST",
            "Manual workflows do not have registerable triggers",
            HTTPStatus.BAD_REQUEST,
        )

    try:
        WorkflowTriggerService.unregister_trigger(path.workflow_id, trigger_type)
    except ValueError as e:
        return error_response("BAD_REQUEST", str(e), HTTPStatus.BAD_REQUEST)

    return {"message": f"Trigger unregistered for workflow {path.workflow_id}"}, HTTPStatus.OK
