"""Comprehensive tests for workflow execution engine — all Phase 7 WF requirements.

This file contains:
1. Original workflow execution tests (basic execution, node order, error handling, etc.)
2. Phase 7 new tests:
   - WF-02: Safe expression evaluator (AST-based, no eval/exec)
   - WF-03: Approval gate node (approve, reject, timeout, DB persistence)
   - WF-04: Agent node with OrchestrationService fallback chain and routing rules
   - WF-05: Edge-aware conditional branching (true/false/skip-downstream)
   - WF-06: Per-node retry policy with configurable backoff strategies
"""

import json
import threading
import time
from unittest.mock import patch

import pytest

from app.models.workflow import (
    AgentNodeConfig,
    FallbackChainEntry,
    RoutingRules,
    WorkflowMessage,
    WorkflowNode,
)
from app.services.workflow_execution_service import (
    WorkflowExecutionService,
    evaluate_condition,
)

# =============================================================================
# Helpers
# =============================================================================


def _create_test_workflow(client, name="Test Workflow"):
    """Create a workflow via API and return workflow_id."""
    resp = client.post("/admin/workflows/", json={"name": name})
    assert resp.status_code == 201
    return resp.get_json()["workflow_id"]


def _create_test_version(client, workflow_id, graph):
    """Create a version with a given graph dict, return version number."""
    graph_json = json.dumps(graph) if isinstance(graph, dict) else graph
    resp = client.post(
        f"/admin/workflows/{workflow_id}/versions",
        json={"graph_json": graph_json},
    )
    assert resp.status_code == 201
    return resp.get_json()["version"]


def _make_graph(nodes, edges, settings=None):
    """Build a valid graph dict from simplified node/edge definitions."""
    graph = {"nodes": nodes, "edges": edges}
    if settings:
        graph["settings"] = settings
    return graph


