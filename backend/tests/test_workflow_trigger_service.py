"""Tests for WorkflowTriggerService."""

import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app.services.workflow_trigger_service import (
    WorkflowTriggerService,
    _WorkflowFileWatchHandler,
)


@pytest.fixture(autouse=True)
def reset_trigger_state():
    """Reset all in-memory trigger state before and after each test."""
    WorkflowTriggerService.reset()
    yield
    WorkflowTriggerService.reset()


# =============================================================================
# Completion Triggers
# =============================================================================


class TestCompletionTriggers:
    """Tests for completion trigger registration and firing."""

    def test_register_completion_trigger(self):
        WorkflowTriggerService.register_completion_trigger("workflow", "wf-001", "wf-target")

        key = ("workflow", "wf-001")
        assert key in WorkflowTriggerService._completion_callbacks
        assert "wf-target" in WorkflowTriggerService._completion_callbacks[key]

    def test_register_duplicate_is_idempotent(self):
        WorkflowTriggerService.register_completion_trigger("workflow", "wf-001", "wf-target")
        WorkflowTriggerService.register_completion_trigger("workflow", "wf-001", "wf-target")

        key = ("workflow", "wf-001")
        assert WorkflowTriggerService._completion_callbacks[key].count("wf-target") == 1

    def test_unregister_completion_trigger(self):
        WorkflowTriggerService.register_completion_trigger("workflow", "wf-001", "wf-target")
        WorkflowTriggerService.unregister_completion_trigger("workflow", "wf-001", "wf-target")

        key = ("workflow", "wf-001")
        assert key not in WorkflowTriggerService._completion_callbacks

    def test_unregister_nonexistent_trigger_is_safe(self):
        """Unregistering a trigger that doesn't exist should not raise."""
        WorkflowTriggerService.unregister_completion_trigger("workflow", "wf-999", "wf-target")

    def test_on_execution_complete_fires_targets(self):
        """Completion triggers fire registered target workflows."""
        WorkflowTriggerService.register_completion_trigger("agent", "agent-001", "wf-chain")

        with patch(
            "app.services.workflow_execution_service.WorkflowExecutionService.execute_workflow"
        ) as mock_exec:
            WorkflowTriggerService.on_execution_complete(
                entity_type="agent",
                entity_id="agent-001",
                status="completed",
                output={"result": "ok"},
                chain_depth=0,
            )

            mock_exec.assert_called_once()
            call_args = mock_exec.call_args
            assert call_args[0][0] == "wf-chain"
            assert call_args[1]["trigger_type"] == "completion"
            input_data = json.loads(call_args[1]["input_json"])
            assert input_data["source_type"] == "agent"
            assert input_data["chain_depth"] == 1

    def test_on_execution_complete_no_targets(self):
        """No-op when no completion callbacks are registered for the entity."""
        # Should not raise
        WorkflowTriggerService.on_execution_complete(
            entity_type="agent",
            entity_id="agent-none",
            status="completed",
        )

    def test_max_chain_depth_prevents_infinite_recursion(self):
        """Triggers do not fire when chain_depth >= MAX_CHAIN_DEPTH."""
        WorkflowTriggerService.register_completion_trigger("workflow", "wf-deep", "wf-next")

        with patch(
            "app.services.workflow_execution_service.WorkflowExecutionService.execute_workflow"
        ) as mock_exec:
            WorkflowTriggerService.on_execution_complete(
                entity_type="workflow",
                entity_id="wf-deep",
                status="completed",
                chain_depth=WorkflowTriggerService.MAX_CHAIN_DEPTH,
            )

            mock_exec.assert_not_called()


# =============================================================================
# Cron Triggers
# =============================================================================


class TestCronTriggers:
    """Tests for cron trigger registration."""

    def test_register_cron_trigger_no_scheduler_raises(self):
        """Raises ValueError if scheduler is not initialized."""
        with patch("app.services.scheduler_service.SCHEDULER_AVAILABLE", True), \
             patch("app.services.scheduler_service.SchedulerService._scheduler", None):
            with pytest.raises(ValueError, match="Scheduler not initialized"):
                WorkflowTriggerService.register_cron_trigger("wf-001", "*/5 * * * *")

    def test_fire_cron_workflow_calls_execute(self):
        """_fire_cron_workflow delegates to WorkflowExecutionService."""
        with patch(
            "app.services.workflow_execution_service.WorkflowExecutionService.execute_workflow"
        ) as mock_exec:
            WorkflowTriggerService._fire_cron_workflow("wf-cron-1")

            mock_exec.assert_called_once_with("wf-cron-1", trigger_type="cron")

    def test_fire_cron_workflow_handles_exception(self):
        """_fire_cron_workflow does not raise when execution fails."""
        with patch(
            "app.services.workflow_execution_service.WorkflowExecutionService.execute_workflow",
            side_effect=RuntimeError("execution failed"),
        ):
            # Should not raise
            WorkflowTriggerService._fire_cron_workflow("wf-cron-fail")


