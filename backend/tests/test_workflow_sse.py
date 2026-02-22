"""Tests for workflow SSE streaming and cancel endpoints."""

import json
from unittest.mock import patch


def _parse_sse_events(data):
    """Parse SSE event stream data into a list of JSON events."""
    events = []
    for line in data.decode("utf-8").split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


class TestCancelEndpoint:
    def test_cancel_running_execution(self, client):
        """POST cancel returns 200 when execution is running."""
        with patch(
            "app.services.workflow_execution_service.WorkflowExecutionService.cancel_execution",
            return_value=True,
        ):
            resp = client.post("/admin/workflows/wf-abc123/executions/wfx-test1234/cancel")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["message"] == "Execution cancelled"

    def test_cancel_nonexistent_execution(self, client):
        """POST cancel returns 404 when execution not found or not running."""
        with patch(
            "app.services.workflow_execution_service.WorkflowExecutionService.cancel_execution",
            return_value=False,
        ):
            resp = client.post("/admin/workflows/wf-abc123/executions/wfx-notfound/cancel")
            assert resp.status_code == 404
            body = resp.get_json()
            assert "not found" in body["error"].lower() or "not running" in body["error"].lower()

    def test_cancel_endpoint_method(self, client):
        """GET to cancel endpoint returns 405 (only POST allowed)."""
        resp = client.get("/admin/workflows/wf-abc123/executions/wfx-test1234/cancel")
        assert resp.status_code == 405