def _wait_for_execution(client, execution_id, timeout=5):
    """Poll execution status until not running, or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/admin/workflows/executions/{execution_id}")
        body = resp.get_json()
        status = body["execution"]["status"]
        if status not in ("running", "pending", "pending_approval"):
            return body
        time.sleep(0.1)
    # Final check
    resp = client.get(f"/admin/workflows/executions/{execution_id}")
    return resp.get_json()


def make_test_graph(nodes, edges=None):
    """Build a valid graph_parsed dict for _run_workflow (Phase 7 helper).

    Args:
        nodes: list of dicts with at least {id, type, label}. Extra keys like
               config, error_mode, retry_max are passed through.
        edges: list of dicts with {source, target} and optional sourceHandle.

    Returns:
        A dict matching the format expected by _run_workflow.
    """
    return {
        "nodes": nodes,
        "edges": edges or [],
    }


def run_workflow_sync(graph_parsed, input_json=None, timeout=30):
    """Run _run_workflow synchronously (blocking), bypassing DB workflow/version lookup.

    Mocks all DB write operations so we can test DAG logic without needing
    a full workflow + version in the database.

    Returns:
        (execution_id, status_dict) from in-memory tracking.
    """
    execution_id = f"wfx-test-{int(time.time() * 1000)}"
    workflow_id = "wf-test01"

    # Register in-memory tracking (normally done by execute_workflow)
    with WorkflowExecutionService._lock:
        WorkflowExecutionService._executions[execution_id] = {
            "workflow_id": workflow_id,
            "status": "running",
            "trigger_type": "manual",
            "node_states": {},
            "_cancelled": False,
        }

    with (
        patch(
            "app.db.workflows.add_workflow_node_execution",
            return_value=1,
        ),
        patch(
            "app.db.workflows.update_workflow_node_execution",
        ),
        patch(
            "app.db.workflows.update_workflow_execution",
        ),
        patch(
            "app.db.workflows.get_workflow_node_executions",
            return_value=[],
        ),
    ):
        WorkflowExecutionService._run_workflow(
            execution_id=execution_id,
            workflow_id=workflow_id,
            graph_parsed=graph_parsed,
            input_json=input_json,
            trigger_type="manual",
            timeout_seconds=timeout,
        )

    with WorkflowExecutionService._lock:
        status = WorkflowExecutionService._executions.get(execution_id, {})
        result = dict(status)

    # Cleanup
    with WorkflowExecutionService._lock:
        WorkflowExecutionService._executions.pop(execution_id, None)

    return execution_id, result


# =============================================================================
# Graph Fixtures (original)
# =============================================================================


def _linear_3_graph():
    """A(trigger) -> B(transform, uppercase) -> C(command, echo test)."""
    nodes = [
        {"id": "A", "type": "trigger", "label": "Start", "config": {"data": {"msg": "hello"}}},
        {
            "id": "B",
            "type": "transform",
            "label": "Transform",
            "config": {"transform_type": "uppercase"},
        },
        {"id": "C", "type": "command", "label": "Echo", "config": {"command": "echo test"}},
    ]
    edges = [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}]
    return _make_graph(nodes, edges)


def _diamond_4_graph():
    """A(trigger) -> {B(transform), C(skill)} -> D(command)."""
    nodes = [
        {"id": "A", "type": "trigger", "label": "Start", "config": {}},
        {
            "id": "B",
            "type": "transform",
            "label": "Upper",
            "config": {"transform_type": "uppercase"},
        },
        {"id": "C", "type": "skill", "label": "Skill", "config": {"skill_name": "test-skill"}},
        {"id": "D", "type": "command", "label": "Echo", "config": {"command": "echo merged"}},
    ]
    edges = [
        {"source": "A", "target": "B"},
        {"source": "A", "target": "C"},
        {"source": "B", "target": "D"},
        {"source": "C", "target": "D"},
    ]
    return _make_graph(nodes, edges)


def _error_stop_graph():
    """A(trigger) -> B(command fails, error_mode=stop) -> C(transform)."""
    nodes = [
        {"id": "A", "type": "trigger", "label": "Start", "config": {}},
        {
            "id": "B",
            "type": "command",
            "label": "Fail",
            "config": {"command": "exit 1"},
            "error_mode": "stop",
        },
        {
            "id": "C",
            "type": "transform",
            "label": "After",
            "config": {"transform_type": "passthrough"},
        },
    ]
    edges = [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}]
    return _make_graph(nodes, edges)


def _error_continue_graph():
    """A(trigger) -> B(command fails, error_mode=continue) -> C(transform)."""
    nodes = [
        {"id": "A", "type": "trigger", "label": "Start", "config": {}},
        {
            "id": "B",
            "type": "command",
            "label": "Fail",
            "config": {"command": "exit 1"},
            "error_mode": "continue",
        },
        {
            "id": "C",
            "type": "transform",
            "label": "After",
            "config": {"transform_type": "passthrough"},
        },
    ]
    edges = [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}]
    return _make_graph(nodes, edges)


def _error_continue_with_error_graph():
    """A(trigger) -> B(command fails, error_mode=continue_with_error) -> C(transform)."""
    nodes = [
        {"id": "A", "type": "trigger", "label": "Start", "config": {}},
        {
            "id": "B",
            "type": "command",
            "label": "Fail",
            "config": {"command": "exit 1"},
            "error_mode": "continue_with_error",
        },
        {
            "id": "C",
            "type": "transform",
            "label": "After",
            "config": {"transform_type": "passthrough"},
        },
    ]
    edges = [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}]
    return _make_graph(nodes, edges)


def _timeout_graph():
    """A(trigger) -> B(script sleeps 10s), workflow timeout=1s."""
    nodes = [
        {"id": "A", "type": "trigger", "label": "Start", "config": {}},
        {
            "id": "B",
            "type": "script",
            "label": "Slow",
            "config": {"script": "import time; time.sleep(10)", "timeout": 60},
        },
    ]
    edges = [{"source": "A", "target": "B"}]
    return _make_graph(nodes, edges, settings={"timeout_seconds": 1})


def _retry_graph():
    """A(trigger) -> B(command fails, retry_max=2)."""
    nodes = [
        {"id": "A", "type": "trigger", "label": "Start", "config": {}},
        {
            "id": "B",
            "type": "command",
            "label": "Retry",
            "config": {"command": "exit 1"},
            "error_mode": "stop",
            "retry_max": 2,
            "retry_backoff_seconds": 0,
        },
    ]
    edges = [{"source": "A", "target": "B"}]
    return _make_graph(nodes, edges)


# =============================================================================
# Tests: Basic Workflow Execution (original)
# =============================================================================


class TestWorkflowExecution:
    def test_execute_linear_workflow(self, client):
        """Linear 3-node workflow runs to completion with correct node execution count."""
        wf_id = _create_test_workflow(client)
        _create_test_version(client, wf_id, _linear_3_graph())

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        assert resp.status_code == 202
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] == "completed"
        # All 3 nodes should have execution records
        assert len(body["node_executions"]) == 3

    def test_execute_returns_execution_id(self, client):
        """POST /run returns 202 with wfx-* execution ID."""
        wf_id = _create_test_workflow(client)
        _create_test_version(client, wf_id, _linear_3_graph())

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        assert resp.status_code == 202
        body = resp.get_json()
        assert body["execution_id"].startswith("wfx-")
        assert body["message"] == "Workflow execution started"

    def test_execute_nonexistent_workflow(self, client):
        """POST /run for unknown workflow returns 404."""
        resp = client.post("/admin/workflows/wf-doesntexist/run")
        assert resp.status_code == 404

    def test_execute_workflow_no_versions(self, client):
        """POST /run for workflow with no versions returns 400."""
        wf_id = _create_test_workflow(client)
        resp = client.post(f"/admin/workflows/{wf_id}/run")
        assert resp.status_code == 400
        assert "no versions" in resp.get_json()["error"].lower()


# =============================================================================
# Tests: Node Execution Order (original)
# =============================================================================


class TestNodeExecutionOrder:
    def test_topological_order_linear(self, client):
        """After executing LINEAR_3, node_executions show A before B before C."""
        wf_id = _create_test_workflow(client)
        _create_test_version(client, wf_id, _linear_3_graph())

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] == "completed"

        nodes = body["node_executions"]
        node_ids = [n["node_id"] for n in nodes]
        assert node_ids.index("A") < node_ids.index("B")
        assert node_ids.index("B") < node_ids.index("C")

    def test_topological_order_diamond(self, client):
        """After executing DIAMOND_4, A executes before B and C, D executes after both."""
        wf_id = _create_test_workflow(client)
        _create_test_version(client, wf_id, _diamond_4_graph())

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] == "completed"

        nodes = body["node_executions"]
        node_ids = [n["node_id"] for n in nodes]
        # A must be before B and C
        assert node_ids.index("A") < node_ids.index("B")
        assert node_ids.index("A") < node_ids.index("C")
        # D must be after B and C
        assert node_ids.index("D") > node_ids.index("B")
        assert node_ids.index("D") > node_ids.index("C")
        # All 4 nodes executed
        assert len(nodes) == 4


# =============================================================================
# Tests: Error Handling (original)
# =============================================================================


class TestErrorHandling:
    def test_error_stop_halts_workflow(self, client):
        """Error stop mode: B fails, C is skipped, workflow is failed."""
        wf_id = _create_test_workflow(client)
        _create_test_version(client, wf_id, _error_stop_graph())

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] == "failed"

        nodes = {n["node_id"]: n for n in body["node_executions"]}
        assert nodes["A"]["status"] == "completed"
        assert nodes["B"]["status"] == "failed"
        assert nodes["C"]["status"] == "skipped"

    def test_error_continue_skips_downstream(self, client):
        """Error continue mode: B fails, C is skipped, workflow completes."""
        wf_id = _create_test_workflow(client)
        _create_test_version(client, wf_id, _error_continue_graph())

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        # Workflow completes because error_mode is continue
        assert body["execution"]["status"] == "completed"

        nodes = {n["node_id"]: n for n in body["node_executions"]}
        assert nodes["A"]["status"] == "completed"
        assert nodes["B"]["status"] == "failed"
        # C is skipped because it depends on failed B
        assert nodes["C"]["status"] == "skipped"

    def test_error_continue_with_error_output(self, client):
        """Error continue_with_error mode: B fails, C receives error data, workflow completes."""
        wf_id = _create_test_workflow(client)
        _create_test_version(client, wf_id, _error_continue_with_error_graph())

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] == "completed"

        nodes = {n["node_id"]: n for n in body["node_executions"]}
        assert nodes["A"]["status"] == "completed"
        assert nodes["B"]["status"] == "failed"
        # C runs because continue_with_error passes error data downstream
        assert nodes["C"]["status"] == "completed"

        # C should have received error data as input
        c_input = json.loads(nodes["C"]["input_json"])
        assert c_input.get("content_type") == "error"
        assert "error" in (c_input.get("text") or "").lower()


# =============================================================================
# Tests: Retry (original)
# =============================================================================


class TestRetry:
    def test_retry_on_failure(self, client):
        """Failed node retries configured number of times then fails."""
        wf_id = _create_test_workflow(client)
        _create_test_version(client, wf_id, _retry_graph())

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] == "failed"

        nodes = {n["node_id"]: n for n in body["node_executions"]}
        assert nodes["B"]["status"] == "failed"
        # Error should mention attempts
        error_msg = nodes["B"].get("error", "")
        assert "3 attempts" in error_msg  # 1 original + 2 retries


# =============================================================================
# Tests: Timeout (original)
# =============================================================================


class TestTimeout:
    def test_workflow_timeout(self, client):
        """Workflow with 1s timeout prevents subsequent nodes from running."""
        wf_id = _create_test_workflow(client)
        # A(trigger) -> B(command sleeps 2s) -> C(command echo).
        timeout_graph = _make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "command",
                    "label": "Slow",
                    "config": {"command": "sleep 2", "timeout": 10},
                },
                {
                    "id": "C",
                    "type": "command",
                    "label": "After",
                    "config": {"command": "echo should_not_run"},
                },
            ],
            edges=[
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
            settings={"timeout_seconds": 1},
        )
        _create_test_version(client, wf_id, timeout_graph)

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] == "failed"
        assert "timed out" in (body["execution"].get("error") or "").lower()


# =============================================================================
# Tests: WorkflowMessage Routing (original)
# =============================================================================


class TestWorkflowMessage:
    def test_message_routing(self, client):
        """Data flows correctly between nodes via WorkflowMessage."""
        wf_id = _create_test_workflow(client)
        graph = _make_graph(
            nodes=[
                {
                    "id": "A",
                    "type": "trigger",
                    "label": "Start",
                    "config": {},
                },
                {
                    "id": "B",
                    "type": "transform",
                    "label": "Upper",
                    "config": {"transform_type": "uppercase"},
                },
            ],
            edges=[{"source": "A", "target": "B"}],
        )
        _create_test_version(client, wf_id, graph)

        resp = client.post(
            f"/admin/workflows/{wf_id}/run",
            json={"input_json": json.dumps("hello world")},
        )
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] == "completed"

        # Check B's output has uppercased text
        nodes = {n["node_id"]: n for n in body["node_executions"]}
        b_output = json.loads(nodes["B"]["output_json"])
        assert b_output["text"] == "HELLO WORLD"

    def test_command_node_captures_output(self, client):
        """Command node execution captures stdout in output."""
        wf_id = _create_test_workflow(client)
        graph = _make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "command",
                    "label": "Echo",
                    "config": {"command": "echo test_output"},
                },
            ],
            edges=[{"source": "A", "target": "B"}],
        )
        _create_test_version(client, wf_id, graph)

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] == "completed"

        nodes = {n["node_id"]: n for n in body["node_executions"]}
        b_output = json.loads(nodes["B"]["output_json"])
        assert "test_output" in b_output["stdout"]
        assert b_output["exit_code"] == 0

    def test_trigger_node_passes_config_data(self, client):
        """Trigger node with config data creates WorkflowMessage with that data."""
        wf_id = _create_test_workflow(client)
        graph = _make_graph(
            nodes=[
                {
                    "id": "A",
                    "type": "trigger",
                    "label": "Start",
                    "config": {"data": {"key": "value"}},
                },
                {
                    "id": "B",
                    "type": "transform",
                    "label": "Pass",
                    "config": {"transform_type": "extract_field", "field": "key"},
                },
            ],
            edges=[{"source": "A", "target": "B"}],
        )
        _create_test_version(client, wf_id, graph)

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] == "completed"

        nodes = {n["node_id"]: n for n in body["node_executions"]}
        b_output = json.loads(nodes["B"]["output_json"])
        assert b_output["data"]["value"] == "value"


# =============================================================================
# Tests: Cancel Execution (original)
# =============================================================================


class TestCancelExecution:
    def test_cancel_running_execution(self, client, monkeypatch):
        """Cancellation sets execution status to cancelled."""
        wf_id = _create_test_workflow(client)
        graph = _make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "command",
                    "label": "Fast",
                    "config": {"command": "echo step1"},
                },
                {
                    "id": "C",
                    "type": "command",
                    "label": "Fast2",
                    "config": {"command": "echo step2"},
                },
            ],
            edges=[
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        )
        _create_test_version(client, wf_id, graph)

        original_cmd = WorkflowExecutionService._execute_command_node.__func__
        call_count = {"n": 0}

        @classmethod
        def slow_command(cls, node_id, node_config, input_msg):
            call_count["n"] += 1
            if call_count["n"] == 1:
                result = original_cmd(cls, node_id, node_config, input_msg)
                time.sleep(0.5)
                return result
            return original_cmd(cls, node_id, node_config, input_msg)

        monkeypatch.setattr(WorkflowExecutionService, "_execute_command_node", slow_command)

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = resp.get_json()["execution_id"]

        time.sleep(0.3)
        cancelled = WorkflowExecutionService.cancel_execution(exec_id)
        assert cancelled is True

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] in ("cancelled", "completed")


# =============================================================================
# Tests: Node Types (original, updated for agent node changes)
# =============================================================================


class TestNodeTypes:
    def test_skill_node_stub(self, client):
        """Skill node returns stub execution message."""
        wf_id = _create_test_workflow(client)
        graph = _make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "skill",
                    "label": "Test Skill",
                    "config": {"skill_name": "my-skill"},
                },
            ],
            edges=[{"source": "A", "target": "B"}],
        )
        _create_test_version(client, wf_id, graph)

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] == "completed"

        nodes = {n["node_id"]: n for n in body["node_executions"]}
        b_output = json.loads(nodes["B"]["output_json"])
        assert "[skill:my-skill]" in b_output["text"]

    def test_agent_node_calls_orchestration(self, client):
        """Agent node calls OrchestrationService (not a stub) and returns dispatched result."""
        from app.services.orchestration_service import ExecutionResult, ExecutionStatus

        mock_result = ExecutionResult(
            status=ExecutionStatus.DISPATCHED,
            execution_id="exec-test-123",
        )

        wf_id = _create_test_workflow(client)
        graph = _make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "agent",
                    "label": "Test Agent",
                    "config": {"agent_id": "agent-123"},
                },
            ],
            edges=[{"source": "A", "target": "B"}],
        )
        _create_test_version(client, wf_id, graph)

        with patch("app.services.orchestration_service.OrchestrationService") as mock_orch:
            mock_orch.execute_with_fallback.return_value = mock_result

            resp = client.post(f"/admin/workflows/{wf_id}/run")
            exec_id = resp.get_json()["execution_id"]

            body = _wait_for_execution(client, exec_id, timeout=10)

        assert body["execution"]["status"] == "completed"
        nodes = {n["node_id"]: n for n in body["node_executions"]}
        b_output = json.loads(nodes["B"]["output_json"])
        assert b_output["data"]["execution_id"] == "exec-test-123"
        assert b_output["data"]["status"] == "dispatched"

    def test_conditional_node_has_text(self, client):
        """Conditional node evaluates has_text condition."""
        wf_id = _create_test_workflow(client)
        graph = _make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "conditional",
                    "label": "Check",
                    "config": {"condition": "has_text"},
                },
            ],
            edges=[{"source": "A", "target": "B"}],
        )
        _create_test_version(client, wf_id, graph)

        resp = client.post(
            f"/admin/workflows/{wf_id}/run",
            json={"input_json": json.dumps("some text")},
        )
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] == "completed"

        nodes = {n["node_id"]: n for n in body["node_executions"]}
        b_output = json.loads(nodes["B"]["output_json"])
        assert b_output["data"]["result"] is True
        assert b_output["data"]["branch"] == "true"

    def test_transform_json_parse(self, client):
        """Transform node parses JSON text into data."""
        wf_id = _create_test_workflow(client)
        graph = _make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "transform",
                    "label": "Parse",
                    "config": {"transform_type": "json_parse"},
                },
            ],
            edges=[{"source": "A", "target": "B"}],
        )
        _create_test_version(client, wf_id, graph)

        resp = client.post(
            f"/admin/workflows/{wf_id}/run",
            json={"input_json": json.dumps('{"foo": "bar"}')},
        )
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] == "completed"

        nodes = {n["node_id"]: n for n in body["node_executions"]}
        b_output = json.loads(nodes["B"]["output_json"])
        assert b_output["data"]["foo"] == "bar"


# =============================================================================
# Tests: Execution Status (original)
# =============================================================================


class TestExecutionStatus:
    def test_get_execution_status_in_memory(self, client):
        """get_execution_status returns in-memory status while running."""
        wf_id = _create_test_workflow(client)
        graph = _make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "command",
                    "label": "Echo",
                    "config": {"command": "echo hi"},
                },
            ],
            edges=[{"source": "A", "target": "B"}],
        )
        _create_test_version(client, wf_id, graph)

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = resp.get_json()["execution_id"]

        status = WorkflowExecutionService.get_execution_status(exec_id)
        assert status is not None
        assert status["execution_id"] == exec_id
        assert status["workflow_id"] == wf_id
        assert status["status"] in ("running", "completed")

    def test_get_execution_status_nonexistent(self, client):
        """get_execution_status returns None for unknown execution."""
        status = WorkflowExecutionService.get_execution_status("wfx-nonexistent")
        assert status is None


# #############################################################################
# PHASE 7 NEW TESTS
# #############################################################################


# =============================================================================
# Group 1: Safe Expression Evaluator (WF-02)
# =============================================================================


class TestExpressionEvaluator:
    """Tests for the AST-based safe expression evaluator."""

    def test_evaluate_condition_comparison_operators(self):
        """Test >, <, >=, <=, ==, != with numeric values."""
        ctx = {"x": 10, "y": 5}

        assert evaluate_condition("x > y", ctx) is True
        assert evaluate_condition("y > x", ctx) is False
        assert evaluate_condition("x < y", ctx) is False
        assert evaluate_condition("y < x", ctx) is True
        assert evaluate_condition("x >= 10", ctx) is True
        assert evaluate_condition("x <= 10", ctx) is True
        assert evaluate_condition("x == 10", ctx) is True
        assert evaluate_condition("x != 5", ctx) is True
        assert evaluate_condition("x != 10", ctx) is False

    def test_evaluate_condition_string_operations(self):
        """Test string equality and 'in' operator on lists."""
        ctx = {"name": "main", "labels": ["bug", "security", "urgent"]}

        assert evaluate_condition('name == "main"', ctx) is True
        assert evaluate_condition('name == "dev"', ctx) is False
        assert evaluate_condition('"security" in labels', ctx) is True
        assert evaluate_condition('"feature" in labels', ctx) is False

    def test_evaluate_condition_boolean_logic(self):
        """Test and, or, not combinators."""
        ctx = {"a": True, "b": False, "x": 10}

        assert evaluate_condition("a and not b", ctx) is True
        assert evaluate_condition("a and b", ctx) is False
        assert evaluate_condition("a or b", ctx) is True
        assert evaluate_condition("not a", ctx) is False
        assert evaluate_condition("x > 5 and x < 20", ctx) is True
        assert evaluate_condition("x > 5 or x < 3", ctx) is True

    def test_evaluate_condition_nested_access(self):
        """Test pr.branch, pr.labels dot-notation access."""
        ctx = {
            "pr": {
                "branch": "main",
                "labels": ["security", "critical"],
                "stats": {"lines_changed": 200},
            }
        }

        assert evaluate_condition('pr.branch == "main"', ctx) is True
        assert evaluate_condition('"security" in pr.labels', ctx) is True
        assert evaluate_condition("pr.stats.lines_changed > 100", ctx) is True

    def test_evaluate_condition_pr_attributes(self):
        """Test 5+ distinct PR attribute conditions per plan spec."""
        ctx = {
            "pr": {
                "lines_changed": 600,
                "branch": "main",
                "draft": False,
                "file_count": 15,
                "labels": ["security", "review-needed"],
            }
        }

        # 1. pr.lines_changed > 500
        assert evaluate_condition("pr.lines_changed > 500", ctx) is True

        # 2. pr.branch == "main"
        assert evaluate_condition('pr.branch == "main"', ctx) is True

        # 3. pr.draft == False
        assert evaluate_condition("pr.draft == False", ctx) is True

        # 4. pr.file_count >= 10 and pr.lines_changed < 1000
        assert evaluate_condition("pr.file_count >= 10 and pr.lines_changed < 1000", ctx) is True

        # 5. "security" in pr.labels
        assert evaluate_condition('"security" in pr.labels', ctx) is True

    def test_evaluate_condition_rejects_unsafe(self):
        """Verify that function calls, imports, etc. raise ValueError."""
        ctx = {"x": 1}

        # Function calls should be rejected
        with pytest.raises(ValueError):
            evaluate_condition("print('hello')", ctx)

        with pytest.raises(ValueError):
            evaluate_condition("__import__('os').system('ls')", ctx)

        with pytest.raises(ValueError):
            evaluate_condition("len([1,2,3])", ctx)

        with pytest.raises(ValueError):
            evaluate_condition("eval('1+1')", ctx)

    def test_evaluate_condition_invalid_expression(self):
        """Verify malformed expressions raise ValueError."""
        ctx = {"x": 1}

        with pytest.raises(ValueError):
            evaluate_condition("x >>>", ctx)

        with pytest.raises(ValueError):
            evaluate_condition("", ctx)

        with pytest.raises(ValueError):
            evaluate_condition("if x: pass", ctx)


# =============================================================================
# Group 2: Edge-Aware Conditional Branching (WF-05)
# =============================================================================


class TestConditionalBranching:
    """Tests for edge-aware conditional branching in DAG execution."""

    def test_conditional_branch_true_path(self):
        """Conditional true: command_a executes, command_b is skipped."""
        graph = make_test_graph(
            nodes=[
                {"id": "trigger", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "cond",
                    "type": "conditional",
                    "label": "Check",
                    "config": {"condition": "expression", "expression": "1 > 0"},
                },
                {
                    "id": "cmd_a",
                    "type": "command",
                    "label": "True Branch",
                    "config": {"command": "echo true_branch"},
                },
                {
                    "id": "cmd_b",
                    "type": "command",
                    "label": "False Branch",
                    "config": {"command": "echo false_branch"},
                },
            ],
            edges=[
                {"source": "trigger", "target": "cond"},
                {"source": "cond", "target": "cmd_a", "sourceHandle": "true"},
                {"source": "cond", "target": "cmd_b", "sourceHandle": "false"},
            ],
        )

        _, status = run_workflow_sync(graph)
        node_states = status.get("node_states", {})

        assert node_states.get("cmd_a") == "completed"
        assert node_states.get("cmd_b") == "skipped"
        assert status.get("status") == "completed"

    def test_conditional_branch_false_path(self):
        """Conditional false: false branch executes, true branch skipped."""
        graph = make_test_graph(
            nodes=[
                {"id": "trigger", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "cond",
                    "type": "conditional",
                    "label": "Check",
                    "config": {"condition": "expression", "expression": "1 < 0"},
                },
                {
                    "id": "cmd_true",
                    "type": "command",
                    "label": "True Branch",
                    "config": {"command": "echo true"},
                },
                {
                    "id": "cmd_false",
                    "type": "command",
                    "label": "False Branch",
                    "config": {"command": "echo false"},
                },
            ],
            edges=[
                {"source": "trigger", "target": "cond"},
                {"source": "cond", "target": "cmd_true", "sourceHandle": "true"},
                {"source": "cond", "target": "cmd_false", "sourceHandle": "false"},
            ],
        )

        _, status = run_workflow_sync(graph)
        node_states = status.get("node_states", {})

        assert node_states.get("cmd_true") == "skipped"
        assert node_states.get("cmd_false") == "completed"

    def test_conditional_branch_skip_downstream(self):
        """When false, both true_branch AND its downstream nodes must be skipped."""
        graph = make_test_graph(
            nodes=[
                {"id": "trigger", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "cond",
                    "type": "conditional",
                    "label": "Check",
                    "config": {"condition": "expression", "expression": "1 < 0"},
                },
                {
                    "id": "true_node",
                    "type": "command",
                    "label": "True Branch",
                    "config": {"command": "echo true"},
                },
                {
                    "id": "downstream_of_true",
                    "type": "command",
                    "label": "Downstream of True",
                    "config": {"command": "echo downstream"},
                },
                {
                    "id": "false_node",
                    "type": "command",
                    "label": "False Branch",
                    "config": {"command": "echo false"},
                },
            ],
            edges=[
                {"source": "trigger", "target": "cond"},
                {"source": "cond", "target": "true_node", "sourceHandle": "true"},
                {"source": "true_node", "target": "downstream_of_true"},
                {"source": "cond", "target": "false_node", "sourceHandle": "false"},
            ],
        )

        _, status = run_workflow_sync(graph)
        node_states = status.get("node_states", {})

        assert node_states.get("true_node") == "skipped"
        assert node_states.get("downstream_of_true") == "skipped"
        assert node_states.get("false_node") == "completed"

    def test_conditional_no_sourcehandle_passthrough(self):
        """Edges without sourceHandle should execute all successors (backward compat)."""
        graph = make_test_graph(
            nodes=[
                {"id": "trigger", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "cond",
                    "type": "conditional",
                    "label": "Check",
                    "config": {"condition": "expression", "expression": "1 > 0"},
                },
                {
                    "id": "next_a",
                    "type": "command",
                    "label": "A",
                    "config": {"command": "echo a"},
                },
                {
                    "id": "next_b",
                    "type": "command",
                    "label": "B",
                    "config": {"command": "echo b"},
                },
            ],
            edges=[
                {"source": "trigger", "target": "cond"},
                # No sourceHandle -- unconditional edges
                {"source": "cond", "target": "next_a"},
                {"source": "cond", "target": "next_b"},
            ],
        )

        _, status = run_workflow_sync(graph)
        node_states = status.get("node_states", {})

        # Both successors should execute since edges have no sourceHandle
        assert node_states.get("next_a") == "completed"
        assert node_states.get("next_b") == "completed"


# =============================================================================
# Group 3: Approval Gate (WF-03)
# =============================================================================


class TestApprovalGate:
    """Tests for approval gate node with approve/reject/timeout."""

    def test_approval_gate_approve(self, isolated_db):
        """Start workflow with approval gate; approve after delay; verify completion."""
        graph = make_test_graph(
            nodes=[
                {"id": "trigger", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "gate",
                    "type": "approval_gate",
                    "label": "Approve?",
                    "config": {"timeout": 10},
                },
                {
                    "id": "cmd",
                    "type": "command",
                    "label": "After Approval",
                    "config": {"command": "echo approved"},
                },
            ],
            edges=[
                {"source": "trigger", "target": "gate"},
                {"source": "gate", "target": "cmd"},
            ],
        )

        execution_id = f"wfx-approve-{int(time.time() * 1000)}"
        workflow_id = "wf-test01"

        with WorkflowExecutionService._lock:
            WorkflowExecutionService._executions[execution_id] = {
                "workflow_id": workflow_id,
                "status": "running",
                "trigger_type": "manual",
                "node_states": {},
                "_cancelled": False,
            }

        def delayed_approve():
            time.sleep(0.5)
            WorkflowExecutionService.approve_node(execution_id, "gate", "test-user")

        approve_thread = threading.Thread(target=delayed_approve, daemon=True)
        approve_thread.start()

        with (
            patch(
                "app.db.workflows.add_workflow_node_execution",
                return_value=1,
            ),
            patch(
                "app.db.workflows.update_workflow_node_execution",
            ),
            patch(
                "app.db.workflows.update_workflow_execution",
            ),
            patch(
                "app.db.workflows.get_workflow_node_executions",
                return_value=[],
            ),
        ):
            WorkflowExecutionService._run_workflow(
                execution_id=execution_id,
                workflow_id=workflow_id,
                graph_parsed=graph,
                input_json=None,
                trigger_type="manual",
                timeout_seconds=30,
            )

        with WorkflowExecutionService._lock:
            status = dict(WorkflowExecutionService._executions.get(execution_id, {}))

        node_states = status.get("node_states", {})
        assert node_states.get("gate") == "completed"
        assert node_states.get("cmd") == "completed"
        assert status.get("status") == "completed"

        approve_thread.join(timeout=2)
        with WorkflowExecutionService._lock:
            WorkflowExecutionService._executions.pop(execution_id, None)

    def test_approval_gate_reject(self, isolated_db):
        """Reject approval gate; verify downstream nodes not executed."""
        graph = make_test_graph(
            nodes=[
                {"id": "trigger", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "gate",
                    "type": "approval_gate",
                    "label": "Approve?",
                    "config": {"timeout": 10},
                },
                {
                    "id": "cmd",
                    "type": "command",
                    "label": "After Approval",
                    "config": {"command": "echo should_not_run"},
                },
            ],
            edges=[
                {"source": "trigger", "target": "gate"},
                {"source": "gate", "target": "cmd"},
            ],
        )

        execution_id = f"wfx-reject-{int(time.time() * 1000)}"
        workflow_id = "wf-test01"

        with WorkflowExecutionService._lock:
            WorkflowExecutionService._executions[execution_id] = {
                "workflow_id": workflow_id,
                "status": "running",
                "trigger_type": "manual",
                "node_states": {},
                "_cancelled": False,
            }

        def delayed_reject():
            time.sleep(0.5)
            WorkflowExecutionService.reject_node(execution_id, "gate", "test-user")

        reject_thread = threading.Thread(target=delayed_reject, daemon=True)
        reject_thread.start()

        with (
            patch(
                "app.db.workflows.add_workflow_node_execution",
                return_value=1,
            ),
            patch(
                "app.db.workflows.update_workflow_node_execution",
            ),
            patch(
                "app.db.workflows.update_workflow_execution",
            ),
            patch(
                "app.db.workflows.get_workflow_node_executions",
                return_value=[],
            ),
        ):
            WorkflowExecutionService._run_workflow(
                execution_id=execution_id,
                workflow_id=workflow_id,
                graph_parsed=graph,
                input_json=None,
                trigger_type="manual",
                timeout_seconds=30,
            )

        with WorkflowExecutionService._lock:
            status = dict(WorkflowExecutionService._executions.get(execution_id, {}))

        node_states = status.get("node_states", {})
        assert node_states.get("gate") == "failed"
        # cmd should either be skipped (if reached in topo order) or not present
        # (if execution broke out of the loop before reaching it)
        assert node_states.get("cmd") in ("skipped", None)
        assert status.get("status") == "failed"

        reject_thread.join(timeout=2)
        with WorkflowExecutionService._lock:
            WorkflowExecutionService._executions.pop(execution_id, None)

    def test_approval_gate_timeout(self, isolated_db):
        """Approval gate with 1s timeout; don't approve; verify timeout failure."""
        graph = make_test_graph(
            nodes=[
                {"id": "trigger", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "gate",
                    "type": "approval_gate",
                    "label": "Approve?",
                    "config": {"timeout": 1},
                },
                {
                    "id": "cmd",
                    "type": "command",
                    "label": "After Approval",
                    "config": {"command": "echo should_not_run"},
                },
            ],
            edges=[
                {"source": "trigger", "target": "gate"},
                {"source": "gate", "target": "cmd"},
            ],
        )

        execution_id = f"wfx-timeout-{int(time.time() * 1000)}"
        workflow_id = "wf-test01"

        with WorkflowExecutionService._lock:
            WorkflowExecutionService._executions[execution_id] = {
                "workflow_id": workflow_id,
                "status": "running",
                "trigger_type": "manual",
                "node_states": {},
                "_cancelled": False,
            }

        with (
            patch(
                "app.db.workflows.add_workflow_node_execution",
                return_value=1,
            ),
            patch(
                "app.db.workflows.update_workflow_node_execution",
            ),
            patch(
                "app.db.workflows.update_workflow_execution",
            ),
            patch(
                "app.db.workflows.get_workflow_node_executions",
                return_value=[],
            ),
        ):
            WorkflowExecutionService._run_workflow(
                execution_id=execution_id,
                workflow_id=workflow_id,
                graph_parsed=graph,
                input_json=None,
                trigger_type="manual",
                timeout_seconds=30,
            )

        with WorkflowExecutionService._lock:
            status = dict(WorkflowExecutionService._executions.get(execution_id, {}))

        node_states = status.get("node_states", {})
        assert node_states.get("gate") == "failed"
        assert status.get("status") == "failed"
        assert "timed out" in (status.get("error", "") or "").lower()

        with WorkflowExecutionService._lock:
            WorkflowExecutionService._executions.pop(execution_id, None)

    def test_approval_state_db_persistence(self, isolated_db):
        """Verify approval state is written to and readable from DB."""
        from app.db.workflows import (
            add_workflow_approval_state,
            get_workflow_approval_state,
            update_workflow_approval_state,
        )

        exec_id = "wfx-persist1"
        node_id = "gate-1"

        row_id = add_workflow_approval_state(exec_id, node_id, timeout_seconds=300)
        assert row_id is not None

        state = get_workflow_approval_state(exec_id, node_id)
        assert state is not None
        assert state["status"] == "pending"
        assert state["timeout_seconds"] == 300

        updated = update_workflow_approval_state(exec_id, node_id, "approved", "admin")
        assert updated is True

        state = get_workflow_approval_state(exec_id, node_id)
        assert state["status"] == "approved"
        assert state["resolved_by"] == "admin"


