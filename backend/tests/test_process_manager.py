"""Tests for ProcessManager: subprocess tracking, cancellation, pause/resume."""

import signal
import subprocess
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app.services.process_manager import ProcessInfo, ProcessManager


@pytest.fixture(autouse=True)
def reset_process_manager():
    """Reset ProcessManager class-level state before and after each test."""
    ProcessManager._processes.clear()
    ProcessManager._cancelled.clear()
    yield
    ProcessManager._processes.clear()
    ProcessManager._cancelled.clear()


def _make_process(pid=1234, poll_return=None):
    """Create a mock subprocess.Popen."""
    proc = MagicMock(spec=subprocess.Popen)
    proc.pid = pid
    proc.poll.return_value = poll_return
    return proc


# ---------------------------------------------------------------------------
# ProcessInfo dataclass
# ---------------------------------------------------------------------------


class TestProcessInfo:
    def test_defaults(self):
        proc = _make_process()
        info = ProcessInfo(
            process=proc, pgid=100, execution_id="exec-1", trigger_id="trig-1"
        )
        assert info.paused_at is None
        assert info.pause_timer is None
        assert info.execution_id == "exec-1"
        assert info.trigger_id == "trig-1"
        assert info.pgid == 100


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_success(self, monkeypatch):
        proc = _make_process(pid=42)
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        assert "exec-1" in ProcessManager._processes
        info = ProcessManager._processes["exec-1"]
        assert info.pgid == 99
        assert info.process is proc
        assert info.trigger_id == "trig-1"

    def test_register_fallback_on_process_lookup_error(self, monkeypatch):
        proc = _make_process(pid=42)
        monkeypatch.setattr("os.getpgid", MagicMock(side_effect=ProcessLookupError))
        ProcessManager.register("exec-2", proc, "trig-2")

        info = ProcessManager._processes["exec-2"]
        assert info.pgid == 42  # Falls back to proc.pid

    def test_register_overwrites_existing(self, monkeypatch):
        monkeypatch.setattr("os.getpgid", lambda pid: pid)
        proc1 = _make_process(pid=10)
        proc2 = _make_process(pid=20)
        ProcessManager.register("exec-1", proc1, "trig-1")
        ProcessManager.register("exec-1", proc2, "trig-1")

        assert ProcessManager._processes["exec-1"].process is proc2


# ---------------------------------------------------------------------------
# cancel()
# ---------------------------------------------------------------------------


