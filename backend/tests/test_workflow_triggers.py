"""Tests for WorkflowTriggerService — completion, cron, polling, file watch triggers,
persistence loading, and trigger management endpoints."""

import hashlib
import json
import os
import time
from unittest.mock import MagicMock

import pytest

from app.db.workflows import (
    get_workflow_executions,
)
from app.services.workflow_execution_service import WorkflowExecutionService
from app.services.workflow_trigger_service import WorkflowTriggerService

# =============================================================================
# Helpers
# =============================================================================


def _create_workflow_with_trigger(client, trigger_type, trigger_config=None, name="Trigger WF"):
    """Create a workflow with specific trigger type and config via API."""
    payload = {
        "name": name,
        "trigger_type": trigger_type,
    }
    if trigger_config:
        payload["trigger_config"] = (
            json.dumps(trigger_config) if isinstance(trigger_config, dict) else trigger_config
        )
    resp = client.post("/admin/workflows/", json=payload)
    assert resp.status_code == 201
    return resp.get_json()["workflow_id"]


def _create_version_for_workflow(client, workflow_id):
    """Create a simple valid version (single trigger node) for a workflow."""
    graph = {
        "nodes": [{"id": "trigger", "type": "trigger", "label": "Start", "config": {}}],
        "edges": [],
    }
    resp = client.post(
        f"/admin/workflows/{workflow_id}/versions",
        json={"graph_json": json.dumps(graph)},
    )
    assert resp.status_code == 201
    return resp.get_json()["version"]


@pytest.fixture(autouse=True)
def reset_trigger_service():
    """Reset WorkflowTriggerService state before and after each test."""
    WorkflowTriggerService.reset()
    yield
    WorkflowTriggerService.reset()


# =============================================================================
# Completion Trigger Tests
# =============================================================================


class TestCompletionTrigger:
    """Tests for completion trigger registration, firing, and chain depth limits."""

    def test_register_completion_trigger(self, client):
        """Register a completion trigger and verify it's in _completion_callbacks."""
        WorkflowTriggerService.register_completion_trigger("workflow", "wf-source", "wf-target")
        key = ("workflow", "wf-source")
        assert key in WorkflowTriggerService._completion_callbacks
        assert "wf-target" in WorkflowTriggerService._completion_callbacks[key]

    def test_completion_trigger_fires_workflow(self, client):
        """Call on_execution_complete with matching source and verify workflow fires."""
        # Create target workflow with version
        wf_id = _create_workflow_with_trigger(client, "completion", name="Chained WF")
        _create_version_for_workflow(client, wf_id)

        # Register completion trigger
        WorkflowTriggerService.register_completion_trigger("workflow", "wf-src", wf_id)

        # Fire completion
        WorkflowTriggerService.on_execution_complete(
            "workflow", "wf-src", "completed", output={"result": "ok"}
        )

        # Give background thread time to create execution
        time.sleep(0.5)

        # Check that an execution was created
        executions = get_workflow_executions(wf_id)
        assert len(executions) >= 1

    def test_completion_trigger_chain_depth_limit(self, client, monkeypatch):
        """Calling on_execution_complete at max depth does NOT fire workflow."""
        calls = []
        monkeypatch.setattr(
            WorkflowExecutionService,
            "execute_workflow",
            classmethod(lambda cls, *args, **kwargs: calls.append(kwargs) or "mock-exec-id"),
        )

        WorkflowTriggerService.register_completion_trigger("workflow", "wf-deep", "wf-target")

        # Call with chain_depth=MAX_CHAIN_DEPTH — should be refused
        WorkflowTriggerService.on_execution_complete(
            "workflow", "wf-deep", "completed", chain_depth=10
        )

        assert len(calls) == 0

    def test_completion_trigger_no_match(self, client, monkeypatch):
        """Calling on_execution_complete with non-matching source fires nothing."""
        calls = []
        monkeypatch.setattr(
            WorkflowExecutionService,
            "execute_workflow",
            classmethod(lambda cls, *args, **kwargs: calls.append(kwargs) or "mock-exec-id"),
        )

        WorkflowTriggerService.register_completion_trigger("workflow", "wf-registered", "wf-target")

        # Different source — should not match
        WorkflowTriggerService.on_execution_complete("workflow", "wf-other", "completed")

        assert len(calls) == 0

    def test_unregister_completion_trigger(self, client, monkeypatch):
        """Register then unregister; on_execution_complete should not fire."""
        calls = []
        monkeypatch.setattr(
            WorkflowExecutionService,
            "execute_workflow",
            classmethod(lambda cls, *args, **kwargs: calls.append(kwargs) or "mock-exec-id"),
        )

        WorkflowTriggerService.register_completion_trigger("workflow", "wf-src", "wf-target")
        WorkflowTriggerService.unregister_completion_trigger("workflow", "wf-src", "wf-target")

        WorkflowTriggerService.on_execution_complete("workflow", "wf-src", "completed")
        assert len(calls) == 0

    def test_completion_trigger_duplicate_registration(self, client):
        """Registering the same trigger twice does not create duplicates."""
        WorkflowTriggerService.register_completion_trigger("workflow", "wf-src", "wf-target")
        WorkflowTriggerService.register_completion_trigger("workflow", "wf-src", "wf-target")

        key = ("workflow", "wf-src")
        assert WorkflowTriggerService._completion_callbacks[key].count("wf-target") == 1