# =============================================================================
# Group 4: Agent Node Fallback (WF-04)
# =============================================================================


class TestAgentNodeFallback:
    """Tests for agent node OrchestrationService integration and routing rules."""

    def test_agent_node_calls_orchestration_service(self):
        """Verify _execute_agent_node calls OrchestrationService.execute_with_fallback."""
        from app.services.orchestration_service import ExecutionResult, ExecutionStatus

        mock_result = ExecutionResult(
            status=ExecutionStatus.DISPATCHED,
            execution_id="exec-123",
        )

        with patch("app.services.orchestration_service.OrchestrationService") as mock_orch:
            mock_orch.execute_with_fallback.return_value = mock_result

            input_msg = WorkflowMessage(text="test message")
            node_config = {"agent_id": "agent-test01"}

            output = WorkflowExecutionService._execute_agent_node("node1", node_config, input_msg)

            mock_orch.execute_with_fallback.assert_called_once()
            call_args = mock_orch.execute_with_fallback.call_args
            trigger_dict = call_args[0][0]
            assert trigger_dict["agent_id"] == "agent-test01"
            assert output.data["execution_id"] == "exec-123"
            assert output.data["status"] == "dispatched"

    def test_agent_node_chain_exhausted_raises(self):
        """Verify CHAIN_EXHAUSTED raises RuntimeError for retry/error_mode handling."""
        from app.services.orchestration_service import ExecutionResult, ExecutionStatus

        mock_result = ExecutionResult(
            status=ExecutionStatus.CHAIN_EXHAUSTED,
            detail="all backends rate-limited",
        )

        with patch("app.services.orchestration_service.OrchestrationService") as mock_orch:
            mock_orch.execute_with_fallback.return_value = mock_result

            input_msg = WorkflowMessage(text="test")
            node_config = {"agent_id": "agent-test01"}

            with pytest.raises(RuntimeError, match="exhausted"):
                WorkflowExecutionService._execute_agent_node("node1", node_config, input_msg)

    def test_agent_node_routing_rules_small_diff(self):
        """Small diff (below threshold) selects cheap tier."""
        from app.services.orchestration_service import ExecutionResult, ExecutionStatus

        mock_result = ExecutionResult(
            status=ExecutionStatus.DISPATCHED,
            execution_id="exec-routed",
        )

        with patch("app.services.orchestration_service.OrchestrationService") as mock_orch:
            mock_orch.execute_with_fallback.return_value = mock_result

            input_msg = WorkflowMessage(
                text="review this",
                data={"pr": {"lines_changed": 100}},
            )

            node_config = {
                "agent_id": "agent-review",
                "fallback_chain": [
                    {"backend_id": "b1", "account_id": "a1", "priority": 0, "tier": "cheap"},
                    {"backend_id": "b2", "account_id": "a2", "priority": 1, "tier": "expensive"},
                ],
                "routing_rules": {
                    "diff_size_threshold": 500,
                    "small_diff_tier": "cheap",
                    "large_diff_tier": "expensive",
                },
            }

            WorkflowExecutionService._execute_agent_node("node1", node_config, input_msg)

            call_args = mock_orch.execute_with_fallback.call_args
            trigger_dict = call_args[0][0]
            override = trigger_dict.get("_fallback_chain_override", [])
            assert len(override) == 1
            assert override[0]["tier"] == "cheap"

    def test_agent_node_routing_rules_large_diff(self):
        """Large diff (above threshold) selects expensive tier."""
        from app.services.orchestration_service import ExecutionResult, ExecutionStatus

        mock_result = ExecutionResult(
            status=ExecutionStatus.DISPATCHED,
            execution_id="exec-large",
        )

        with patch("app.services.orchestration_service.OrchestrationService") as mock_orch:
            mock_orch.execute_with_fallback.return_value = mock_result

            input_msg = WorkflowMessage(
                text="review this large PR",
                data={"pr": {"lines_changed": 1500}},
            )

            node_config = {
                "agent_id": "agent-review",
                "fallback_chain": [
                    {"backend_id": "b1", "account_id": "a1", "priority": 0, "tier": "cheap"},
                    {"backend_id": "b2", "account_id": "a2", "priority": 1, "tier": "expensive"},
                ],
                "routing_rules": {
                    "diff_size_threshold": 500,
                    "small_diff_tier": "cheap",
                    "large_diff_tier": "expensive",
                },
            }

            WorkflowExecutionService._execute_agent_node("node1", node_config, input_msg)

            call_args = mock_orch.execute_with_fallback.call_args
            trigger_dict = call_args[0][0]
            override = trigger_dict.get("_fallback_chain_override", [])
            assert len(override) == 1
            assert override[0]["tier"] == "expensive"


