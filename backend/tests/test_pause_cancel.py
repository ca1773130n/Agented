"""Tests for pause/resume/bulk-cancel execution management."""

import signal
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.db.triggers import (
    create_execution_log,
    get_execution_log,
    get_execution_logs_filtered,
    update_execution_log,
)
from app.services.process_manager import ProcessManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_process(pid=12345, pgid=12345, poll_return=None):
    """Create a mock subprocess.Popen."""
    proc = MagicMock(spec=subprocess.Popen)
    proc.pid = pid
    proc.poll.return_value = poll_return
    return proc


def _seed_execution(execution_id="exec-test-001", trigger_id="bot-security", status="running"):
    """Insert a minimal execution log record for testing."""
    create_execution_log(
        execution_id=execution_id,
        trigger_id=trigger_id,
        trigger_type="manual",
        started_at="2026-03-05T10:00:00",
        prompt="test",
        backend_type="claude",
        command="echo test",
    )
    if status != "running":
        update_execution_log(execution_id=execution_id, status=status)
    return execution_id


@pytest.fixture(autouse=True)
def _reset_process_manager():
    """Reset ProcessManager singleton state between tests."""
    ProcessManager._processes.clear()
    ProcessManager._cancelled.clear()
    yield
    # Cleanup timers
    for info in ProcessManager._processes.values():
        if info.pause_timer:
            info.pause_timer.cancel()
    ProcessManager._processes.clear()
    ProcessManager._cancelled.clear()


# ---------------------------------------------------------------------------
# ProcessManager.pause() tests
# ---------------------------------------------------------------------------


class TestProcessManagerPause:
    """Test ProcessManager.pause() method."""

    def test_pause_sends_sigstop(self):
        """Pause sends SIGSTOP to process group and returns True."""
        proc = _make_mock_process()
        ProcessManager.register("exec-001", proc, "trig-001")
        _seed_execution("exec-001")

        with patch("os.killpg") as mock_killpg:
            result = ProcessManager.pause("exec-001")

        assert result is True
        mock_killpg.assert_called_once_with(proc.pid, signal.SIGSTOP)

    def test_pause_updates_status_to_paused(self):
        """Pause updates DB status to 'paused' via CAS."""
        proc = _make_mock_process()
        ProcessManager.register("exec-002", proc, "trig-001")
        _seed_execution("exec-002")

        with patch("os.killpg"):
            ProcessManager.pause("exec-002")

        execution = get_execution_log("exec-002")
        assert execution["status"] == "paused"

    def test_pause_sets_paused_at_timestamp(self):
        """Pause records the pause timestamp in ProcessInfo."""
        proc = _make_mock_process()
        ProcessManager.register("exec-003", proc, "trig-001")
        _seed_execution("exec-003")

        with patch("os.killpg"):
            ProcessManager.pause("exec-003")

        info = ProcessManager._processes["exec-003"]
        assert info.paused_at is not None
        assert info.paused_at > 0

    def test_pause_schedules_auto_cancel_timer(self):
        """Pause schedules a daemon timer for auto-cancel."""
        proc = _make_mock_process()
        ProcessManager.register("exec-004", proc, "trig-001")
        _seed_execution("exec-004")

        with patch("os.killpg"):
            ProcessManager.pause("exec-004")

        info = ProcessManager._processes["exec-004"]
        assert info.pause_timer is not None
        assert info.pause_timer.daemon is True
        info.pause_timer.cancel()  # Cleanup

    def test_pause_returns_false_for_nonexistent(self):
        """Pause returns False when execution is not tracked."""
        result = ProcessManager.pause("nonexistent")
        assert result is False

    def test_pause_returns_false_if_not_running(self):
        """Pause returns False when CAS fails (execution not in running state)."""
        proc = _make_mock_process()
        ProcessManager.register("exec-005", proc, "trig-001")
        _seed_execution("exec-005", status="success")

        with patch("os.killpg"):
            result = ProcessManager.pause("exec-005")

        assert result is False


