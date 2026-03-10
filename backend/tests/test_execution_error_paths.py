"""Tests for ExecutionService error paths: timeouts, pipe failures, rate limits, retries."""

import subprocess
import threading
from unittest.mock import MagicMock, patch, ANY

import pytest

from app.services.execution_service import ExecutionService, ExecutionState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_execution_service_state():
    """Reset class-level mutable state between tests."""
    ExecutionService._rate_limit_detected.clear()
    ExecutionService._transient_failure_detected.clear()
    ExecutionService._pending_retries.clear()
    for timer in ExecutionService._retry_timers.values():
        timer.cancel()
    ExecutionService._retry_timers.clear()
    ExecutionService._retry_counts.clear()
    yield
    ExecutionService._rate_limit_detected.clear()
    ExecutionService._transient_failure_detected.clear()
    ExecutionService._pending_retries.clear()
    for timer in ExecutionService._retry_timers.values():
        timer.cancel()
    ExecutionService._retry_timers.clear()
    ExecutionService._retry_counts.clear()


def _make_trigger(**overrides):
    """Build a minimal trigger dict with sensible defaults."""
    trigger = {
        "id": "trg-test01",
        "name": "Test Trigger",
        "trigger_source": "webhook",
        "backend_type": "claude",
        "prompt_template": "Analyze {message} at {paths}",
        "enabled": 1,
    }
    trigger.update(overrides)
    return trigger


def _mock_process(exit_code=0, wait_side_effect=None):
    """Create a mock subprocess.Popen with configurable behavior."""
    mock_proc = MagicMock(spec=subprocess.Popen)
    mock_proc.pid = 12345
    mock_proc.stdout = MagicMock()
    mock_proc.stdout.readline = MagicMock(return_value="")
    mock_proc.stderr = MagicMock()
    mock_proc.stderr.readline = MagicMock(return_value="")
    mock_proc.poll.return_value = exit_code
    if wait_side_effect:
        mock_proc.wait.side_effect = wait_side_effect
    else:
        mock_proc.wait.return_value = exit_code
    return mock_proc


def _standard_patches():
    """Return the set of patches commonly needed for run_trigger tests."""
    return {
        "paths": patch(
            "app.services.execution_service.get_paths_for_trigger_detailed", return_value=[]
        ),
        "log_svc": patch("app.services.execution_service.ExecutionLogService"),
        "audit": patch("app.services.execution_service.AuditLogService"),
        "budget": patch("app.services.execution_service.BudgetService"),
        "pm": patch("app.services.execution_service.ProcessManager"),
        "github": patch("app.services.execution_service.GitHubService"),
        "which": patch("shutil.which", return_value=None),
    }


# ---------------------------------------------------------------------------
# Subprocess timeout handling
# ---------------------------------------------------------------------------


class TestSubprocessTimeout:
    def test_timeout_expired_marks_timeout_status(self, isolated_db):
        """When subprocess.wait() raises TimeoutExpired, status should be TIMEOUT."""
        patches = _standard_patches()
        mock_proc = _mock_process(
            wait_side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=300)
        )

        with (
            patches["paths"],
            patches["log_svc"] as mock_log_svc,
            patches["audit"],
            patches["budget"] as mock_budget,
            patches["pm"],
            patches["github"],
            patches["which"],
            patch("subprocess.Popen", return_value=mock_proc),
            patch("threading.Thread") as mock_thread_cls,
        ):
            mock_budget.check_budget.return_value = {"allowed": True}
            mock_log_svc.start_execution.return_value = "exec-timeout"

            mock_thread = MagicMock()
            mock_thread.is_alive.return_value = False
            mock_thread_cls.return_value = mock_thread

            trigger = _make_trigger(timeout_seconds=1)
            result = ExecutionService.run_trigger(trigger, "test msg")

        assert result == "exec-timeout"
        finish_call = mock_log_svc.finish_execution.call_args
        assert finish_call[1]["status"] == ExecutionState.TIMEOUT
        assert "timed out" in finish_call[1]["error_message"]

    def test_timeout_kills_process_group(self, isolated_db):
        """On timeout, the process group should be killed via os.killpg."""
        patches = _standard_patches()
        mock_proc = _mock_process(
            wait_side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=300)
        )
        mock_proc.pid = 99999

        with (
            patches["paths"],
            patches["log_svc"] as mock_log_svc,
            patches["audit"],
            patches["budget"] as mock_budget,
            patches["pm"],
            patches["github"],
            patches["which"],
            patch("subprocess.Popen", return_value=mock_proc),
            patch("threading.Thread") as mock_thread_cls,
            patch("os.killpg") as mock_killpg,
            patch("os.getpgid", return_value=99999),
        ):
            mock_budget.check_budget.return_value = {"allowed": True}
            mock_log_svc.start_execution.return_value = "exec-kill"

            mock_thread = MagicMock()
            mock_thread.is_alive.return_value = False
            mock_thread_cls.return_value = mock_thread

            trigger = _make_trigger(timeout_seconds=1)
            ExecutionService.run_trigger(trigger, "test")

        mock_killpg.assert_called()