# =============================================================================
# Cron Trigger Tests
# =============================================================================


def _setup_cron_mocks(monkeypatch):
    """Set up APScheduler mocks for cron trigger tests.

    Returns the mock_scheduler so tests can assert on it.
    """
    from app.services import scheduler_service as sched_mod

    mock_scheduler = MagicMock()
    mock_scheduler.get_job.return_value = None
    monkeypatch.setattr(sched_mod.SchedulerService, "_scheduler", mock_scheduler)
    monkeypatch.setattr(sched_mod, "SCHEDULER_AVAILABLE", True)

    # Mock CronTrigger with a real-enough fake
    mock_cron_trigger_cls = MagicMock()
    mock_pytz = MagicMock()

    # Make pytz.timezone return a mock with a str representation
    class FakeTz:
        def __init__(self, name):
            self.zone = name
            self.timezone = name

        def __str__(self):
            return self.zone

    mock_pytz.timezone = lambda name: FakeTz(name)
    mock_pytz.UTC = FakeTz("UTC")

    # Make CronTrigger.from_crontab return a mock trigger with timezone attribute
    def fake_from_crontab(expr, timezone=None):
        # Validate cron expression minimally (5 fields required)
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Wrong number of fields; got {len(parts)}, expected 5")
        # Check for obviously invalid fields
        for part in parts:
            if not any(c.isdigit() or c in "*,-/" for c in part):
                raise ValueError(f"Invalid field: {part}")
        result = MagicMock()
        result.timezone = timezone
        return result

    mock_cron_trigger_cls.from_crontab = fake_from_crontab
    monkeypatch.setattr(sched_mod, "CronTrigger", mock_cron_trigger_cls)
    monkeypatch.setattr(sched_mod, "pytz", mock_pytz)

    return mock_scheduler