# ---------------------------------------------------------------------------
# ProcessManager.resume() tests
# ---------------------------------------------------------------------------


class TestProcessManagerResume:
    """Test ProcessManager.resume() method."""

    def test_resume_sends_sigcont(self):
        """Resume sends SIGCONT to process group and returns True."""
        proc = _make_mock_process()
        ProcessManager.register("exec-010", proc, "trig-001")
        _seed_execution("exec-010")

        with patch("os.killpg") as mock_killpg:
            # First pause
            ProcessManager.pause("exec-010")
            mock_killpg.reset_mock()
            # Then resume
            result = ProcessManager.resume("exec-010")

        assert result is True
        mock_killpg.assert_called_once_with(proc.pid, signal.SIGCONT)

    def test_resume_updates_status_to_running(self):
        """Resume updates DB status back to 'running' via CAS."""
        proc = _make_mock_process()
        ProcessManager.register("exec-011", proc, "trig-001")
        _seed_execution("exec-011")

        with patch("os.killpg"):
            ProcessManager.pause("exec-011")
            ProcessManager.resume("exec-011")

        execution = get_execution_log("exec-011")
        assert execution["status"] == "running"

    def test_resume_cancels_auto_cancel_timer(self):
        """Resume cancels the auto-cancel timer."""
        proc = _make_mock_process()
        ProcessManager.register("exec-012", proc, "trig-001")
        _seed_execution("exec-012")

        with patch("os.killpg"):
            ProcessManager.pause("exec-012")
            info = ProcessManager._processes["exec-012"]
            timer = info.pause_timer
            assert timer is not None
            ProcessManager.resume("exec-012")

        assert info.pause_timer is None
        assert info.paused_at is None

    def test_resume_returns_false_if_not_paused(self):
        """Resume returns False when execution is not in paused state."""
        proc = _make_mock_process()
        ProcessManager.register("exec-013", proc, "trig-001")
        _seed_execution("exec-013")  # Status is "running"

        with patch("os.killpg"):
            result = ProcessManager.resume("exec-013")

        assert result is False

    def test_resume_returns_false_for_nonexistent(self):
        """Resume returns False when execution is not tracked."""
        result = ProcessManager.resume("nonexistent")
        assert result is False


# ---------------------------------------------------------------------------
# Auto-cancel timeout tests
# ---------------------------------------------------------------------------


class TestAutoCancel:
    """Test auto-cancel behavior after pause timeout."""

    def test_auto_cancel_fires_after_timeout(self):
        """Auto-cancel sends SIGCONT then SIGTERM to stopped process."""
        proc = _make_mock_process(poll_return=None)
        ProcessManager.register("exec-020", proc, "trig-001")
        _seed_execution("exec-020")

        # Use a very short timeout for testing
        with (
            patch("os.killpg") as mock_killpg,
            patch("app.services.process_manager.PAUSE_TIMEOUT", 0.1),
        ):
            ProcessManager.pause("exec-020")
            # Cancel the real timer and invoke directly
            info = ProcessManager._processes["exec-020"]
            info.pause_timer.cancel()

            # Manually invoke auto-cancel
            ProcessManager._auto_cancel_paused("exec-020")

        # Should have called: SIGSTOP (pause), SIGCONT (auto-cancel), SIGTERM (cancel)
        calls = mock_killpg.call_args_list
        signals_sent = [c[0][1] for c in calls]
        assert signal.SIGSTOP in signals_sent
        assert signal.SIGCONT in signals_sent
        assert signal.SIGTERM in signals_sent

    def test_auto_cancel_updates_status_to_pause_timeout(self):
        """Auto-cancel updates DB status to 'pause_timeout'."""
        proc = _make_mock_process()
        ProcessManager.register("exec-021", proc, "trig-001")
        _seed_execution("exec-021")

        with patch("os.killpg"):
            ProcessManager.pause("exec-021")
            info = ProcessManager._processes["exec-021"]
            info.pause_timer.cancel()
            ProcessManager._auto_cancel_paused("exec-021")

        execution = get_execution_log("exec-021")
        assert execution["status"] == "pause_timeout"

    def test_auto_cancel_skips_if_already_resumed(self):
        """Auto-cancel does nothing if execution was already resumed."""
        proc = _make_mock_process()
        ProcessManager.register("exec-022", proc, "trig-001")
        _seed_execution("exec-022")

        with patch("os.killpg") as mock_killpg:
            ProcessManager.pause("exec-022")
            info = ProcessManager._processes["exec-022"]
            info.pause_timer.cancel()
            ProcessManager.resume("exec-022")
            mock_killpg.reset_mock()

            # Fire auto-cancel -- should be a no-op since status is now "running"
            ProcessManager._auto_cancel_paused("exec-022")

        # No signals should have been sent after resume
        mock_killpg.assert_not_called()

        execution = get_execution_log("exec-022")
        assert execution["status"] == "running"