# ---------------------------------------------------------------------------
# Log streaming pipe failures (_stream_pipe)
# ---------------------------------------------------------------------------


class TestStreamPipeErrors:
    def test_oserror_in_stream_pipe_is_caught(self, isolated_db):
        """OSError during pipe reading should be caught, not crash the thread."""
        mock_pipe = MagicMock()
        mock_pipe.readline.side_effect = OSError("Broken pipe")

        with patch("app.services.execution_service.ExecutionLogService"):
            # Should not raise
            ExecutionService._stream_pipe("exec-pipe", "stdout", mock_pipe)

        mock_pipe.close.assert_called_once()

    def test_valueerror_in_stream_pipe_is_caught(self, isolated_db):
        """ValueError during pipe reading should be caught."""
        mock_pipe = MagicMock()
        mock_pipe.readline.side_effect = ValueError("I/O operation on closed file")

        with patch("app.services.execution_service.ExecutionLogService"):
            ExecutionService._stream_pipe("exec-pipe2", "stderr", mock_pipe)

        mock_pipe.close.assert_called_once()

    def test_unexpected_error_in_stream_pipe_is_caught(self, isolated_db):
        """Unexpected exceptions during pipe reading should be caught."""
        mock_pipe = MagicMock()
        mock_pipe.readline.side_effect = RuntimeError("unexpected")

        with patch("app.services.execution_service.ExecutionLogService"):
            ExecutionService._stream_pipe("exec-pipe3", "stdout", mock_pipe)

        mock_pipe.close.assert_called_once()

    def test_pipe_close_called_in_finally(self, isolated_db):
        """pipe.close() should always be called, even on success."""
        lines = iter(["line1\n", "line2\n", ""])
        mock_pipe = MagicMock()
        mock_pipe.readline.side_effect = lines

        with patch("app.services.execution_runner.ExecutionLogService") as mock_log:
            ExecutionService._stream_pipe("exec-ok", "stdout", mock_pipe)

        mock_pipe.close.assert_called_once()
        # Two lines should have been appended
        assert mock_log.append_log.call_count == 2


# ---------------------------------------------------------------------------
# Rate limit detection in stderr stream
# ---------------------------------------------------------------------------


class TestRateLimitDetection:
    def test_rate_limit_detected_in_stderr(self, isolated_db):
        """Rate limit patterns in stderr should populate _rate_limit_detected."""
        lines = iter(["rate limit hit, retry in 60s\n", ""])
        mock_pipe = MagicMock()
        mock_pipe.readline.side_effect = lines

        with (
            patch("app.services.execution_service.ExecutionLogService"),
            patch("app.services.execution_service.AuditLogService"),
            patch(
                "app.services.execution_runner.RateLimitService.check_stderr_line",
                return_value=60,
            ),
        ):
            ExecutionService._stream_pipe("exec-rl", "stderr", mock_pipe, "claude")

        assert ExecutionService._rate_limit_detected.get("exec-rl") == 60

    def test_no_rate_limit_when_not_stderr(self, isolated_db):
        """Rate limit checking should NOT happen on stdout stream."""
        lines = iter(["rate limit\n", ""])
        mock_pipe = MagicMock()
        mock_pipe.readline.side_effect = lines

        with (
            patch("app.services.execution_service.ExecutionLogService"),
            patch(
                "app.services.execution_runner.RateLimitService.check_stderr_line",
                return_value=60,
            ) as mock_check,
        ):
            ExecutionService._stream_pipe("exec-stdout", "stdout", mock_pipe, "claude")

        mock_check.assert_not_called()
        assert "exec-stdout" not in ExecutionService._rate_limit_detected


# ---------------------------------------------------------------------------
# Transient failure detection
# ---------------------------------------------------------------------------