class TestCancel:
    def test_cancel_known_execution(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        killpg = MagicMock()
        monkeypatch.setattr("os.killpg", killpg)

        result = ProcessManager.cancel("exec-1")
        assert result is True
        killpg.assert_called_once_with(99, signal.SIGKILL)
        assert ProcessManager.is_cancelled("exec-1")

    def test_cancel_unknown_execution(self):
        result = ProcessManager.cancel("nonexistent")
        assert result is False
        # Still marks as cancelled even if not found
        assert ProcessManager.is_cancelled("nonexistent")

    def test_cancel_process_already_dead(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        monkeypatch.setattr("os.killpg", MagicMock(side_effect=ProcessLookupError))
        result = ProcessManager.cancel("exec-1")
        assert result is True  # Already dead counts as success

    def test_cancel_os_error(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        monkeypatch.setattr("os.killpg", MagicMock(side_effect=OSError("permission denied")))
        result = ProcessManager.cancel("exec-1")
        assert result is False


# ---------------------------------------------------------------------------
# cancel_graceful()
# ---------------------------------------------------------------------------


class TestCancelGraceful:
    def test_graceful_cancel_sends_sigterm(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        killpg = MagicMock()
        monkeypatch.setattr("os.killpg", killpg)

        # Patch Timer to prevent actual threads
        timer_mock = MagicMock()
        monkeypatch.setattr("threading.Timer", MagicMock(return_value=timer_mock))

        result = ProcessManager.cancel_graceful("exec-1")
        assert result is True
        killpg.assert_called_once_with(99, signal.SIGTERM)
        assert ProcessManager.is_cancelled("exec-1")

    def test_graceful_cancel_unknown_execution(self):
        result = ProcessManager.cancel_graceful("nonexistent")
        assert result is False

    def test_graceful_cancel_process_already_dead(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        monkeypatch.setattr("os.killpg", MagicMock(side_effect=ProcessLookupError))
        result = ProcessManager.cancel_graceful("exec-1")
        assert result is True

    def test_graceful_cancel_os_error(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        monkeypatch.setattr("os.killpg", MagicMock(side_effect=PermissionError("denied")))
        result = ProcessManager.cancel_graceful("exec-1")
        assert result is False

    def test_force_kill_timer_fires_when_process_alive(self, monkeypatch):
        """Verify the _force_kill closure works when process is still alive."""
        proc = _make_process(poll_return=None)  # poll() returns None => still running
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        killpg_calls = []
        monkeypatch.setattr("os.killpg", lambda pgid, sig: killpg_calls.append((pgid, sig)))

        # Use a very short timeout so the force-kill fires quickly
        result = ProcessManager.cancel_graceful("exec-1", sigterm_timeout=0.05)
        assert result is True

        # Wait for the timer to fire
        time.sleep(0.2)
        # Should have SIGTERM first, then SIGKILL
        assert (99, signal.SIGTERM) in killpg_calls
        assert (99, signal.SIGKILL) in killpg_calls

    def test_force_kill_timer_skips_when_process_exited(self, monkeypatch):
        """Verify the _force_kill closure skips kill when process already exited."""
        proc = _make_process(poll_return=0)  # poll() returns 0 => already exited
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        killpg_calls = []
        monkeypatch.setattr("os.killpg", lambda pgid, sig: killpg_calls.append((pgid, sig)))

        result = ProcessManager.cancel_graceful("exec-1", sigterm_timeout=0.05)
        assert result is True

        time.sleep(0.2)
        # Only SIGTERM, no SIGKILL since process already exited
        assert killpg_calls == [(99, signal.SIGTERM)]


# ---------------------------------------------------------------------------
# is_cancelled()
# ---------------------------------------------------------------------------


class TestIsCancelled:
    def test_not_cancelled_by_default(self):
        assert ProcessManager.is_cancelled("exec-1") is False

    def test_cancelled_after_cancel(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        monkeypatch.setattr("os.killpg", MagicMock())
        ProcessManager.register("exec-1", proc, "trig-1")
        ProcessManager.cancel("exec-1")
        assert ProcessManager.is_cancelled("exec-1") is True


# ---------------------------------------------------------------------------
# pause() / resume()
# ---------------------------------------------------------------------------


class TestPauseResume:
    def test_pause_success(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        killpg = MagicMock()
        monkeypatch.setattr("os.killpg", killpg)

        mock_cas = MagicMock(return_value=True)
        mock_broadcast = MagicMock()
        timer_instance = MagicMock()

        with patch(
            "app.db.triggers.update_execution_status_cas", mock_cas
        ), patch(
            "app.services.execution_log_service.ExecutionLogService._broadcast", mock_broadcast
        ), patch(
            "threading.Timer", return_value=timer_instance
        ):
            result = ProcessManager.pause("exec-1")

        assert result is True
        killpg.assert_any_call(99, signal.SIGSTOP)
        mock_cas.assert_called_once_with("exec-1", "paused", expected_status="running")
        info = ProcessManager._processes["exec-1"]
        assert info.paused_at is not None
        assert info.pause_timer is timer_instance

    def test_pause_unknown_execution(self):
        result_module = MagicMock()
        result_module.update_execution_status_cas = MagicMock(return_value=True)
        with patch.dict("sys.modules", {"app.db.triggers": result_module}):
            result = ProcessManager.pause("nonexistent")
        assert result is False

    def test_pause_cas_failure(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        mock_cas = MagicMock(return_value=False)
        with patch("app.db.triggers.update_execution_status_cas", mock_cas):
            result = ProcessManager.pause("exec-1")
        assert result is False

    def test_pause_process_lookup_error(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        monkeypatch.setattr("os.killpg", MagicMock(side_effect=ProcessLookupError))
        mock_cas = MagicMock(return_value=True)
        with patch("app.db.triggers.update_execution_status_cas", mock_cas):
            result = ProcessManager.pause("exec-1")
        assert result is False

    def test_resume_success(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        # Simulate paused state
        info = ProcessManager._processes["exec-1"]
        info.paused_at = time.time()
        timer_mock = MagicMock()
        info.pause_timer = timer_mock

        killpg = MagicMock()
        monkeypatch.setattr("os.killpg", killpg)

        mock_cas = MagicMock(return_value=True)
        mock_broadcast = MagicMock()
        with patch("app.db.triggers.update_execution_status_cas", mock_cas), patch(
            "app.services.execution_log_service.ExecutionLogService._broadcast", mock_broadcast
        ):
            result = ProcessManager.resume("exec-1")

        assert result is True
        killpg.assert_called_once_with(99, signal.SIGCONT)
        mock_cas.assert_called_once_with("exec-1", "running", expected_status="paused")
        timer_mock.cancel.assert_called_once()
        assert info.paused_at is None
        assert info.pause_timer is None

    def test_resume_unknown_execution(self):
        result_module = MagicMock()
        result_module.update_execution_status_cas = MagicMock(return_value=True)
        with patch.dict("sys.modules", {"app.db.triggers": result_module}):
            result = ProcessManager.resume("nonexistent")
        assert result is False

    def test_resume_cas_failure(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        mock_cas = MagicMock(return_value=False)
        with patch("app.db.triggers.update_execution_status_cas", mock_cas):
            result = ProcessManager.resume("exec-1")
        assert result is False

    def test_resume_process_lookup_error(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        monkeypatch.setattr("os.killpg", MagicMock(side_effect=ProcessLookupError))
        mock_cas = MagicMock(return_value=True)
        with patch("app.db.triggers.update_execution_status_cas", mock_cas):
            result = ProcessManager.resume("exec-1")
        assert result is False


# ---------------------------------------------------------------------------
# _auto_cancel_paused()
# ---------------------------------------------------------------------------


class TestAutoCancelPaused:
    def test_auto_cancel_sends_sigcont_then_sigterm(self, monkeypatch):
        proc = _make_process(poll_return=None)
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        killpg_calls = []
        monkeypatch.setattr("os.killpg", lambda pgid, sig: killpg_calls.append((pgid, sig)))

        mock_cas = MagicMock(return_value=True)
        timer_mock = MagicMock()
        with patch("app.db.triggers.update_execution_status_cas", mock_cas), patch(
            "threading.Timer", return_value=timer_mock
        ):
            ProcessManager._auto_cancel_paused("exec-1")

        mock_cas.assert_called_once_with("exec-1", "pause_timeout", expected_status="paused")
        assert (99, signal.SIGCONT) in killpg_calls
        assert (99, signal.SIGTERM) in killpg_calls
        assert ProcessManager.is_cancelled("exec-1")

    def test_auto_cancel_unknown_execution(self, monkeypatch):
        mock_cas = MagicMock(return_value=True)
        with patch("app.db.triggers.update_execution_status_cas", mock_cas):
            ProcessManager._auto_cancel_paused("nonexistent")
        mock_cas.assert_not_called()

    def test_auto_cancel_cas_failure(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        killpg = MagicMock()
        monkeypatch.setattr("os.killpg", killpg)

        mock_cas = MagicMock(return_value=False)
        with patch("app.db.triggers.update_execution_status_cas", mock_cas):
            ProcessManager._auto_cancel_paused("exec-1")

        killpg.assert_not_called()
        assert not ProcessManager.is_cancelled("exec-1")

    def test_auto_cancel_process_already_dead(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")

        monkeypatch.setattr("os.killpg", MagicMock(side_effect=ProcessLookupError))

        mock_cas = MagicMock(return_value=True)
        with patch("app.db.triggers.update_execution_status_cas", mock_cas):
            ProcessManager._auto_cancel_paused("exec-1")
        # Should return early after SIGCONT fails, not crash


# ---------------------------------------------------------------------------
# is_paused()
# ---------------------------------------------------------------------------


class TestIsPaused:
    def test_not_paused_by_default(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")
        assert ProcessManager.is_paused("exec-1") is False

    def test_unknown_execution_not_paused(self):
        assert ProcessManager.is_paused("nonexistent") is False

    def test_paused_when_paused_at_set(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")
        ProcessManager._processes["exec-1"].paused_at = time.time()
        assert ProcessManager.is_paused("exec-1") is True


# ---------------------------------------------------------------------------
# cleanup()
# ---------------------------------------------------------------------------


class TestCleanup:
    def test_cleanup_removes_process(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")
        ProcessManager._cancelled.add("exec-1")

        ProcessManager.cleanup("exec-1")
        assert "exec-1" not in ProcessManager._processes
        assert "exec-1" not in ProcessManager._cancelled

    def test_cleanup_cancels_pause_timer(self, monkeypatch):
        proc = _make_process()
        monkeypatch.setattr("os.getpgid", lambda pid: 99)
        ProcessManager.register("exec-1", proc, "trig-1")
        timer_mock = MagicMock()
        ProcessManager._processes["exec-1"].pause_timer = timer_mock

        ProcessManager.cleanup("exec-1")
        timer_mock.cancel.assert_called_once()

    def test_cleanup_nonexistent_is_noop(self):
        ProcessManager.cleanup("nonexistent")  # Should not raise


# ---------------------------------------------------------------------------
# get_active_count() / get_active_executions()
# ---------------------------------------------------------------------------


class TestActiveQueries:
    def test_get_active_count_empty(self):
        assert ProcessManager.get_active_count() == 0

    def test_get_active_count(self, monkeypatch):
        monkeypatch.setattr("os.getpgid", lambda pid: pid)
        ProcessManager.register("exec-1", _make_process(pid=1), "trig-1")
        ProcessManager.register("exec-2", _make_process(pid=2), "trig-2")
        assert ProcessManager.get_active_count() == 2

    def test_get_active_executions(self, monkeypatch):
        monkeypatch.setattr("os.getpgid", lambda pid: pid)
        ProcessManager.register("exec-1", _make_process(pid=1), "trig-1")
        ProcessManager.register("exec-2", _make_process(pid=2), "trig-2")
        result = ProcessManager.get_active_executions()
        assert sorted(result) == ["exec-1", "exec-2"]

    def test_get_active_executions_empty(self):
        assert ProcessManager.get_active_executions() == []


# ---------------------------------------------------------------------------
# cancel_all()
# ---------------------------------------------------------------------------


class TestCancelAll:
    def test_cancel_all_no_active_processes(self):
        ProcessManager.cancel_all()  # Should not raise

    def test_cancel_all_processes_complete(self, monkeypatch):
        monkeypatch.setattr("os.getpgid", lambda pid: pid)
        proc = _make_process(pid=1)
        proc.wait.return_value = 0
        ProcessManager.register("exec-1", proc, "trig-1")

        ProcessManager.cancel_all(timeout=5)
        proc.wait.assert_called_once()

    def test_cancel_all_force_kills_on_timeout(self, monkeypatch):
        monkeypatch.setattr("os.getpgid", lambda pid: pid)
        proc = _make_process(pid=1)
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=1)

        killpg = MagicMock()
        monkeypatch.setattr("os.killpg", killpg)
        ProcessManager.register("exec-1", proc, "trig-1")

        ProcessManager.cancel_all(timeout=1)
        killpg.assert_called_once_with(1, signal.SIGKILL)

    def test_cancel_all_handles_process_lookup_error(self, monkeypatch):
        monkeypatch.setattr("os.getpgid", lambda pid: pid)
        proc = _make_process(pid=1)
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=1)

        monkeypatch.setattr("os.killpg", MagicMock(side_effect=ProcessLookupError))
        ProcessManager.register("exec-1", proc, "trig-1")

        ProcessManager.cancel_all(timeout=1)  # Should not raise

    def test_cancel_all_multiple_processes(self, monkeypatch):
        monkeypatch.setattr("os.getpgid", lambda pid: pid)

        proc1 = _make_process(pid=1)
        proc1.wait.return_value = 0
        proc2 = _make_process(pid=2)
        proc2.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=1)

        killpg = MagicMock()
        monkeypatch.setattr("os.killpg", killpg)

        ProcessManager.register("exec-1", proc1, "trig-1")
        ProcessManager.register("exec-2", proc2, "trig-2")

        ProcessManager.cancel_all(timeout=2)
        proc1.wait.assert_called_once()
        proc2.wait.assert_called_once()
        killpg.assert_called_once_with(2, signal.SIGKILL)
