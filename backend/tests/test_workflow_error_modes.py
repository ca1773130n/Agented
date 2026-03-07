"""Targeted tests for workflow node error modes — continue_on_error, stop_on_error,
retry logic, DAG failure propagation, and error data flow through complex graphs.

Complements test_workflow_execution.py by focusing on edge cases and complex DAG
topologies where error handling behavior is nuanced.
"""

import time
from unittest.mock import patch

import pytest

from app.models.workflow import WorkflowMessage
from app.services.workflow_execution_service import WorkflowExecutionService


# =============================================================================
# Helpers (mirrors patterns from test_workflow_execution.py)
# =============================================================================


def make_graph(nodes, edges=None, settings=None):
    """Build a graph_parsed dict for _run_workflow."""
    graph = {"nodes": nodes, "edges": edges or []}
    if settings:
        graph["settings"] = settings
    return graph


def run_sync(graph, input_json=None, timeout=30):
    """Run _run_workflow synchronously with all DB ops mocked.

    Returns (execution_id, status_dict) from in-memory tracking.
    """
    execution_id = f"wfx-err-{int(time.time() * 1000)}"
    workflow_id = "wf-errtest"

    with WorkflowExecutionService._lock:
        WorkflowExecutionService._executions[execution_id] = {
            "workflow_id": workflow_id,
            "status": "running",
            "trigger_type": "manual",
            "node_states": {},
            "_cancelled": False,
        }

    with (
        patch("app.db.workflows.add_workflow_node_execution", return_value=1),
        patch("app.db.workflows.update_workflow_node_execution"),
        patch("app.db.workflows.update_workflow_execution"),
        patch("app.db.workflows.get_workflow_node_executions", return_value=[]),
    ):
        WorkflowExecutionService._run_workflow(
            execution_id=execution_id,
            workflow_id=workflow_id,
            graph_parsed=graph,
            input_json=input_json,
            trigger_type="manual",
            timeout_seconds=timeout,
        )

    with WorkflowExecutionService._lock:
        status = dict(WorkflowExecutionService._executions.get(execution_id, {}))

    with WorkflowExecutionService._lock:
        WorkflowExecutionService._executions.pop(execution_id, None)

    return execution_id, status


def _always_fail(node_id, node_config, input_msg):
    """Node handler that always raises."""
    raise RuntimeError(f"node {node_id} exploded")


def _succeed(node_id, node_config, input_msg):
    """Node handler that always succeeds."""
    return WorkflowMessage(text=f"ok from {node_id}")


# =============================================================================
# Tests: stop_on_error mode
# =============================================================================


class TestStopOnError:
    """Node failure with error_mode=stop should halt the workflow and skip downstream."""

    def test_stop_mode_fails_workflow(self):
        """A failing node with stop mode sets workflow status to failed."""
        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "command",
                    "label": "Fail",
                    "config": {"command": "x"},
                    "error_mode": "stop",
                },
            ],
            edges=[{"source": "A", "target": "B"}],
        )

        with patch.object(
            WorkflowExecutionService, "_execute_command_node", side_effect=_always_fail
        ):
            _, status = run_sync(graph)

        assert status["status"] == "failed"
        assert "B" in status.get("error", "")

    def test_stop_mode_skips_all_downstream(self):
        """With stop mode, all nodes after the failing node are skipped.

        Note: when stop mode breaks out of the main loop, downstream nodes are
        added to the skipped_nodes set for DB recording but _update_node_state
        is not called for nodes that were never visited in the loop. We verify
        the workflow failed and that downstream nodes were NOT executed (i.e.
        they do not appear as 'completed' or 'running' in node_states).
        """
        # A -> B(fail,stop) -> C -> D
        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "command",
                    "label": "Fail",
                    "config": {"command": "x"},
                    "error_mode": "stop",
                },
                {"id": "C", "type": "transform", "label": "Mid", "config": {}},
                {"id": "D", "type": "transform", "label": "End", "config": {}},
            ],
            edges=[
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
                {"source": "C", "target": "D"},
            ],
        )

        with patch.object(
            WorkflowExecutionService, "_execute_command_node", side_effect=_always_fail
        ):
            _, status = run_sync(graph)

        assert status["status"] == "failed"
        assert status["node_states"]["A"] == "completed"
        assert status["node_states"]["B"] == "failed"
        # C and D were never visited in the loop (break after B), so they
        # won't have in-memory node_states entries. Verify they did NOT run.
        assert status["node_states"].get("C") != "completed"
        assert status["node_states"].get("D") != "completed"

    def test_stop_mode_in_diamond_skips_merge_node(self):
        """In a diamond DAG, stop on one branch halts workflow; merge node does not run."""
        #   A
        #  / \
        # B   C(fail,stop)
        #  \ /
        #   D
        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {"id": "B", "type": "transform", "label": "Left", "config": {}},
                {
                    "id": "C",
                    "type": "command",
                    "label": "Right Fail",
                    "config": {"command": "x"},
                    "error_mode": "stop",
                },
                {"id": "D", "type": "transform", "label": "Merge", "config": {}},
            ],
            edges=[
                {"source": "A", "target": "B"},
                {"source": "A", "target": "C"},
                {"source": "B", "target": "D"},
                {"source": "C", "target": "D"},
            ],
        )

        with patch.object(
            WorkflowExecutionService, "_execute_command_node", side_effect=_always_fail
        ):
            _, status = run_sync(graph)

        assert status["status"] == "failed"
        # D must not have completed because C (a predecessor) failed with stop mode
        assert status["node_states"].get("D") != "completed"