class TestTransientFailureDetection:
    def test_transient_failure_detected_in_stderr(self, isolated_db):
        """Transient failures (502, timeout) should populate _transient_failure_detected."""
        lines = iter(["502 Bad Gateway\n", ""])
        mock_pipe = MagicMock()
        mock_pipe.readline.side_effect = lines

        with (
            patch("app.services.execution_service.ExecutionLogService"),
            patch("app.services.execution_service.AuditLogService"),
            patch(
                "app.services.execution_runner.RateLimitService.check_stderr_line",
                return_value=None,
            ),
            patch(
                "app.services.circuit_breaker_service.CircuitBreakerService.is_transient_error",
                return_value=True,
            ),
        ):
            ExecutionService._stream_pipe("exec-tf", "stderr", mock_pipe, "claude")

        assert ExecutionService._transient_failure_detected.get("exec-tf") == "502 Bad Gateway"

    def test_only_first_transient_failure_recorded(self, isolated_db):
        """Only the first transient error per execution should be recorded."""
        lines = iter(["502 Bad Gateway\n", "503 Service Unavailable\n", ""])
        mock_pipe = MagicMock()
        mock_pipe.readline.side_effect = lines

        with (
            patch("app.services.execution_service.ExecutionLogService"),
            patch("app.services.execution_service.AuditLogService"),
            patch(
                "app.services.execution_runner.RateLimitService.check_stderr_line",
                return_value=None,
            ),
            patch(
                "app.services.circuit_breaker_service.CircuitBreakerService.is_transient_error",
                return_value=True,
            ),
        ):
            ExecutionService._stream_pipe("exec-tf2", "stderr", mock_pipe, "claude")

        # Only first transient error should be recorded
        assert ExecutionService._transient_failure_detected["exec-tf2"] == "502 Bad Gateway"


# ---------------------------------------------------------------------------
# Rate limit retry scheduling
# ---------------------------------------------------------------------------


class TestRetryScheduling:
    def test_schedule_retry_creates_timer(self, isolated_db):
        """schedule_retry should create an active timer in _retry_timers."""
        trigger = _make_trigger()
        with (
            patch("app.services.audit_log_service.AuditLogService"),
            patch("app.services.execution_retry.upsert_pending_retry"),
        ):
            ExecutionService.schedule_retry(
                trigger=trigger,
                message_text="test",
                event=None,
                trigger_type="webhook",
                cooldown_seconds=10,
            )

        assert "trg-test01" in ExecutionService._retry_timers
        assert "trg-test01" in ExecutionService._pending_retries
        # Cancel the timer to prevent it from firing during test teardown
        ExecutionService._retry_timers["trg-test01"].cancel()

    def test_schedule_retry_replaces_existing_timer(self, isolated_db):
        """A new retry should cancel the existing timer for the same trigger."""
        trigger = _make_trigger()
        with (
            patch("app.services.audit_log_service.AuditLogService"),
            patch("app.services.execution_retry.upsert_pending_retry"),
        ):
            ExecutionService.schedule_retry(trigger, "msg1", None, "webhook", 10)
            first_timer = ExecutionService._retry_timers["trg-test01"]

            ExecutionService.schedule_retry(trigger, "msg2", None, "webhook", 20)
            second_timer = ExecutionService._retry_timers["trg-test01"]

        assert first_timer is not second_timer
        # First timer should have been cancelled
        assert first_timer.finished.is_set() or not first_timer.is_alive()
        second_timer.cancel()

    def test_schedule_retry_exceeds_max_attempts(self, isolated_db):
        """After MAX_RETRY_ATTEMPTS, schedule_retry should give up."""
        trigger = _make_trigger()
        ExecutionService._retry_counts["trg-test01"] = 100  # Well above max

        with (
            patch("app.services.audit_log_service.AuditLogService"),
            patch("app.services.execution_log_service.ExecutionLogService") as mock_log,
            patch("app.services.execution_retry.upsert_pending_retry"),
            patch("app.services.execution_retry.delete_pending_retry"),
        ):
            mock_log.start_execution.return_value = "exec-exhaust"
            ExecutionService.schedule_retry(trigger, "msg", None, "webhook", 10)

        # Should NOT have created a timer
        assert "trg-test01" not in ExecutionService._retry_timers
        # Should have created a terminal failure execution record
        mock_log.finish_execution.assert_called_once()
        call_kwargs = mock_log.finish_execution.call_args[1]
        assert call_kwargs["status"] == ExecutionState.FAILED
        assert "exhausted" in call_kwargs["error_message"].lower()

    def test_pending_retries_snapshot(self, isolated_db):
        """get_pending_retries should return in-memory state merged with DB."""
        ExecutionService._pending_retries["trg-mem"] = {
            "trigger_id": "trg-mem",
            "cooldown_seconds": 30,
        }
        with patch(
            "app.services.execution_retry.get_all_pending_retries",
            return_value=[
                {
                    "trigger_id": "trg-db",
                    "cooldown_seconds": 60,
                    "retry_at": "2026-01-01T00:00:00",
                    "created_at": "2026-01-01T00:00:00",
                }
            ],
        ):
            result = ExecutionService.get_pending_retries()

        assert "trg-mem" in result
        assert "trg-db" in result