# =============================================================================
# Group 5: Per-Node Retry Policy (WF-06)
# =============================================================================


class TestRetryPolicy:
    """Tests for per-node retry policy with configurable backoff strategies."""

    def test_retry_exponential_backoff(self):
        """Node fails twice then succeeds with exponential backoff."""
        call_count = {"n": 0}
        sleep_delays = []

        def failing_command(node_id, node_config, input_msg):
            call_count["n"] += 1
            if call_count["n"] <= 2:
                raise RuntimeError("temporary failure")
            return WorkflowMessage(text="success")

        def mock_sleep(seconds):
            sleep_delays.append(seconds)

        graph = make_test_graph(
            nodes=[
                {"id": "trigger", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "cmd",
                    "type": "command",
                    "label": "Flaky Command",
                    "config": {"command": "echo test"},
                    "retry_max": 3,
                    "retry_backoff_seconds": 1,
                    "backoff_strategy": "exponential",
                },
            ],
            edges=[
                {"source": "trigger", "target": "cmd"},
            ],
        )

        with (
            patch.object(
                WorkflowExecutionService,
                "_execute_command_node",
                side_effect=failing_command,
            ),
            patch("time.sleep", side_effect=mock_sleep),
        ):
            _, status = run_workflow_sync(graph)

        assert status.get("status") == "completed"
        assert call_count["n"] == 3  # 2 failures + 1 success
        # Exponential: delay = 1 * 2^0 = 1, then 1 * 2^1 = 2
        assert sleep_delays == [1, 2]

    def test_retry_fixed_backoff(self):
        """Node fails twice then succeeds with fixed backoff (constant delay)."""
        call_count = {"n": 0}
        sleep_delays = []

        def failing_command(node_id, node_config, input_msg):
            call_count["n"] += 1
            if call_count["n"] <= 2:
                raise RuntimeError("temporary failure")
            return WorkflowMessage(text="success")

        def mock_sleep(seconds):
            sleep_delays.append(seconds)

        graph = make_test_graph(
            nodes=[
                {"id": "trigger", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "cmd",
                    "type": "command",
                    "label": "Flaky Command",
                    "config": {"command": "echo test"},
                    "retry_max": 3,
                    "retry_backoff_seconds": 2,
                    "backoff_strategy": "fixed",
                },
            ],
            edges=[
                {"source": "trigger", "target": "cmd"},
            ],
        )

        with (
            patch.object(
                WorkflowExecutionService,
                "_execute_command_node",
                side_effect=failing_command,
            ),
            patch("time.sleep", side_effect=mock_sleep),
        ):
            _, status = run_workflow_sync(graph)

        assert status.get("status") == "completed"
        assert call_count["n"] == 3
        # Fixed: delay is always 2
        assert sleep_delays == [2, 2]

    def test_retry_linear_backoff(self):
        """Node fails twice then succeeds with linear backoff."""
        call_count = {"n": 0}
        sleep_delays = []

        def failing_command(node_id, node_config, input_msg):
            call_count["n"] += 1
            if call_count["n"] <= 2:
                raise RuntimeError("temporary failure")
            return WorkflowMessage(text="success")

        def mock_sleep(seconds):
            sleep_delays.append(seconds)

        graph = make_test_graph(
            nodes=[
                {"id": "trigger", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "cmd",
                    "type": "command",
                    "label": "Flaky Command",
                    "config": {"command": "echo test"},
                    "retry_max": 3,
                    "retry_backoff_seconds": 1,
                    "backoff_strategy": "linear",
                },
            ],
            edges=[
                {"source": "trigger", "target": "cmd"},
            ],
        )

        with (
            patch.object(
                WorkflowExecutionService,
                "_execute_command_node",
                side_effect=failing_command,
            ),
            patch("time.sleep", side_effect=mock_sleep),
        ):
            _, status = run_workflow_sync(graph)

        assert status.get("status") == "completed"
        assert call_count["n"] == 3
        # Linear: delay = base * attempts -> 1*1=1, 1*2=2
        assert sleep_delays == [1, 2]

    def test_retry_respects_max_attempts(self):
        """Node always fails: verify exactly max_attempts+1 attempts, then failure."""
        call_count = {"n": 0}

        def always_fail(node_id, node_config, input_msg):
            call_count["n"] += 1
            raise RuntimeError("permanent failure")

        graph = make_test_graph(
            nodes=[
                {"id": "trigger", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "cmd",
                    "type": "command",
                    "label": "Always Fails",
                    "config": {"command": "echo test"},
                    "retry_max": 2,
                    "retry_backoff_seconds": 0,
                    "backoff_strategy": "fixed",
                },
            ],
            edges=[
                {"source": "trigger", "target": "cmd"},
            ],
        )

        with (
            patch.object(
                WorkflowExecutionService,
                "_execute_command_node",
                side_effect=always_fail,
            ),
            patch("time.sleep"),
        ):
            _, status = run_workflow_sync(graph)

        assert status.get("status") == "failed"
        # retry_max=2 means 1 initial + 2 retries = 3 total
        assert call_count["n"] == 3

    def test_retry_does_not_restart_dag(self):
        """Retrying a mid-DAG node does NOT re-execute earlier nodes."""
        trigger_count = {"n": 0}
        cmd_count = {"n": 0}
        original_trigger = WorkflowExecutionService._execute_trigger_node.__func__

        def counting_trigger(node_id, node_config, input_msg):
            trigger_count["n"] += 1
            return original_trigger(WorkflowExecutionService, node_id, node_config, input_msg)

        def failing_then_success(node_id, node_config, input_msg):
            cmd_count["n"] += 1
            if cmd_count["n"] <= 1:
                raise RuntimeError("first attempt fails")
            return WorkflowMessage(text="success")

        graph = make_test_graph(
            nodes=[
                {"id": "trigger", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "cmd",
                    "type": "command",
                    "label": "Retried Command",
                    "config": {"command": "echo test"},
                    "retry_max": 2,
                    "retry_backoff_seconds": 0,
                    "backoff_strategy": "fixed",
                },
            ],
            edges=[
                {"source": "trigger", "target": "cmd"},
            ],
        )

        with (
            patch.object(
                WorkflowExecutionService,
                "_execute_trigger_node",
                side_effect=counting_trigger,
            ),
            patch.object(
                WorkflowExecutionService,
                "_execute_command_node",
                side_effect=failing_then_success,
            ),
            patch("time.sleep"),
        ):
            _, status = run_workflow_sync(graph)

        assert status.get("status") == "completed"
        assert trigger_count["n"] == 1
        assert cmd_count["n"] == 2