# =============================================================================
# Tests: continue_on_error mode
# =============================================================================


class TestContinueOnError:
    """Node failure with error_mode=continue should skip dependents but not halt."""

    def test_continue_mode_completes_workflow(self):
        """Workflow completes even when a node fails with continue mode."""
        # A -> B(fail,continue) -> C (skipped)
        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "command",
                    "label": "Fail",
                    "config": {"command": "x"},
                    "error_mode": "continue",
                },
                {"id": "C", "type": "transform", "label": "After", "config": {}},
            ],
            edges=[
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        )

        with patch.object(
            WorkflowExecutionService, "_execute_command_node", side_effect=_always_fail
        ):
            _, status = run_sync(graph)

        assert status["status"] == "completed"
        assert status["node_states"]["B"] == "failed"
        assert status["node_states"]["C"] == "skipped"

    def test_continue_mode_parallel_branch_succeeds(self):
        """In a diamond, continue mode on one branch lets the other branch succeed."""
        #   A
        #  / \
        # B   C(fail,continue)
        #  |
        #  D
        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {"id": "B", "type": "transform", "label": "Left OK", "config": {}},
                {
                    "id": "C",
                    "type": "command",
                    "label": "Right Fail",
                    "config": {"command": "x"},
                    "error_mode": "continue",
                },
                {"id": "D", "type": "transform", "label": "After B", "config": {}},
            ],
            edges=[
                {"source": "A", "target": "B"},
                {"source": "A", "target": "C"},
                {"source": "B", "target": "D"},
            ],
        )

        with patch.object(
            WorkflowExecutionService, "_execute_command_node", side_effect=_always_fail
        ):
            _, status = run_sync(graph)

        assert status["status"] == "completed"
        assert status["node_states"]["B"] == "completed"
        assert status["node_states"]["C"] == "failed"
        # D only depends on B (which succeeded), so it should complete
        assert status["node_states"]["D"] == "completed"


# =============================================================================
# Tests: continue_with_error mode
# =============================================================================


class TestContinueWithError:
    """Node failure with continue_with_error passes error data downstream."""

    def test_continue_with_error_passes_error_downstream(self):
        """Failed node's error message flows to its successor as input."""
        received_inputs = {}

        original_transform = WorkflowExecutionService._execute_transform_node.__func__

        def capturing_transform(node_id, node_config, input_msg):
            received_inputs[node_id] = input_msg
            return original_transform(WorkflowExecutionService, node_id, node_config, input_msg)

        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "command",
                    "label": "Fail",
                    "config": {"command": "x"},
                    "error_mode": "continue_with_error",
                },
                {
                    "id": "C",
                    "type": "transform",
                    "label": "Receiver",
                    "config": {"transform_type": "passthrough"},
                },
            ],
            edges=[
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        )

        with (
            patch.object(
                WorkflowExecutionService, "_execute_command_node", side_effect=_always_fail
            ),
            patch.object(
                WorkflowExecutionService,
                "_execute_transform_node",
                side_effect=capturing_transform,
            ),
        ):
            _, status = run_sync(graph)

        assert status["status"] == "completed"
        assert status["node_states"]["B"] == "failed"
        assert status["node_states"]["C"] == "completed"
        # C should have received an error-typed message
        c_input = received_inputs.get("C")
        assert c_input is not None
        assert c_input.content_type == "error"
        assert "error" in (c_input.text or "").lower()

    def test_continue_with_error_preserves_error_metadata(self):
        """Error output includes node_id and attempt count in data."""
        captured_outputs = {}

        def capture_transform(node_id, node_config, input_msg):
            captured_outputs[node_id] = input_msg
            return WorkflowMessage(text="handled")

        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "command",
                    "label": "Fail",
                    "config": {"command": "x"},
                    "error_mode": "continue_with_error",
                    "retry_max": 1,
                    "retry_backoff_seconds": 0,
                },
                {
                    "id": "C",
                    "type": "transform",
                    "label": "Check",
                    "config": {},
                },
            ],
            edges=[
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        )

        with (
            patch.object(
                WorkflowExecutionService, "_execute_command_node", side_effect=_always_fail
            ),
            patch.object(
                WorkflowExecutionService,
                "_execute_transform_node",
                side_effect=capture_transform,
            ),
            patch("time.sleep"),
        ):
            _, status = run_sync(graph)

        assert status["status"] == "completed"
        c_input = captured_outputs.get("C")
        assert c_input is not None
        assert c_input.data["node_id"] == "B"
        assert c_input.data["attempts"] == 2  # 1 initial + 1 retry