# ---------------------------------------------------------------------------
# Budget exceeded mid-execution (_budget_monitor)
# ---------------------------------------------------------------------------


class TestBudgetMonitor:
    def test_budget_exceeded_kills_process(self, isolated_db):
        """When budget check fails mid-execution, process should be killed."""
        mock_proc = MagicMock()
        # Process is running for the first poll, then dead after kill
        mock_proc.poll.side_effect = [None, None, 0]
        mock_proc.pid = 11111

        with (
            patch("app.services.execution_runner.BudgetService") as mock_budget,
            patch("app.services.execution_runner.ExecutionLogService") as mock_log,
            patch("app.services.execution_runner.AuditLogService"),
            patch("os.killpg") as mock_killpg,
            patch("os.getpgid", return_value=11111),
            patch("time.sleep"),  # Don't actually sleep
        ):
            mock_budget.check_budget.return_value = {
                "allowed": False,
                "reason": "hard limit reached",
            }

            ExecutionService._budget_monitor(
                "exec-bm", "trg-test01", "trigger", "trg-test01", mock_proc, interval_seconds=0
            )

        mock_killpg.assert_called()
        mock_log.append_log.assert_called()
        # Verify the log message mentions budget
        log_calls = [str(c) for c in mock_log.append_log.call_args_list]
        assert any("BUDGET" in c for c in log_calls)

    def test_budget_monitor_exits_when_process_completes(self, isolated_db):
        """Budget monitor should exit when process.poll() returns non-None."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # Already exited

        with (
            patch("app.services.execution_runner.BudgetService") as mock_budget,
            patch("app.services.execution_runner.ExecutionLogService"),
            patch("app.services.execution_runner.AuditLogService"),
        ):
            # Should return immediately since process is already done
            ExecutionService._budget_monitor(
                "exec-done", "trg-t", "trigger", "trg-t", mock_proc, interval_seconds=0
            )

        # Budget check should not have been called since process already exited
        mock_budget.check_budget.assert_not_called()

    def test_budget_monitor_exception_is_swallowed(self, isolated_db):
        """Exceptions in budget check should be caught and not crash the monitor."""
        mock_proc = MagicMock()
        # Run once, then exit
        mock_proc.poll.side_effect = [None, 0]

        with (
            patch("app.services.execution_runner.BudgetService") as mock_budget,
            patch("app.services.execution_runner.ExecutionLogService"),
            patch("app.services.execution_runner.AuditLogService"),
            patch("time.sleep"),
        ):
            mock_budget.check_budget.side_effect = RuntimeError("DB error")
            # Should not raise
            ExecutionService._budget_monitor(
                "exec-err", "trg-t", "trigger", "trg-t", mock_proc, interval_seconds=0
            )


# ---------------------------------------------------------------------------
# _match_payload edge cases
# ---------------------------------------------------------------------------


class TestMatchPayloadEdgeCases:
    def test_empty_payload(self):
        """Empty payload with default config should return empty string."""
        result = ExecutionService._match_payload({}, {})
        assert result == ""

    def test_nested_field_path(self):
        """Nested text_field_path should traverse the payload."""
        config = {"text_field_path": "data.message"}
        payload = {"data": {"message": "nested value"}}
        result = ExecutionService._match_payload(config, payload)
        assert result == "nested value"

    def test_match_field_with_none_value(self):
        """match_field_path with None actual value should not match."""
        config = {"match_field_path": "type", "match_field_value": "alert"}
        payload = {"text": "hello"}  # 'type' key missing
        result = ExecutionService._match_payload(config, payload)
        assert result is None

    def test_match_field_both_empty(self):
        """Empty match_field_path and match_field_value should skip matching."""
        config = {"match_field_path": "", "match_field_value": ""}
        payload = {"text": "hello"}
        result = ExecutionService._match_payload(config, payload)
        assert result == "hello"

    def test_detection_keyword_empty_string(self):
        """Empty detection_keyword should not filter anything."""
        config = {"detection_keyword": ""}
        payload = {"text": "normal message"}
        result = ExecutionService._match_payload(config, payload)
        assert result == "normal message"

    def test_boolean_text_field_converted_to_string(self):
        """Boolean values in text field should be converted to string."""
        config = {"text_field_path": "flag"}
        payload = {"flag": True}
        result = ExecutionService._match_payload(config, payload)
        assert result == "True"

    def test_list_text_field_converted_to_string(self):
        """List values in text field should be converted to string."""
        config = {"text_field_path": "items"}
        payload = {"items": [1, 2, 3]}
        result = ExecutionService._match_payload(config, payload)
        assert result == "[1, 2, 3]"

    def test_match_field_numeric_comparison(self):
        """Numeric match_field_value should compare as strings."""
        config = {"match_field_path": "code", "match_field_value": "200"}
        payload = {"code": 200, "text": "ok"}
        result = ExecutionService._match_payload(config, payload)
        assert result == "ok"

    def test_detection_keyword_case_sensitive(self):
        """detection_keyword matching should be case-sensitive."""
        config = {"detection_keyword": "CRITICAL"}
        payload = {"text": "critical issue"}
        result = ExecutionService._match_payload(config, payload)
        assert result is None


# ---------------------------------------------------------------------------
# FileNotFoundError when CLI binary not found
# ---------------------------------------------------------------------------


class TestCLINotFound:
    def test_file_not_found_error_with_opencode_backend(self, isolated_db):
        """FileNotFoundError for non-claude backends should still be handled."""
        patches = _standard_patches()

        with (
            patches["paths"],
            patches["log_svc"] as mock_log_svc,
            patches["audit"],
            patches["budget"] as mock_budget,
            patches["pm"],
            patches["github"],
            patches["which"],
            patch("subprocess.Popen", side_effect=FileNotFoundError("opencode not found")),
        ):
            mock_log_svc.start_execution.return_value = "exec-oc"
            mock_budget.check_budget.return_value = {"allowed": True}

            trigger = _make_trigger(backend_type="opencode")
            result = ExecutionService.run_trigger(trigger, "test")

        assert result == "exec-oc"
        finish_call = mock_log_svc.finish_execution.call_args
        assert finish_call[1]["status"] == ExecutionState.FAILED
        assert "not found" in finish_call[1]["error_message"]

    def test_generic_exception_preserves_error_message(self, isolated_db):
        """Generic exceptions should preserve the error message in the execution record."""
        patches = _standard_patches()

        with (
            patches["paths"],
            patches["log_svc"] as mock_log_svc,
            patches["audit"],
            patches["budget"] as mock_budget,
            patches["pm"],
            patches["github"],
            patches["which"],
            patch("subprocess.Popen", side_effect=PermissionError("Permission denied")),
        ):
            mock_log_svc.start_execution.return_value = "exec-perm"
            mock_budget.check_budget.return_value = {"allowed": True}

            trigger = _make_trigger()
            result = ExecutionService.run_trigger(trigger, "test")

        assert result == "exec-perm"
        finish_call = mock_log_svc.finish_execution.call_args
        assert finish_call[1]["status"] == ExecutionState.FAILED
        assert "Permission denied" in finish_call[1]["error_message"]


# ---------------------------------------------------------------------------
# Disabled trigger dispatching
# ---------------------------------------------------------------------------


class TestDisabledTrigger:
    @patch("app.services.trigger_dispatcher.get_webhook_triggers", return_value=[])
    def test_disabled_triggers_not_returned_by_query(self, mock_get, isolated_db):
        """Disabled triggers should be filtered out at the DB query level (enabled=1)."""
        with patch("app.database.get_webhook_teams", return_value=[]):
            result = ExecutionService.dispatch_webhook_event({"text": "test"})
        assert result is False
        # get_webhook_triggers only returns enabled triggers; disabled ones aren't dispatched


# ---------------------------------------------------------------------------
# Cancelled execution detection
# ---------------------------------------------------------------------------


class TestCancelledExecution:
    def test_cancelled_execution_marks_cancelled_status(self, isolated_db):
        """When ProcessManager.is_cancelled returns True, status should be CANCELLED."""
        patches = _standard_patches()
        mock_proc = _mock_process(exit_code=-9)

        with (
            patches["paths"],
            patches["log_svc"] as mock_log_svc,
            patches["audit"],
            patches["budget"] as mock_budget,
            patches["pm"] as mock_pm,
            patches["github"],
            patches["which"],
            patch("subprocess.Popen", return_value=mock_proc),
            patch("threading.Thread") as mock_thread_cls,
        ):
            mock_budget.check_budget.return_value = {"allowed": True}
            mock_log_svc.start_execution.return_value = "exec-cancel"
            mock_pm.is_cancelled.return_value = True

            mock_thread = MagicMock()
            mock_thread.is_alive.return_value = False
            mock_thread_cls.return_value = mock_thread

            trigger = _make_trigger()
            result = ExecutionService.run_trigger(trigger, "test")

        assert result == "exec-cancel"
        finish_call = mock_log_svc.finish_execution.call_args
        assert finish_call[1]["status"] == ExecutionState.CANCELLED


# ---------------------------------------------------------------------------
# Incomplete output warnings (thread still alive after join)
# ---------------------------------------------------------------------------


class TestIncompleteOutput:
    def test_thread_still_alive_logs_warning(self, isolated_db):
        """When reader threads don't exit after join, a warning should be appended."""
        patches = _standard_patches()
        mock_proc = _mock_process(exit_code=0)

        with (
            patches["paths"],
            patches["log_svc"] as mock_log_svc,
            patches["audit"],
            patches["budget"] as mock_budget,
            patches["pm"] as mock_pm,
            patches["github"],
            patches["which"],
            patch("subprocess.Popen", return_value=mock_proc),
            patch("threading.Thread") as mock_thread_cls,
        ):
            mock_budget.check_budget.return_value = {"allowed": True}
            mock_budget.extract_token_usage.return_value = None
            mock_log_svc.start_execution.return_value = "exec-alive"
            mock_log_svc.get_stdout_log.return_value = ""
            mock_pm.is_cancelled.return_value = False

            mock_thread = MagicMock()
            mock_thread.is_alive.return_value = True  # Thread stuck
            mock_thread_cls.return_value = mock_thread

            trigger = _make_trigger()
            ExecutionService.run_trigger(trigger, "test")

        # Check that warning about incomplete output was appended
        log_calls = [str(c) for c in mock_log_svc.append_log.call_args_list]
        assert any("incomplete" in c.lower() for c in log_calls)