class TestStreamEndpoint:
    def test_stream_execution_not_found(self, client):
        """GET stream returns error event when execution not found."""
        with patch(
            "app.services.workflow_execution_service.WorkflowExecutionService.get_execution_status",
            return_value=None,
        ):
            resp = client.get("/admin/workflows/wf-abc123/executions/wfx-notfound/stream")
            assert resp.status_code == 200
            assert resp.content_type == "text/event-stream; charset=utf-8"

            events = _parse_sse_events(resp.data)
            assert len(events) >= 1
            assert events[0]["type"] == "error"
            assert "not found" in events[0]["message"].lower()

    def test_stream_execution_initial_status(self, client):
        """GET stream emits initial status then execution_complete when terminal."""
        call_count = [0]

        def mock_get_status(execution_id):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "execution_id": execution_id,
                    "workflow_id": "wf-abc123",
                    "status": "running",
                    "node_states": {},
                }
            return {
                "execution_id": execution_id,
                "workflow_id": "wf-abc123",
                "status": "completed",
                "node_states": {"n1": "completed"},
            }

        with (
            patch(
                "app.services.workflow_execution_service.WorkflowExecutionService.get_execution_status",
                side_effect=mock_get_status,
            ),
            patch("time.sleep"),
        ):
            resp = client.get("/admin/workflows/wf-abc123/executions/wfx-test1234/stream")
            events = _parse_sse_events(resp.data)

            # First event: initial status
            assert events[0]["type"] == "status"
            assert events[0]["execution_id"] == "wfx-test1234"
            assert events[0]["status"] == "running"

            # Should have execution_complete event
            complete_events = [e for e in events if e["type"] == "execution_complete"]
            assert len(complete_events) == 1
            assert complete_events[0]["status"] == "completed"

    def test_stream_emits_node_state_changes(self, client):
        """GET stream emits node_start, node_complete events on state changes."""
        call_count = [0]

        def mock_get_status(execution_id):
            call_count[0] += 1
            if call_count[0] == 1:
                # Initial status
                return {
                    "execution_id": execution_id,
                    "workflow_id": "wf-abc123",
                    "status": "running",
                    "node_states": {"n1": "running"},
                }
            elif call_count[0] == 2:
                # n1 completed, n2 started
                return {
                    "execution_id": execution_id,
                    "workflow_id": "wf-abc123",
                    "status": "running",
                    "node_states": {"n1": "completed", "n2": "running"},
                }
            else:
                # All done
                return {
                    "execution_id": execution_id,
                    "workflow_id": "wf-abc123",
                    "status": "completed",
                    "node_states": {"n1": "completed", "n2": "completed"},
                }

        with (
            patch(
                "app.services.workflow_execution_service.WorkflowExecutionService.get_execution_status",
                side_effect=mock_get_status,
            ),
            patch("time.sleep"),
        ):
            resp = client.get("/admin/workflows/wf-abc123/executions/wfx-test1234/stream")
            events = _parse_sse_events(resp.data)

            # Check for node_complete event for n1
            node_complete_events = [
                e for e in events if e["type"] == "node_complete" and e["node_id"] == "n1"
            ]
            assert len(node_complete_events) >= 1

            # Check for node_start event for n2
            node_start_events = [
                e for e in events if e["type"] == "node_start" and e["node_id"] == "n2"
            ]
            assert len(node_start_events) >= 1

            # Check for execution_complete
            complete_events = [e for e in events if e["type"] == "execution_complete"]
            assert len(complete_events) == 1
            assert complete_events[0]["status"] == "completed"

    def test_stream_terminates_on_failed(self, client):
        """GET stream emits execution_complete with status=failed when execution fails."""
        call_count = [0]

        def mock_get_status(execution_id):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "execution_id": execution_id,
                    "workflow_id": "wf-abc123",
                    "status": "running",
                    "node_states": {"n1": "running"},
                }
            return {
                "execution_id": execution_id,
                "workflow_id": "wf-abc123",
                "status": "failed",
                "node_states": {"n1": "failed"},
            }

        with (
            patch(
                "app.services.workflow_execution_service.WorkflowExecutionService.get_execution_status",
                side_effect=mock_get_status,
            ),
            patch("time.sleep"),
        ):
            resp = client.get("/admin/workflows/wf-abc123/executions/wfx-test1234/stream")
            events = _parse_sse_events(resp.data)

            complete_events = [e for e in events if e["type"] == "execution_complete"]
            assert len(complete_events) == 1
            assert complete_events[0]["status"] == "failed"

            # Should also have node_failed event
            node_failed_events = [
                e for e in events if e["type"] == "node_failed" and e["node_id"] == "n1"
            ]
            assert len(node_failed_events) >= 1

    def test_stream_terminates_on_cancelled(self, client):
        """GET stream emits execution_complete with status=cancelled."""
        call_count = [0]

        def mock_get_status(execution_id):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "execution_id": execution_id,
                    "workflow_id": "wf-abc123",
                    "status": "running",
                    "node_states": {},
                }
            return {
                "execution_id": execution_id,
                "workflow_id": "wf-abc123",
                "status": "cancelled",
                "node_states": {},
            }

        with (
            patch(
                "app.services.workflow_execution_service.WorkflowExecutionService.get_execution_status",
                side_effect=mock_get_status,
            ),
            patch("time.sleep"),
        ):
            resp = client.get("/admin/workflows/wf-abc123/executions/wfx-test1234/stream")
            events = _parse_sse_events(resp.data)

            complete_events = [e for e in events if e["type"] == "execution_complete"]
            assert len(complete_events) == 1
            assert complete_events[0]["status"] == "cancelled"

    def test_stream_already_completed(self, client):
        """GET stream for already-completed execution emits status + execution_complete."""
        with patch(
            "app.services.workflow_execution_service.WorkflowExecutionService.get_execution_status",
            return_value={
                "execution_id": "wfx-done1234",
                "workflow_id": "wf-abc123",
                "status": "completed",
                "node_states": {"n1": "completed"},
            },
        ):
            resp = client.get("/admin/workflows/wf-abc123/executions/wfx-done1234/stream")
            events = _parse_sse_events(resp.data)

            assert events[0]["type"] == "status"
            assert events[0]["status"] == "completed"
            assert events[1]["type"] == "execution_complete"
            assert events[1]["status"] == "completed"

    def test_stream_content_type(self, client):
        """GET stream returns text/event-stream content type."""
        with patch(
            "app.services.workflow_execution_service.WorkflowExecutionService.get_execution_status",
            return_value=None,
        ):
            resp = client.get("/admin/workflows/wf-abc123/executions/wfx-test1234/stream")
            assert "text/event-stream" in resp.content_type