# =============================================================================
# Tests: Retry behavior
# =============================================================================


class TestRetryBehavior:
    """Retry logic: attempt counting, success after retries, interaction with error modes."""

    def test_retry_succeeds_on_last_attempt(self):
        """Node fails retry_max times then succeeds on the final attempt."""
        call_count = {"n": 0}

        def fail_then_succeed(node_id, node_config, input_msg):
            call_count["n"] += 1
            if call_count["n"] <= 3:  # fail first 3 attempts
                raise RuntimeError("not yet")
            return WorkflowMessage(text="finally")

        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "command",
                    "label": "Flaky",
                    "config": {"command": "x"},
                    "retry_max": 3,
                    "retry_backoff_seconds": 0,
                    "backoff_strategy": "fixed",
                },
            ],
            edges=[{"source": "A", "target": "B"}],
        )

        with (
            patch.object(
                WorkflowExecutionService,
                "_execute_command_node",
                side_effect=fail_then_succeed,
            ),
            patch("time.sleep"),
        ):
            _, status = run_sync(graph)

        assert status["status"] == "completed"
        assert call_count["n"] == 4  # 1 initial + 3 retries

    def test_retry_exhausted_then_continue(self):
        """Node exhausts retries with continue mode: workflow completes, downstream skipped."""
        call_count = {"n": 0}

        def always_fail(node_id, node_config, input_msg):
            call_count["n"] += 1
            raise RuntimeError("permanent")

        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "command",
                    "label": "Fail",
                    "config": {"command": "x"},
                    "error_mode": "continue",
                    "retry_max": 2,
                    "retry_backoff_seconds": 0,
                },
                {"id": "C", "type": "transform", "label": "After", "config": {}},
            ],
            edges=[
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
            ],
        )

        with (
            patch.object(
                WorkflowExecutionService, "_execute_command_node", side_effect=always_fail
            ),
            patch("time.sleep"),
        ):
            _, status = run_sync(graph)

        assert status["status"] == "completed"
        assert call_count["n"] == 3  # 1 + 2 retries
        assert status["node_states"]["B"] == "failed"
        assert status["node_states"]["C"] == "skipped"

    def test_no_retry_when_retry_max_zero(self):
        """With retry_max=0, the node is attempted exactly once."""
        call_count = {"n": 0}

        def count_and_fail(node_id, node_config, input_msg):
            call_count["n"] += 1
            raise RuntimeError("once")

        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "command",
                    "label": "NoRetry",
                    "config": {"command": "x"},
                    "error_mode": "stop",
                    "retry_max": 0,
                },
            ],
            edges=[{"source": "A", "target": "B"}],
        )

        with patch.object(
            WorkflowExecutionService, "_execute_command_node", side_effect=count_and_fail
        ):
            _, status = run_sync(graph)

        assert status["status"] == "failed"
        assert call_count["n"] == 1


# =============================================================================
# Tests: DAG failure propagation
# =============================================================================


