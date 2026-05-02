"""Workflows namespace — full /admin/workflows/* port (track A, wave 62).

21 routes: CRUD (5), versions (3), execution (run + list + detail +
cancel + stream), analytics (2), DAG validate, approval gates (3),
trigger registration (2). The /executions/{id}/stream SSE polling
loop is preserved verbatim using Litestar's Stream response.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from litestar import MediaType, Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)
from litestar.response import Stream

from app.database import (
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
from app.database import create_workflow as db_create_workflow
from app.db.owned_entities import get_for_user

from ..auth import Caller


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@get("/", sync_to_thread=False)
def list_workflows(caller: Caller) -> dict[str, Any]:
    if caller.user_id:
        return {"workflows": get_for_user("workflows", caller.user_id)}
    return {"workflows": get_all_workflows()}


@post("/", sync_to_thread=False)
def create_workflow(data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    name = data.get("name")
    if not name:
        raise ClientException(detail="name is required")

    graph = data.get("graph")
    if graph:
        from app.services.workflow_validation_service import validate_workflow_dag

        is_valid, errors = validate_workflow_dag(graph)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail={"message": "DAG validation failed", "errors": errors},
            )

    workflow_id = db_create_workflow(
        name=name,
        description=data.get("description"),
        trigger_type=data.get("trigger_type", "manual"),
        trigger_config=data.get("trigger_config"),
    )
    if not workflow_id:
        raise HTTPException(status_code=500, detail="Failed to create workflow")
    return {"message": "Workflow created", "workflow_id": workflow_id}


@get("/pending-approvals", sync_to_thread=False)
def list_pending_approvals(caller: Caller) -> dict[str, Any]:
    del caller
    return {"pending_approvals": get_pending_approval_states()}


@post("/validate", sync_to_thread=False)
def validate_workflow_endpoint(data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    from app.services.workflow_validation_service import validate_workflow_dag

    if not data:
        raise ClientException(detail="JSON body required")
    is_valid, errors = validate_workflow_dag(data.get("graph", {}))
    if not is_valid:
        raise HTTPException(
            status_code=400, detail={"valid": False, "errors": errors}
        )
    return {"valid": True, "errors": errors}


@get("/{workflow_id:str}", sync_to_thread=False)
def get_workflow_endpoint(workflow_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise NotFoundException(detail="Workflow not found")
    return workflow


@put("/{workflow_id:str}", sync_to_thread=False)
def update_workflow_endpoint(
    workflow_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")

    graph = data.get("graph")
    if graph:
        from app.services.workflow_validation_service import validate_workflow_dag

        is_valid, errors = validate_workflow_dag(graph)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail={"message": "DAG validation failed", "errors": errors},
            )

    if not update_workflow(
        workflow_id,
        name=data.get("name"),
        description=data.get("description"),
        trigger_type=data.get("trigger_type"),
        trigger_config=data.get("trigger_config"),
        enabled=data.get("enabled"),
    ):
        raise NotFoundException(detail="Workflow not found or no changes made")
    return get_workflow(workflow_id)


@delete("/{workflow_id:str}", status_code=200, sync_to_thread=False)
def delete_workflow_endpoint(workflow_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    if not delete_workflow(workflow_id):
        raise NotFoundException(detail="Workflow not found")
    return {"message": "Workflow deleted"}


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


@post("/{workflow_id:str}/versions", sync_to_thread=False)
def create_version(
    workflow_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    graph_json = data.get("graph_json")
    if not graph_json:
        raise ClientException(detail="graph_json is required")
    if not get_workflow(workflow_id):
        raise NotFoundException(detail="Workflow not found")
    version, error = add_workflow_version_raw(workflow_id, graph_json)
    if version is None:
        raise ClientException(detail=error or "Failed to create version")
    return {"message": "Version created", "version": version}


@get("/{workflow_id:str}/versions", sync_to_thread=False)
def list_versions(workflow_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return {"versions": get_workflow_versions(workflow_id)}


@get("/{workflow_id:str}/versions/latest", sync_to_thread=False)
def get_latest_version_endpoint(
    workflow_id: str, caller: Caller
) -> dict[str, Any]:
    del caller
    version = get_latest_workflow_version(workflow_id)
    if not version:
        raise NotFoundException(detail="No versions found")
    return version


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


@post("/{workflow_id:str}/run", status_code=202, sync_to_thread=False)
def run_workflow(
    workflow_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    from app.services.workflow_execution_service import WorkflowExecutionService

    timeout_seconds = (data or {}).get("timeout_seconds")
    if timeout_seconds is not None:
        try:
            timeout_seconds = int(timeout_seconds)
            if timeout_seconds <= 0:
                raise ClientException(
                    detail="timeout_seconds must be a positive integer"
                )
        except (TypeError, ValueError):
            raise ClientException(detail="timeout_seconds must be an integer") from None

    try:
        execution_id = WorkflowExecutionService.execute_workflow(
            workflow_id=workflow_id,
            input_json=(data or {}).get("input_json"),
            trigger_type="manual",
            timeout_seconds=timeout_seconds,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise NotFoundException(detail=msg) from None
        raise ClientException(detail=msg) from None

    return {"message": "Workflow execution started", "execution_id": execution_id}


@get("/{workflow_id:str}/executions", sync_to_thread=False)
def list_executions(workflow_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return {"executions": get_workflow_executions(workflow_id)}


@get("/executions/{execution_id:str}", sync_to_thread=False)
def get_execution_detail(
    execution_id: str, caller: Caller
) -> dict[str, Any]:
    del caller
    execution = get_workflow_execution(execution_id)
    if not execution:
        raise NotFoundException(detail="Execution not found")
    return {
        "execution": execution,
        "node_executions": get_workflow_node_executions(execution_id),
    }


@post(
    "/{workflow_id:str}/executions/{execution_id:str}/cancel",
    sync_to_thread=False,
)
def cancel_execution(
    workflow_id: str, execution_id: str, caller: Caller
) -> dict[str, Any]:
    del caller, workflow_id
    from app.services.workflow_execution_service import WorkflowExecutionService

    if not WorkflowExecutionService.cancel_execution(execution_id):
        raise NotFoundException(detail="Execution not found or not running")
    return {"message": "Execution cancelled"}


@get(
    "/{workflow_id:str}/executions/{execution_id:str}/stream",
    media_type=MediaType.TEXT,
    sync_to_thread=False,
)
def stream_execution(
    workflow_id: str, execution_id: str, caller: Caller
) -> Stream:
    del caller, workflow_id
    from app.services.workflow_execution_service import WorkflowExecutionService

    def generate():
        status = WorkflowExecutionService.get_execution_status(execution_id)
        if status is None:
            yield (
                f"data: {json.dumps({'type': 'error', 'message': 'Execution not found'})}\n\n"
            )
            return

        yield (
            "data: "
            + json.dumps(
                {
                    "type": "status",
                    "execution_id": status["execution_id"],
                    "status": status["status"],
                    "node_states": status.get("node_states", {}),
                }
            )
            + "\n\n"
        )

        if status["status"] in ("completed", "failed", "cancelled"):
            yield (
                "data: "
                + json.dumps(
                    {"type": "execution_complete", "status": status["status"]}
                )
                + "\n\n"
            )
            return

        prev_states = dict(status.get("node_states", {}))
        for _ in range(600):
            time.sleep(0.5)
            current = WorkflowExecutionService.get_execution_status(execution_id)
            if current is None:
                yield (
                    "data: "
                    + json.dumps({"type": "error", "message": "Execution lost"})
                    + "\n\n"
                )
                return
            current_states = current.get("node_states", {})
            for node_id, node_status in current_states.items():
                if node_status != prev_states.get(node_id):
                    if node_status == "running":
                        event_type = "node_start"
                    elif node_status == "completed":
                        event_type = "node_complete"
                    elif node_status == "failed":
                        event_type = "node_failed"
                    else:
                        event_type = "node_start"
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "type": event_type,
                                "node_id": node_id,
                                "status": node_status,
                            }
                        )
                        + "\n\n"
                    )
            prev_states = dict(current_states)
            if current["status"] in ("completed", "failed", "cancelled"):
                yield (
                    "data: "
                    + json.dumps(
                        {"type": "execution_complete", "status": current["status"]}
                    )
                    + "\n\n"
                )
                return

    return Stream(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@get("/{workflow_id:str}/analytics", sync_to_thread=False)
def workflow_analytics(
    workflow_id: str, caller: Caller, days: int = 30
) -> dict[str, Any]:
    del caller
    if not get_workflow(workflow_id):
        raise NotFoundException(detail="Workflow not found")
    return {
        "nodes": get_workflow_node_analytics(workflow_id),
        "summary": get_workflow_execution_analytics(workflow_id, days=days),
    }


@get("/executions/{execution_id:str}/timeline", sync_to_thread=False)
def execution_timeline(
    execution_id: str, caller: Caller
) -> dict[str, Any]:
    del caller
    execution = get_workflow_execution(execution_id)
    if not execution:
        raise NotFoundException(detail="Execution not found")
    return {
        "nodes": get_workflow_execution_timeline(execution_id),
        "workflow_id": execution.get("workflow_id"),
        "status": execution.get("status"),
    }


# ---------------------------------------------------------------------------
# Approval gates
# ---------------------------------------------------------------------------


@post(
    "/executions/{execution_id:str}/nodes/{node_id:str}/approve",
    sync_to_thread=False,
)
def approve_node(
    execution_id: str, node_id: str, data: Optional[dict], caller: Caller
) -> dict[str, Any]:
    del caller
    from app.services.workflow_execution_service import WorkflowExecutionService

    resolved_by = (data or {}).get("resolved_by") if data else None
    if not WorkflowExecutionService.approve_node(
        execution_id, node_id, resolved_by=resolved_by
    ):
        raise NotFoundException(
            detail="Approval not found or node is not pending approval"
        )
    return {"message": "Node approved", "execution_id": execution_id}


@post(
    "/executions/{execution_id:str}/nodes/{node_id:str}/reject",
    sync_to_thread=False,
)
def reject_node(
    execution_id: str, node_id: str, data: Optional[dict], caller: Caller
) -> dict[str, Any]:
    del caller
    from app.services.workflow_execution_service import WorkflowExecutionService

    resolved_by = (data or {}).get("resolved_by") if data else None
    if not WorkflowExecutionService.reject_node(
        execution_id, node_id, resolved_by=resolved_by
    ):
        raise NotFoundException(
            detail="Approval not found or node is not pending approval"
        )
    return {"message": "Node rejected", "execution_id": execution_id}


# ---------------------------------------------------------------------------
# Trigger management
# ---------------------------------------------------------------------------


@post("/{workflow_id:str}/triggers/register", sync_to_thread=False)
def register_trigger(workflow_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    from app.services.workflow_trigger_service import WorkflowTriggerService

    workflow = get_workflow(workflow_id)
    if not workflow:
        raise NotFoundException(detail="Workflow not found")
    trigger_type = workflow.get("trigger_type", "manual")
    if trigger_type == "manual":
        raise ClientException(
            detail="Manual workflows do not have registerable triggers"
        )
    config_str = workflow.get("trigger_config")
    if not config_str:
        raise ClientException(detail="Workflow has no trigger_config")
    try:
        config = json.loads(config_str)
    except (json.JSONDecodeError, TypeError):
        raise ClientException(detail="Invalid trigger_config JSON") from None
    try:
        WorkflowTriggerService.register_trigger(workflow_id, trigger_type, config)
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None
    return {"message": f"Trigger registered for workflow {workflow_id}"}


@delete(
    "/{workflow_id:str}/triggers/unregister",
    status_code=200,
    sync_to_thread=False,
)
def unregister_trigger(workflow_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    from app.services.workflow_trigger_service import WorkflowTriggerService

    workflow = get_workflow(workflow_id)
    if not workflow:
        raise NotFoundException(detail="Workflow not found")
    trigger_type = workflow.get("trigger_type", "manual")
    if trigger_type == "manual":
        raise ClientException(
            detail="Manual workflows do not have registerable triggers"
        )
    try:
        WorkflowTriggerService.unregister_trigger(workflow_id, trigger_type)
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None
    return {"message": f"Trigger unregistered for workflow {workflow_id}"}


workflows_router = Router(
    path="/admin/workflows",
    route_handlers=[
        list_workflows,
        create_workflow,
        list_pending_approvals,
        validate_workflow_endpoint,
        get_workflow_endpoint,
        update_workflow_endpoint,
        delete_workflow_endpoint,
        create_version,
        list_versions,
        get_latest_version_endpoint,
        run_workflow,
        list_executions,
        get_execution_detail,
        cancel_execution,
        stream_execution,
        workflow_analytics,
        execution_timeline,
        approve_node,
        reject_node,
        register_trigger,
        unregister_trigger,
    ],
)
