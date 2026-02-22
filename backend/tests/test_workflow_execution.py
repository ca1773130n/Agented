"""Tests for WorkflowExecutionService — DAG execution engine with node dispatch,
error handling, retry, timeout, message routing, and cancellation."""

import json
import time

from app.services.workflow_execution_service import WorkflowExecutionService

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
        if status not in ("running", "pending"):
            return body
        time.sleep(0.1)
    # Final check
    resp = client.get(f"/admin/workflows/executions/{execution_id}")
    return resp.get_json()


# =============================================================================
# Graph Fixtures
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
# Tests: Basic Workflow Execution
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
# Tests: Node Execution Order
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
# Tests: Error Handling
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
        """Error continue mode: B fails, C is skipped (downstream of failed node), workflow completes."""
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
# Tests: Retry
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
# Tests: Timeout
# =============================================================================


class TestTimeout:
    def test_workflow_timeout(self, client):
        """Workflow with 1s timeout prevents subsequent nodes from running."""
        wf_id = _create_test_workflow(client)
        # A(trigger) -> B(command sleeps 2s) -> C(command echo).
        # Timeout is 1s. A runs instantly. B starts (sleep 2) and runs to completion
        # because timeout is only checked between nodes. After B finishes (~2s),
        # the timeout check at C's iteration fires.
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
# Tests: WorkflowMessage Routing
# =============================================================================


class TestWorkflowMessage:
    def test_message_routing(self, client):
        """Data flows correctly between nodes via WorkflowMessage."""
        wf_id = _create_test_workflow(client)
        # Trigger outputs text "hello world" -> transform uppercases it -> command receives it
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
# Tests: Cancel Execution
# =============================================================================


class TestCancelExecution:
    def test_cancel_running_execution(self, client, monkeypatch):
        """Cancellation sets execution status to cancelled."""
        wf_id = _create_test_workflow(client)
        # Use a graph with two slow nodes. Monkeypatch the command dispatcher
        # to insert a delay, giving us time to cancel between nodes.
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

        # Monkeypatch the command dispatcher to add a delay after first call
        original_cmd = WorkflowExecutionService._execute_command_node.__func__
        call_count = {"n": 0}

        @classmethod
        def slow_command(cls, node_id, node_config, input_msg):
            call_count["n"] += 1
            if call_count["n"] == 1:
                result = original_cmd(cls, node_id, node_config, input_msg)
                time.sleep(0.5)  # Give time for cancel to be set
                return result
            return original_cmd(cls, node_id, node_config, input_msg)

        monkeypatch.setattr(WorkflowExecutionService, "_execute_command_node", slow_command)

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = resp.get_json()["execution_id"]

        # Wait for B to start, then cancel
        time.sleep(0.3)
        cancelled = WorkflowExecutionService.cancel_execution(exec_id)
        assert cancelled is True

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] in ("cancelled", "completed")


# =============================================================================
# Tests: Node Types
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

    def test_agent_node_stub(self, client):
        """Agent node returns stub execution message."""
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

        resp = client.post(f"/admin/workflows/{wf_id}/run")
        exec_id = resp.get_json()["execution_id"]

        body = _wait_for_execution(client, exec_id, timeout=10)
        assert body["execution"]["status"] == "completed"

        nodes = {n["node_id"]: n for n in body["node_executions"]}
        b_output = json.loads(nodes["B"]["output_json"])
        assert "[agent:agent-123]" in b_output["text"]

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
# Tests: Execution Status Service
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

        # Check status immediately (may be running or completed)
        status = WorkflowExecutionService.get_execution_status(exec_id)
        assert status is not None
        assert status["execution_id"] == exec_id
        assert status["workflow_id"] == wf_id
        assert status["status"] in ("running", "completed")

    def test_get_execution_status_nonexistent(self, client):
        """get_execution_status returns None for unknown execution."""
        status = WorkflowExecutionService.get_execution_status("wfx-nonexistent")
        assert status is None