# ---------------------------------------------------------------------------
# restore_pending_retries
# ---------------------------------------------------------------------------


class TestRestorePendingRetries:
    def test_restore_with_empty_db(self, isolated_db):
        """Restore with no DB rows should return 0."""
        with patch("app.services.execution_retry.get_all_pending_retries", return_value=[]):
            count = ExecutionService.restore_pending_retries()
        assert count == 0

    def test_restore_db_error(self, isolated_db):
        """DB error during restore should return 0 without crashing."""
        with patch(
            "app.services.execution_retry.get_all_pending_retries",
            side_effect=RuntimeError("DB corrupt"),
        ):
            count = ExecutionService.restore_pending_retries()
        assert count == 0

    def test_restore_creates_timers(self, isolated_db):
        """Valid DB rows should create in-memory timers."""
        import datetime
        import json

        retry_at = (datetime.datetime.now() + datetime.timedelta(seconds=30)).isoformat()
        trigger = _make_trigger()

        rows = [
            {
                "trigger_id": "trg-test01",
                "trigger_json": json.dumps(trigger),
                "message_text": "test",
                "event_json": "{}",
                "trigger_type": "webhook",
                "cooldown_seconds": 10,
                "retry_at": retry_at,
                "created_at": datetime.datetime.now().isoformat(),
            }
        ]

        with (
            patch("app.services.execution_retry.get_all_pending_retries", return_value=rows),
            patch("app.services.execution_retry.delete_pending_retry"),
        ):
            count = ExecutionService.restore_pending_retries()

        assert count == 1
        assert "trg-test01" in ExecutionService._retry_timers
        assert "trg-test01" in ExecutionService._pending_retries
        # Cleanup
        ExecutionService._retry_timers["trg-test01"].cancel()