# =============================================================================
# Polling Triggers
# =============================================================================


class TestPollingTriggers:
    """Tests for API polling trigger logic."""

    def test_poll_api_first_poll_records_hash_no_fire(self):
        """First poll with status_changed condition stores hash but does not fire."""
        WorkflowTriggerService._polling_jobs["wf-poll-1"] = {
            "last_hash": None,
            "job_id": "wf-poll-wf-poll-1",
            "url": "http://example.com",
            "method": "GET",
            "headers": None,
            "condition": "status_changed",
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"response body"
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            with patch(
                "app.services.workflow_execution_service.WorkflowExecutionService.execute_workflow"
            ) as mock_exec:
                WorkflowTriggerService._poll_api(
                    "wf-poll-1", "http://example.com", "GET", None, "status_changed"
                )

                mock_exec.assert_not_called()

        # Hash should now be stored
        assert WorkflowTriggerService._polling_jobs["wf-poll-1"]["last_hash"] is not None

    def test_poll_api_fires_on_change(self):
        """Poll fires workflow when response hash changes."""
        import hashlib

        initial_hash = hashlib.sha256(b"old response").hexdigest()
        WorkflowTriggerService._polling_jobs["wf-poll-2"] = {
            "last_hash": initial_hash,
            "job_id": "wf-poll-wf-poll-2",
            "url": "http://example.com",
            "method": "GET",
            "headers": None,
            "condition": "status_changed",
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"new response"
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            with patch(
                "app.services.workflow_execution_service.WorkflowExecutionService.execute_workflow"
            ) as mock_exec:
                WorkflowTriggerService._poll_api(
                    "wf-poll-2", "http://example.com", "GET", None, "status_changed"
                )

                mock_exec.assert_called_once()

    def test_poll_api_always_condition_fires_every_time(self):
        """Poll with 'always' condition fires on every poll."""
        WorkflowTriggerService._polling_jobs["wf-poll-always"] = {
            "last_hash": "somehash",
            "job_id": "wf-poll-wf-poll-always",
            "url": "http://example.com",
            "method": "GET",
            "headers": None,
            "condition": "always",
        }

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"same response"
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            with patch(
                "app.services.workflow_execution_service.WorkflowExecutionService.execute_workflow"
            ) as mock_exec:
                WorkflowTriggerService._poll_api(
                    "wf-poll-always", "http://example.com", "GET", None, "always"
                )

                mock_exec.assert_called_once()

    def test_poll_api_request_failure_does_not_raise(self):
        """Network error in poll does not propagate."""
        WorkflowTriggerService._polling_jobs["wf-poll-err"] = {
            "last_hash": None,
            "job_id": "wf-poll-wf-poll-err",
            "url": "http://example.com",
            "method": "GET",
            "headers": None,
            "condition": "status_changed",
        }

        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            # Should not raise
            WorkflowTriggerService._poll_api(
                "wf-poll-err", "http://example.com", "GET", None, "status_changed"
            )

    def test_unregister_polling_trigger(self):
        """Unregister removes polling state."""
        WorkflowTriggerService._polling_jobs["wf-poll-del"] = {
            "last_hash": None,
            "job_id": "wf-poll-wf-poll-del",
        }

        with patch("app.services.scheduler_service.SchedulerService._scheduler", None):
            WorkflowTriggerService.unregister_polling_trigger("wf-poll-del")

        assert "wf-poll-del" not in WorkflowTriggerService._polling_jobs


# =============================================================================
# Generic register_trigger / unregister_trigger
# =============================================================================


class TestRegisterTrigger:
    """Tests for the generic register_trigger dispatcher."""

    def test_register_completion_trigger_via_generic(self):
        WorkflowTriggerService.register_trigger(
            "wf-gen-1", "completion", {"source_type": "agent", "source_id": "agent-001"}
        )

        key = ("agent", "agent-001")
        assert "wf-gen-1" in WorkflowTriggerService._completion_callbacks[key]

    def test_register_completion_trigger_missing_fields_raises(self):
        with pytest.raises(ValueError, match="source_type and source_id"):
            WorkflowTriggerService.register_trigger("wf-gen-2", "completion", {})

    def test_register_cron_trigger_missing_expression_raises(self):
        with pytest.raises(ValueError, match="cron_expression"):
            WorkflowTriggerService.register_trigger("wf-gen-3", "cron", {})

    def test_register_poll_trigger_missing_url_raises(self):
        with pytest.raises(ValueError, match="url"):
            WorkflowTriggerService.register_trigger("wf-gen-4", "poll", {})

    def test_register_file_watch_trigger_missing_path_raises(self):
        with pytest.raises(ValueError, match="watch_path"):
            WorkflowTriggerService.register_trigger("wf-gen-5", "file_watch", {})

    def test_register_unknown_trigger_type_raises(self):
        with pytest.raises(ValueError, match="Unknown trigger type"):
            WorkflowTriggerService.register_trigger("wf-gen-6", "unknown_type", {})

    def test_unregister_unknown_trigger_type_raises(self):
        with pytest.raises(ValueError, match="Unknown trigger type"):
            WorkflowTriggerService.unregister_trigger("wf-gen-7", "unknown_type")

    def test_unregister_completion_trigger_via_generic(self):
        WorkflowTriggerService.register_completion_trigger("agent", "agent-001", "wf-unreg")

        WorkflowTriggerService.unregister_trigger("wf-unreg", "completion")

        key = ("agent", "agent-001")
        assert key not in WorkflowTriggerService._completion_callbacks


# =============================================================================
# _WorkflowFileWatchHandler
# =============================================================================


class TestWorkflowFileWatchHandler:
    """Tests for the file watch handler debounce logic."""

    def test_ignores_directory_events(self):
        handler = _WorkflowFileWatchHandler("wf-fw-1")

        event = MagicMock()
        event.is_directory = True

        handler.dispatch(event)

        assert len(handler._pending) == 0

    def test_accepts_file_events(self):
        handler = _WorkflowFileWatchHandler("wf-fw-2", debounce_seconds=10.0)

        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/test.py"
        event.event_type = "modified"

        handler.dispatch(event)

        assert "/tmp/test.py" in handler._pending
        handler.stop()

    def test_pattern_filtering_rejects_non_matching(self):
        handler = _WorkflowFileWatchHandler("wf-fw-3", patterns=["*.py"], debounce_seconds=10.0)

        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/readme.md"
        event.event_type = "modified"

        handler.dispatch(event)

        assert len(handler._pending) == 0
        handler.stop()

    def test_pattern_filtering_accepts_matching(self):
        handler = _WorkflowFileWatchHandler("wf-fw-4", patterns=["*.py"], debounce_seconds=10.0)

        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/app.py"
        event.event_type = "modified"

        handler.dispatch(event)

        assert "/tmp/app.py" in handler._pending
        handler.stop()

    def test_stop_cancels_timer(self):
        handler = _WorkflowFileWatchHandler("wf-fw-5", debounce_seconds=10.0)

        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/test.py"
        event.event_type = "modified"

        handler.dispatch(event)
        assert handler._timer is not None

        handler.stop()
        assert handler._timer is None


# =============================================================================
# Init / Shutdown / Reset
# =============================================================================


class TestLifecycle:
    """Tests for init, shutdown, and reset."""

    @patch.object(WorkflowTriggerService, "_load_file_watch_triggers")
    @patch.object(WorkflowTriggerService, "_load_polling_triggers")
    @patch.object(WorkflowTriggerService, "_load_cron_triggers")
    @patch.object(WorkflowTriggerService, "_load_completion_triggers")
    def test_init_loads_all_triggers(self, mock_comp, mock_cron, mock_poll, mock_fw):
        WorkflowTriggerService._initialized = False
        WorkflowTriggerService.init()

        mock_comp.assert_called_once()
        mock_cron.assert_called_once()
        mock_poll.assert_called_once()
        mock_fw.assert_called_once()
        assert WorkflowTriggerService._initialized is True

    @patch.object(WorkflowTriggerService, "_load_file_watch_triggers")
    @patch.object(WorkflowTriggerService, "_load_polling_triggers")
    @patch.object(WorkflowTriggerService, "_load_cron_triggers")
    @patch.object(WorkflowTriggerService, "_load_completion_triggers")
    def test_init_is_idempotent(self, mock_comp, mock_cron, mock_poll, mock_fw):
        WorkflowTriggerService._initialized = False
        WorkflowTriggerService.init()
        WorkflowTriggerService.init()

        # Each loader should only be called once
        mock_comp.assert_called_once()

    def test_reset_clears_state(self):
        WorkflowTriggerService.register_completion_trigger("workflow", "wf-r", "wf-t")
        WorkflowTriggerService._polling_jobs["wf-p"] = {"last_hash": None}
        WorkflowTriggerService._initialized = True

        WorkflowTriggerService.reset()

        assert len(WorkflowTriggerService._completion_callbacks) == 0
        assert len(WorkflowTriggerService._polling_jobs) == 0
        assert WorkflowTriggerService._initialized is False