class TestDAGFailurePropagation:
    """Complex DAG topologies with intermediate node failures."""

    def test_deep_chain_stop_skips_all_descendants(self):
        """In A->B->C->D->E, B fails with stop: C, D, E never execute."""
        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "command",
                    "label": "Fail",
                    "config": {"command": "x"},
                    "error_mode": "stop",
                },
                {"id": "C", "type": "transform", "label": "C", "config": {}},
                {"id": "D", "type": "transform", "label": "D", "config": {}},
                {"id": "E", "type": "transform", "label": "E", "config": {}},
            ],
            edges=[
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
                {"source": "C", "target": "D"},
                {"source": "D", "target": "E"},
            ],
        )

        with patch.object(
            WorkflowExecutionService, "_execute_command_node", side_effect=_always_fail
        ):
            _, status = run_sync(graph)

        assert status["status"] == "failed"
        # After stop-break, downstream nodes are not visited in the loop,
        # so they won't appear as completed in node_states.
        for nid in ("C", "D", "E"):
            assert status["node_states"].get(nid) != "completed"

    def test_diamond_continue_one_branch_fails(self):
        """Diamond: one branch fails (continue), merge node is skipped since it depends on failed branch."""
        #    A
        #   / \
        #  B   C(fail,continue)
        #   \ /
        #    D
        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {"id": "B", "type": "transform", "label": "OK", "config": {}},
                {
                    "id": "C",
                    "type": "command",
                    "label": "Fail",
                    "config": {"command": "x"},
                    "error_mode": "continue",
                },
                {"id": "D", "type": "transform", "label": "Merge", "config": {}},
            ],
            edges=[
                {"source": "A", "target": "B"},
                {"source": "A", "target": "C"},
                {"source": "B", "target": "D"},
                {"source": "C", "target": "D"},
            ],
        )

        with patch.object(
            WorkflowExecutionService, "_execute_command_node", side_effect=_always_fail
        ):
            _, status = run_sync(graph)

        # Workflow completes (continue mode)
        assert status["status"] == "completed"
        assert status["node_states"]["C"] == "failed"
        # D is downstream of C, so it gets skipped
        assert status["node_states"]["D"] == "skipped"

    def test_fan_out_one_branch_fails_others_complete(self):
        """Fan-out: A -> {B, C(fail,continue), D}. B and D complete, C fails."""
        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {"id": "B", "type": "transform", "label": "B", "config": {}},
                {
                    "id": "C",
                    "type": "command",
                    "label": "Fail",
                    "config": {"command": "x"},
                    "error_mode": "continue",
                },
                {"id": "D", "type": "transform", "label": "D", "config": {}},
            ],
            edges=[
                {"source": "A", "target": "B"},
                {"source": "A", "target": "C"},
                {"source": "A", "target": "D"},
            ],
        )

        with patch.object(
            WorkflowExecutionService, "_execute_command_node", side_effect=_always_fail
        ):
            _, status = run_sync(graph)

        assert status["status"] == "completed"
        assert status["node_states"]["B"] == "completed"
        assert status["node_states"]["C"] == "failed"
        assert status["node_states"]["D"] == "completed"

    def test_continue_with_error_through_chain(self):
        """A -> B(fail, continue_with_error) -> C -> D: error data flows through the chain."""
        received = {}

        original_transform = WorkflowExecutionService._execute_transform_node.__func__

        def tracking_transform(node_id, node_config, input_msg):
            received[node_id] = input_msg
            return original_transform(WorkflowExecutionService, node_id, node_config, input_msg)

        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "B",
                    "type": "command",
                    "label": "Fail",
                    "config": {"command": "x"},
                    "error_mode": "continue_with_error",
                },
                {
                    "id": "C",
                    "type": "transform",
                    "label": "Mid",
                    "config": {"transform_type": "passthrough"},
                },
                {
                    "id": "D",
                    "type": "transform",
                    "label": "End",
                    "config": {"transform_type": "passthrough"},
                },
            ],
            edges=[
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"},
                {"source": "C", "target": "D"},
            ],
        )

        with (
            patch.object(
                WorkflowExecutionService, "_execute_command_node", side_effect=_always_fail
            ),
            patch.object(
                WorkflowExecutionService,
                "_execute_transform_node",
                side_effect=tracking_transform,
            ),
        ):
            _, status = run_sync(graph)

        assert status["status"] == "completed"
        assert status["node_states"]["C"] == "completed"
        assert status["node_states"]["D"] == "completed"
        # C received the error message from B
        assert received["C"].content_type == "error"

    def test_workflow_error_message_includes_node_id(self):
        """Workflow-level error message identifies the failing node."""
        graph = make_graph(
            nodes=[
                {"id": "A", "type": "trigger", "label": "Start", "config": {}},
                {
                    "id": "problematic_node",
                    "type": "command",
                    "label": "Fail",
                    "config": {"command": "x"},
                    "error_mode": "stop",
                },
            ],
            edges=[{"source": "A", "target": "problematic_node"}],
        )

        with patch.object(
            WorkflowExecutionService, "_execute_command_node", side_effect=_always_fail
        ):
            _, status = run_sync(graph)

        assert status["status"] == "failed"
        assert "problematic_node" in status["error"]