class TestCronTrigger:
    """Tests for cron trigger registration, validation, timezone, and firing."""

    def test_register_cron_trigger(self, client, monkeypatch):
        """Register a cron trigger and verify APScheduler job is created."""
        mock_scheduler = _setup_cron_mocks(monkeypatch)

        WorkflowTriggerService.register_cron_trigger("wf-cron-1", "0 9 * * 1-5")

        mock_scheduler.add_job.assert_called_once()
        call_kwargs = mock_scheduler.add_job.call_args
        assert call_kwargs[1]["id"] == "wf-cron-wf-cron-1"

    def test_cron_trigger_invalid_expression(self, client, monkeypatch):
        """Register with invalid cron expression raises ValueError."""
        _setup_cron_mocks(monkeypatch)

        with pytest.raises(ValueError, match="Invalid cron expression"):
            WorkflowTriggerService.register_cron_trigger("wf-bad", "invalid cron")

    def test_cron_trigger_with_timezone(self, client, monkeypatch):
        """Register with timezone 'America/New_York' and verify CronTrigger created."""
        mock_scheduler = _setup_cron_mocks(monkeypatch)

        WorkflowTriggerService.register_cron_trigger(
            "wf-tz", "30 8 * * *", timezone_str="America/New_York"
        )

        mock_scheduler.add_job.assert_called_once()
        # Verify the trigger keyword argument was passed
        call_kwargs = mock_scheduler.add_job.call_args[1]
        trigger = call_kwargs.get("trigger")
        # The trigger should be a CronTrigger with New York timezone
        assert trigger is not None
        assert "New_York" in str(trigger.timezone)

    def test_unregister_cron_trigger(self, client, monkeypatch):
        """Register then unregister, verify job removed from scheduler."""
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_job = MagicMock()
        mock_scheduler.get_job.return_value = mock_job
        monkeypatch.setattr(SchedulerService, "_scheduler", mock_scheduler)

        WorkflowTriggerService.unregister_cron_trigger("wf-unreg")

        mock_scheduler.remove_job.assert_called_once_with("wf-cron-wf-unreg")

    def test_fire_cron_workflow(self, client, monkeypatch):
        """Call _fire_cron_workflow directly and verify execute_workflow called."""
        calls = []
        monkeypatch.setattr(
            WorkflowExecutionService,
            "execute_workflow",
            classmethod(lambda cls, *args, **kwargs: calls.append(kwargs) or "mock-exec-id"),
        )

        WorkflowTriggerService._fire_cron_workflow("wf-cron-fire")

        assert len(calls) == 1
        assert calls[0]["trigger_type"] == "cron"


# =============================================================================
# Polling Trigger Tests
# =============================================================================


class TestPollingTrigger:
    """Tests for polling trigger registration, deduplication, and firing."""

    def test_register_polling_trigger(self, client, monkeypatch):
        """Register a polling trigger and verify scheduler job created."""
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = None
        monkeypatch.setattr(SchedulerService, "_scheduler", mock_scheduler)
        monkeypatch.setattr("app.services.scheduler_service.SCHEDULER_AVAILABLE", True)

        WorkflowTriggerService.register_polling_trigger(
            "wf-poll-1", "https://example.com/api/status", interval_seconds=30
        )

        mock_scheduler.add_job.assert_called_once()
        assert "wf-poll-1" in WorkflowTriggerService._polling_jobs

    def test_poll_api_fires_on_change(self, client, monkeypatch):
        """Poll with different response hash fires workflow."""
        calls = []
        monkeypatch.setattr(
            WorkflowExecutionService,
            "execute_workflow",
            classmethod(lambda cls, *args, **kwargs: calls.append(kwargs) or "mock-exec-id"),
        )

        # Set up polling state with initial hash
        WorkflowTriggerService._polling_jobs["wf-poll-change"] = {
            "last_hash": "old-hash-value",
            "job_id": "wf-poll-wf-poll-change",
            "url": "https://example.com",
        }

        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.read.return_value = b"new response body"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        import app.services.workflow_trigger_service as wts_mod

        monkeypatch.setattr(
            wts_mod.urllib.request,
            "urlopen",
            lambda *a, **kw: mock_response,
        )

        WorkflowTriggerService._poll_api(
            "wf-poll-change", "https://example.com", "GET", None, "status_changed"
        )

        assert len(calls) == 1
        assert calls[0]["trigger_type"] == "poll"

    def test_poll_api_deduplicates(self, client, monkeypatch):
        """Poll with same response hash does not fire workflow (deduplication)."""
        calls = []
        monkeypatch.setattr(
            WorkflowExecutionService,
            "execute_workflow",
            classmethod(lambda cls, *args, **kwargs: calls.append(kwargs) or "mock-exec-id"),
        )

        body = b"same response body"
        body_hash = hashlib.sha256(body).hexdigest()

        # Set initial hash to the same value as response
        WorkflowTriggerService._polling_jobs["wf-poll-dedup"] = {
            "last_hash": body_hash,
            "job_id": "wf-poll-wf-poll-dedup",
            "url": "https://example.com",
        }

        mock_response = MagicMock()
        mock_response.read.return_value = body
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        import app.services.workflow_trigger_service as wts_mod

        monkeypatch.setattr(
            wts_mod.urllib.request,
            "urlopen",
            lambda *a, **kw: mock_response,
        )

        WorkflowTriggerService._poll_api(
            "wf-poll-dedup", "https://example.com", "GET", None, "status_changed"
        )

        # Should NOT fire because hash is same
        assert len(calls) == 0

    def test_unregister_polling_trigger(self, client, monkeypatch):
        """Register then unregister, verify job removed and _polling_jobs cleaned."""
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = MagicMock()
        monkeypatch.setattr(SchedulerService, "_scheduler", mock_scheduler)

        WorkflowTriggerService._polling_jobs["wf-unreg-poll"] = {
            "last_hash": None,
            "job_id": "wf-poll-wf-unreg-poll",
        }

        WorkflowTriggerService.unregister_polling_trigger("wf-unreg-poll")

        mock_scheduler.remove_job.assert_called_once()
        assert "wf-unreg-poll" not in WorkflowTriggerService._polling_jobs