# ---------------------------------------------------------------------------
# Cleanup tests
# ---------------------------------------------------------------------------


class TestCleanup:
    """Test cleanup cancels pause timer."""

    def test_cleanup_cancels_pause_timer(self):
        """Cleanup cancels any active pause timer."""
        proc = _make_mock_process()
        ProcessManager.register("exec-030", proc, "trig-001")
        _seed_execution("exec-030")

        with patch("os.killpg"):
            ProcessManager.pause("exec-030")
            info = ProcessManager._processes["exec-030"]
            timer = info.pause_timer
            assert timer is not None

        ProcessManager.cleanup("exec-030")
        assert "exec-030" not in ProcessManager._processes


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestPauseResumeAPI:
    """Test pause/resume/bulk-cancel API endpoints."""

    def test_pause_endpoint_returns_200(self, client):
        """POST /admin/executions/<id>/pause returns 200 with paused status."""
        eid = _seed_execution("exec-api-001")
        proc = _make_mock_process()
        ProcessManager.register(eid, proc, "trig-001")

        with patch("os.killpg"):
            resp = client.post(f"/admin/executions/{eid}/pause")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "paused"

    def test_pause_nonrunning_returns_409(self, client):
        """POST /admin/executions/<id>/pause on completed execution returns 409."""
        eid = _seed_execution("exec-api-002", status="success")

        resp = client.post(f"/admin/executions/{eid}/pause")

        assert resp.status_code == 409

    def test_pause_nonexistent_returns_404(self, client):
        """POST /admin/executions/<id>/pause on missing execution returns 404."""
        resp = client.post("/admin/executions/nonexistent/pause")

        assert resp.status_code == 404

    def test_resume_endpoint_returns_200(self, client):
        """POST /admin/executions/<id>/resume returns 200 with running status."""
        eid = _seed_execution("exec-api-003")
        proc = _make_mock_process()
        ProcessManager.register(eid, proc, "trig-001")

        with patch("os.killpg"):
            client.post(f"/admin/executions/{eid}/pause")
            resp = client.post(f"/admin/executions/{eid}/resume")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "running"

    def test_resume_nonpaused_returns_409(self, client):
        """POST /admin/executions/<id>/resume on running execution returns 409."""
        eid = _seed_execution("exec-api-004")

        resp = client.post(f"/admin/executions/{eid}/resume")

        assert resp.status_code == 409

    def test_bulk_cancel_by_execution_ids(self, client):
        """POST /admin/executions/bulk-cancel by explicit IDs cancels matching."""
        eid1 = _seed_execution("exec-bulk-001")
        eid2 = _seed_execution("exec-bulk-002")
        proc1 = _make_mock_process(pid=111, pgid=111)
        proc2 = _make_mock_process(pid=222, pgid=222)
        ProcessManager.register(eid1, proc1, "trig-001")
        ProcessManager.register(eid2, proc2, "trig-001")

        with patch("os.killpg"):
            resp = client.post(
                "/admin/executions/bulk-cancel",
                json={"execution_ids": [eid1, eid2]},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["cancelled"] == 2
        assert data["failed"] == 0
        assert len(data["details"]) == 2

    def test_bulk_cancel_by_trigger_id(self, client):
        """POST /admin/executions/bulk-cancel by trigger_id cancels matching."""
        eid1 = _seed_execution("exec-bulk-010", trigger_id="bot-pr-review")
        eid2 = _seed_execution("exec-bulk-011", trigger_id="bot-pr-review")
        proc1 = _make_mock_process(pid=333, pgid=333)
        proc2 = _make_mock_process(pid=444, pgid=444)
        ProcessManager.register(eid1, proc1, "bot-pr-review")
        ProcessManager.register(eid2, proc2, "bot-pr-review")

        with patch("os.killpg"):
            resp = client.post(
                "/admin/executions/bulk-cancel",
                json={"trigger_id": "bot-pr-review", "status": "running"},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["cancelled"] == 2

    def test_bulk_cancel_returns_per_execution_details(self, client):
        """Bulk cancel response includes per-execution success/failure details."""
        eid1 = _seed_execution("exec-bulk-020")
        eid2 = _seed_execution("exec-bulk-021", status="success")  # Not cancellable
        proc1 = _make_mock_process(pid=555, pgid=555)
        ProcessManager.register(eid1, proc1, "trig-001")

        with patch("os.killpg"):
            resp = client.post(
                "/admin/executions/bulk-cancel",
                json={"execution_ids": [eid1, eid2]},
            )

        data = resp.get_json()
        assert data["cancelled"] == 1
        assert data["failed"] == 1
        # Check detail structure
        detail_map = {d["execution_id"]: d for d in data["details"]}
        assert detail_map[eid1]["success"] is True
        assert detail_map[eid2]["success"] is False
        assert "status is success" in detail_map[eid2]["reason"]

    def test_paused_execution_shows_paused_in_get(self, client):
        """GET /admin/executions/<id> shows 'paused' status after pause."""
        eid = _seed_execution("exec-api-010")
        proc = _make_mock_process()
        ProcessManager.register(eid, proc, "trig-001")

        with patch("os.killpg"):
            client.post(f"/admin/executions/{eid}/pause")

        resp = client.get(f"/admin/executions/{eid}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "paused"


# ---------------------------------------------------------------------------
# get_execution_logs_filtered tests
# ---------------------------------------------------------------------------


class TestGetExecutionLogsFiltered:
    """Test the filtered execution log query helper."""

    def test_filter_by_status(self):
        """Filter returns only executions matching status."""
        _seed_execution("exec-filt-001", status="running")
        _seed_execution("exec-filt-002", status="success")

        results = get_execution_logs_filtered(status="running")
        ids = [r["execution_id"] for r in results]
        assert "exec-filt-001" in ids
        assert "exec-filt-002" not in ids

    def test_filter_by_trigger_id(self):
        """Filter returns only executions matching trigger_id."""
        _seed_execution("exec-filt-010", trigger_id="bot-security")
        _seed_execution("exec-filt-011", trigger_id="bot-pr-review")

        results = get_execution_logs_filtered(trigger_id="bot-security")
        ids = [r["execution_id"] for r in results]
        assert "exec-filt-010" in ids
        assert "exec-filt-011" not in ids

    def test_filter_combined(self):
        """Combined status + trigger_id filter works."""
        _seed_execution("exec-filt-020", trigger_id="bot-pr-review", status="running")
        _seed_execution("exec-filt-021", trigger_id="bot-pr-review", status="success")

        results = get_execution_logs_filtered(status="running", trigger_id="bot-pr-review")
        assert len(results) == 1
        assert results[0]["execution_id"] == "exec-filt-020"