# =============================================================================
# Group 6: Model Validation (supplementary)
# =============================================================================


class TestWorkflowModels:
    """Tests for new Pydantic models added in Phase 7."""

    def test_fallback_chain_entry(self):
        """FallbackChainEntry model validates correctly."""
        entry = FallbackChainEntry(backend_id="b1", account_id="a1", priority=1, tier="cheap")
        assert entry.tier == "cheap"
        assert entry.priority == 1

    def test_routing_rules_defaults(self):
        """RoutingRules model has correct defaults."""
        rules = RoutingRules()
        assert rules.diff_size_threshold == 500
        assert rules.small_diff_tier == "cheap"
        assert rules.large_diff_tier == "expensive"

    def test_agent_node_config(self):
        """AgentNodeConfig model validates with all fields."""
        config = AgentNodeConfig(
            agent_id="agent-test",
            trigger_id="trig-123",
            fallback_chain=[
                FallbackChainEntry(backend_id="b1", account_id="a1"),
            ],
            routing_rules=RoutingRules(diff_size_threshold=1000),
        )
        assert config.agent_id == "agent-test"
        assert len(config.fallback_chain) == 1
        assert config.routing_rules.diff_size_threshold == 1000

    def test_workflow_node_backoff_strategy(self):
        """WorkflowNode accepts backoff_strategy field."""
        for strategy in ["fixed", "linear", "exponential"]:
            node = WorkflowNode(
                id="n1",
                type="command",
                label="Test",
                backoff_strategy=strategy,
            )
            assert node.backoff_strategy == strategy

    def test_workflow_node_backoff_strategy_default(self):
        """WorkflowNode defaults to exponential backoff."""
        node = WorkflowNode(id="n1", type="command", label="Test")
        assert node.backoff_strategy == "exponential"