# =============================================================================
# File Watch Trigger Tests
# =============================================================================


class TestFileWatchTrigger:
    """Tests for file watch trigger registration, firing, and cleanup."""

    def test_register_file_watch_trigger(self, client, tmp_path):
        """Register file watch on a temp directory; verify observer started."""
        watch_dir = str(tmp_path / "watch")
        os.makedirs(watch_dir)

        WorkflowTriggerService.register_file_watch_trigger("wf-fw-1", watch_dir)

        assert "wf-fw-1" in WorkflowTriggerService._file_watchers
        watcher_info = WorkflowTriggerService._file_watchers["wf-fw-1"]
        assert watcher_info["observer"] is not None
        assert watcher_info["observer"].is_alive()

    def test_file_watch_fires_on_change(self, client, tmp_path, monkeypatch):
        """Register watcher, create a file, verify workflow execution is triggered."""
        calls = []
        monkeypatch.setattr(
            WorkflowExecutionService,
            "execute_workflow",
            classmethod(lambda cls, *args, **kwargs: calls.append(kwargs) or "mock-exec-id"),
        )

        watch_dir = str(tmp_path / "watched")
        os.makedirs(watch_dir)

        WorkflowTriggerService.register_file_watch_trigger("wf-fw-fire", watch_dir)

        # Create a file in the watched directory
        test_file = os.path.join(watch_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("hello world")

        # Wait for watchdog + debounce (1s debounce + some margin)
        time.sleep(2.5)

        assert len(calls) >= 1
        assert calls[0]["trigger_type"] == "file_watch"

    def test_unregister_file_watch_trigger(self, client, tmp_path):
        """Register then unregister; verify observer stopped and removed."""
        watch_dir = str(tmp_path / "unwatch")
        os.makedirs(watch_dir)

        WorkflowTriggerService.register_file_watch_trigger("wf-fw-unreg", watch_dir)
        assert "wf-fw-unreg" in WorkflowTriggerService._file_watchers

        observer = WorkflowTriggerService._file_watchers["wf-fw-unreg"]["observer"]
        WorkflowTriggerService.unregister_file_watch_trigger("wf-fw-unreg")

        assert "wf-fw-unreg" not in WorkflowTriggerService._file_watchers
        assert not observer.is_alive()

    def test_file_watch_invalid_path(self, client):
        """Registering a watch on a nonexistent path raises ValueError."""
        with pytest.raises(ValueError, match="not a directory"):
            WorkflowTriggerService.register_file_watch_trigger(
                "wf-bad-path", "/nonexistent/path/that/does/not/exist"
            )


# =============================================================================
# Persistence Tests
# =============================================================================


class TestTriggerPersistence:
    """Tests for loading triggers from DB on startup."""

    def test_load_completion_triggers_on_init(self, client):
        """Create workflow with trigger_type=completion; loading picks it up."""
        wf_id = _create_workflow_with_trigger(
            client,
            "completion",
            trigger_config={"source_type": "workflow", "source_id": "wf-src-123"},
            name="Persist Completion WF",
        )

        # Clear and reload
        WorkflowTriggerService._completion_callbacks.clear()
        WorkflowTriggerService._load_completion_triggers()

        key = ("workflow", "wf-src-123")
        assert key in WorkflowTriggerService._completion_callbacks
        assert wf_id in WorkflowTriggerService._completion_callbacks[key]

    def test_load_cron_triggers_on_init(self, client, monkeypatch):
        """Create workflow with trigger_type=cron; loading registers APScheduler job."""
        mock_scheduler = _setup_cron_mocks(monkeypatch)

        _create_workflow_with_trigger(
            client,
            "cron",
            trigger_config={"cron_expression": "0 9 * * 1-5", "timezone": "UTC"},
            name="Persist Cron WF",
        )

        WorkflowTriggerService._load_cron_triggers()

        # Should have called add_job on the scheduler
        assert mock_scheduler.add_job.call_count >= 1


# =============================================================================
# Trigger Endpoint Tests
# =============================================================================


class TestTriggerEndpoints:
    """Tests for the trigger management API endpoints."""

    def test_register_trigger_endpoint(self, client, monkeypatch):
        """POST /admin/workflows/:id/triggers/register returns 200."""
        # Mock the trigger service to avoid needing scheduler
        monkeypatch.setattr(
            WorkflowTriggerService,
            "register_trigger",
            classmethod(lambda cls, *args, **kwargs: None),
        )

        wf_id = _create_workflow_with_trigger(
            client,
            "completion",
            trigger_config={"source_type": "workflow", "source_id": "wf-src"},
            name="Endpoint Register WF",
        )

        resp = client.post(f"/admin/workflows/{wf_id}/triggers/register")
        assert resp.status_code == 200
        assert "registered" in resp.get_json()["message"].lower()

    def test_unregister_trigger_endpoint(self, client, monkeypatch):
        """DELETE /admin/workflows/:id/triggers/unregister returns 200."""
        monkeypatch.setattr(
            WorkflowTriggerService,
            "unregister_trigger",
            classmethod(lambda cls, *args, **kwargs: None),
        )

        wf_id = _create_workflow_with_trigger(
            client,
            "completion",
            trigger_config={"source_type": "workflow", "source_id": "wf-src"},
            name="Endpoint Unregister WF",
        )

        resp = client.delete(f"/admin/workflows/{wf_id}/triggers/unregister")
        assert resp.status_code == 200
        assert "unregistered" in resp.get_json()["message"].lower()

    def test_register_manual_trigger_rejected(self, client):
        """Manual workflows should reject trigger registration."""
        wf_id = _create_workflow_with_trigger(client, "manual", name="Manual WF")

        resp = client.post(f"/admin/workflows/{wf_id}/triggers/register")
        assert resp.status_code == 400

    def test_register_trigger_not_found(self, client):
        """Non-existent workflow returns 404."""
        resp = client.post("/admin/workflows/wf-nonexistent/triggers/register")
        assert resp.status_code == 404


# =============================================================================
# Generic Register/Unregister Tests
# =============================================================================


class TestGenericTriggerRegistration:
    """Tests for the generic register_trigger/unregister_trigger methods."""

    def test_register_unknown_type_raises(self, client):
        """Unknown trigger type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown trigger type"):
            WorkflowTriggerService.register_trigger("wf-1", "unknown_type", {})

    def test_unregister_unknown_type_raises(self, client):
        """Unknown trigger type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown trigger type"):
            WorkflowTriggerService.unregister_trigger("wf-1", "unknown_type")
