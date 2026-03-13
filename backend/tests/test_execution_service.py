"""Tests for ExecutionService: command building, dispatch, token usage, error paths."""

import json
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
    # Cancel any lingering timers
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


# ---------------------------------------------------------------------------
# build_command (delegates to CommandBuilder)
# ---------------------------------------------------------------------------


class TestBuildCommand:
    def test_claude_default(self):
        cmd = ExecutionService.build_command("claude", "hello world")
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "hello world" in cmd
        assert "--verbose" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd

    def test_claude_with_paths(self):
        cmd = ExecutionService.build_command("claude", "prompt", allowed_paths=["/a", "/b"])
        add_dir_indices = [i for i, v in enumerate(cmd) if v == "--add-dir"]
        assert len(add_dir_indices) == 2

    def test_claude_with_model(self):
        cmd = ExecutionService.build_command("claude", "prompt", model="sonnet")
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "sonnet"

    def test_claude_with_allowed_tools(self):
        cmd = ExecutionService.build_command("claude", "prompt", allowed_tools="Read,Grep")
        idx = cmd.index("--allowedTools")
        assert cmd[idx + 1] == "Read,Grep"

    def test_claude_default_allowed_tools(self):
        cmd = ExecutionService.build_command("claude", "prompt")
        idx = cmd.index("--allowedTools")
        assert cmd[idx + 1] == "Read,Glob,Grep,Bash"

    def test_opencode_backend(self):
        cmd = ExecutionService.build_command("opencode", "run this")
        assert cmd[0] == "opencode"
        assert "run" in cmd
        assert "run this" in cmd

    def test_opencode_with_model(self):
        cmd = ExecutionService.build_command("opencode", "prompt", model="gpt-4")
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "gpt-4"

    def test_gemini_backend(self):
        cmd = ExecutionService.build_command("gemini", "analyze")
        assert cmd[0] == "gemini"
        assert "-p" in cmd
        assert "analyze" in cmd

    def test_gemini_with_paths(self):
        cmd = ExecutionService.build_command("gemini", "analyze", allowed_paths=["/src"])
        assert "--include-directories" in cmd

    def test_codex_backend(self):
        cmd = ExecutionService.build_command("codex", "fix bugs")
        assert cmd[0] == "codex"
        assert "exec" in cmd
        assert "--full-auto" in cmd
        assert "fix bugs" in cmd

    def test_codex_with_reasoning(self):
        cmd = ExecutionService.build_command(
            "codex", "fix", codex_settings={"reasoning_level": "high"}
        )
        assert "--reasoning-effort" in cmd
        idx = cmd.index("--reasoning-effort")
        assert cmd[idx + 1] == "high"

    def test_codex_invalid_reasoning_ignored(self):
        cmd = ExecutionService.build_command(
            "codex", "fix", codex_settings={"reasoning_level": "ultra"}
        )
        assert "--reasoning-effort" not in cmd


# ---------------------------------------------------------------------------
# build_resolve_command
# ---------------------------------------------------------------------------


class TestBuildResolveCommand:
    def test_basic_resolve_command(self):
        cmd = ExecutionService.build_resolve_command("vuln summary", ["/app"])
        assert cmd[0] == "claude"
        assert "--allowedTools" in cmd
        idx = cmd.index("--allowedTools")
        assert "Edit" in cmd[idx + 1]
        assert "Write" in cmd[idx + 1]
        assert "--add-dir" in cmd

    def test_resolve_command_multiple_paths(self):
        cmd = ExecutionService.build_resolve_command("summary", ["/a", "/b", "/c"])
        add_dir_count = cmd.count("--add-dir")
        assert add_dir_count == 3


# ---------------------------------------------------------------------------
# _match_payload
# ---------------------------------------------------------------------------


class TestMatchPayload:
    def test_match_with_text_field(self):
        config = {"text_field_path": "body"}
        payload = {"body": "hello world"}
        result = ExecutionService._match_payload(config, payload)
        assert result == "hello world"

    def test_match_default_text_field(self):
        config = {}
        payload = {"text": "default text"}
        result = ExecutionService._match_payload(config, payload)
        assert result == "default text"

    def test_match_field_value_mismatch(self):
        config = {"match_field_path": "type", "match_field_value": "alert"}
        payload = {"type": "info", "text": "some text"}
        result = ExecutionService._match_payload(config, payload)
        assert result is None

    def test_match_field_value_match(self):
        config = {"match_field_path": "type", "match_field_value": "alert"}
        payload = {"type": "alert", "text": "danger"}
        result = ExecutionService._match_payload(config, payload)
        assert result == "danger"

    def test_detection_keyword_present(self):
        config = {"detection_keyword": "CRITICAL"}
        payload = {"text": "CRITICAL vulnerability found"}
        result = ExecutionService._match_payload(config, payload)
        assert result == "CRITICAL vulnerability found"

    def test_detection_keyword_absent(self):
        config = {"detection_keyword": "CRITICAL"}
        payload = {"text": "minor issue"}
        result = ExecutionService._match_payload(config, payload)
        assert result is None

    def test_missing_text_field_returns_empty(self):
        config = {"text_field_path": "nonexistent"}
        payload = {"other": "data"}
        result = ExecutionService._match_payload(config, payload)
        assert result == ""

    def test_non_string_text_converted(self):
        config = {"text_field_path": "count"}
        payload = {"count": 42}
        result = ExecutionService._match_payload(config, payload)
        assert result == "42"


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_idle_when_no_execution(self):
        status = ExecutionService.get_status("nonexistent-trigger")
        assert status["status"] == ExecutionState.IDLE

    @patch("app.services.execution_service.get_latest_execution_for_trigger")
    def test_status_from_running_execution(self, mock_get_latest):
        mock_get_latest.return_value = {
            "status": "running",
            "started_at": "2024-01-01T00:00:00",
            "finished_at": None,
            "error_message": None,
            "execution_id": "exec-abc123",
        }
        status = ExecutionService.get_status("trg-test01")
        assert status["status"] == ExecutionState.RUNNING
        assert status["execution_id"] == "exec-abc123"

    @patch("app.services.execution_service.get_latest_execution_for_trigger")
    def test_status_from_finished_execution(self, mock_get_latest):
        mock_get_latest.return_value = {
            "status": "success",
            "started_at": "2024-01-01T00:00:00",
            "finished_at": "2024-01-01T00:05:00",
            "error_message": None,
            "execution_id": "exec-done01",
        }
        status = ExecutionService.get_status("trg-test01")
        assert status["status"] == ExecutionState.SUCCESS
        assert status["execution_id"] == "exec-done01"


# ---------------------------------------------------------------------------
# was_rate_limited / was_transient_failure
# ---------------------------------------------------------------------------


class TestRateLimitTracking:
    def test_was_rate_limited_returns_none_for_unknown(self):
        assert ExecutionService.was_rate_limited("unknown-exec") is None

    def test_was_rate_limited_returns_none_for_empty_id(self):
        assert ExecutionService.was_rate_limited("") is None
        assert ExecutionService.was_rate_limited(None) is None

    def test_was_rate_limited_pops_entry(self):
        ExecutionService._rate_limit_detected["exec-1"] = 60
        assert ExecutionService.was_rate_limited("exec-1") == 60
        # Second call returns None (popped)
        assert ExecutionService.was_rate_limited("exec-1") is None

    def test_was_transient_failure_returns_none_for_unknown(self):
        assert ExecutionService.was_transient_failure("unknown") is None

    def test_was_transient_failure_pops_entry(self):
        ExecutionService._transient_failure_detected["exec-2"] = "502 Bad Gateway"
        assert ExecutionService.was_transient_failure("exec-2") == "502 Bad Gateway"
        assert ExecutionService.was_transient_failure("exec-2") is None


# ---------------------------------------------------------------------------
# dispatch_webhook_event
# ---------------------------------------------------------------------------


class TestDispatchWebhookEvent:
    @patch("app.services.trigger_dispatcher.get_webhook_triggers", return_value=[])
    def test_no_matching_triggers_returns_false(self, mock_triggers, isolated_db):
        with patch("app.database.get_webhook_teams", return_value=[]):
            result = ExecutionService.dispatch_webhook_event({"text": "hello"})
        assert result is False

    @patch("app.services.execution_service.ExecutionService.save_trigger_event")
    @patch("app.services.trigger_dispatcher.check_and_insert_dedup_key", return_value=True)
    @patch("app.services.trigger_dispatcher.get_webhook_triggers")
    def test_matching_trigger_dispatches(
        self, mock_get_triggers, mock_dedup, mock_save, isolated_db
    ):
        trigger = _make_trigger(
            text_field_path="body",
            detection_keyword="",
        )
        mock_get_triggers.return_value = [trigger]

        with (
            patch(
                "app.services.execution_queue_service.ExecutionQueueService.enqueue"
            ) as mock_enqueue,
            patch("app.database.get_webhook_teams", return_value=[]),
        ):
            result = ExecutionService.dispatch_webhook_event({"body": "test message"})

        assert result is True
        mock_enqueue.assert_called_once()

    @patch("app.services.execution_service.ExecutionService.save_trigger_event")
    @patch("app.services.trigger_dispatcher.check_and_insert_dedup_key", return_value=False)
    @patch("app.services.trigger_dispatcher.get_webhook_triggers")
    def test_dedup_skips_duplicate(self, mock_get_triggers, mock_dedup, mock_save, isolated_db):
        trigger = _make_trigger(text_field_path="body")
        mock_get_triggers.return_value = [trigger]

        with (
            patch(
                "app.services.execution_queue_service.ExecutionQueueService.enqueue"
            ) as mock_enqueue,
            patch("app.database.get_webhook_teams", return_value=[]),
        ):
            result = ExecutionService.dispatch_webhook_event({"body": "test"})

        assert result is False
        mock_enqueue.assert_not_called()

    @patch("app.services.execution_service.ExecutionService.save_trigger_event")
    @patch("app.services.trigger_dispatcher.check_and_insert_dedup_key", return_value=True)
    @patch("app.services.trigger_dispatcher.get_webhook_triggers")
    def test_hmac_validation_failure_skips_trigger(
        self, mock_get_triggers, mock_dedup, mock_save, isolated_db
    ):
        trigger = _make_trigger(webhook_secret="my-secret")
        mock_get_triggers.return_value = [trigger]

        with (
            patch(
                "app.services.webhook_validation_service.WebhookValidationService.validate_signature",
                return_value=False,
            ),
            patch("app.database.get_webhook_teams", return_value=[]),
        ):
            result = ExecutionService.dispatch_webhook_event(
                {"text": "test"},
                raw_payload=b'{"text":"test"}',
                signature_header="sha256=bad",
            )

        assert result is False


# ---------------------------------------------------------------------------
# dispatch_github_event
# ---------------------------------------------------------------------------


class TestDispatchGithubEvent:
    @patch("app.services.trigger_dispatcher.get_triggers_by_trigger_source", return_value=[])
    def test_no_github_triggers(self, mock_get, isolated_db):
        with patch("app.database.get_teams_by_trigger_source", return_value=[]):
            result = ExecutionService.dispatch_github_event(
                "https://github.com/owner/repo",
                {
                    "pr_number": 1,
                    "pr_title": "Test",
                    "pr_url": "https://github.com/owner/repo/pull/1",
                    "pr_author": "user",
                    "repo_full_name": "owner/repo",
                    "action": "opened",
                },
            )
        assert result is False

    @patch("app.services.execution_service.ExecutionService.save_trigger_event")
    @patch("app.services.trigger_dispatcher.get_triggers_by_trigger_source")
    def test_github_trigger_dispatches(self, mock_get_triggers, mock_save, isolated_db):
        trigger = _make_trigger(trigger_source="github")
        mock_get_triggers.return_value = [trigger]

        pr_data = {
            "pr_number": 42,
            "pr_title": "Fix bug",
            "pr_url": "https://github.com/o/r/pull/42",
            "pr_author": "dev",
            "repo_full_name": "o/r",
            "action": "opened",
        }

        with (
            patch(
                "app.services.execution_queue_service.ExecutionQueueService.enqueue"
            ) as mock_enqueue,
            patch("app.database.get_teams_by_trigger_source", return_value=[]),
        ):
            result = ExecutionService.dispatch_github_event("https://github.com/o/r", pr_data)

        assert result is True
        mock_enqueue.assert_called_once()
        call_kwargs = mock_enqueue.call_args
        assert call_kwargs[1]["trigger_type"] == "github"


# ---------------------------------------------------------------------------
# run_trigger -- error paths (subprocess mocked)
# ---------------------------------------------------------------------------


class TestRunTriggerErrorPaths:
    @patch("app.services.execution_service.ProcessManager")
    @patch("app.services.execution_service.BudgetService")
    @patch("app.services.execution_service.AuditLogService")
    @patch("app.services.execution_service.ExecutionLogService")
    @patch("app.services.execution_service.get_paths_for_trigger_detailed", return_value=[])
    @patch("subprocess.Popen", side_effect=FileNotFoundError("claude not found"))
    def test_file_not_found_marks_failed(
        self,
        mock_popen,
        mock_paths,
        mock_log_svc,
        mock_audit,
        mock_budget,
        mock_pm,
        isolated_db,
    ):
        mock_log_svc.start_execution.return_value = "exec-001"
        mock_budget.check_budget.return_value = {"allowed": True}
        trigger = _make_trigger()

        result = ExecutionService.run_trigger(trigger, "test message")

        assert result == "exec-001"
        mock_log_svc.finish_execution.assert_called_once()
        call_kwargs = mock_log_svc.finish_execution.call_args
        assert call_kwargs[1]["status"] == ExecutionState.FAILED
        assert "not found" in call_kwargs[1]["error_message"]

    @patch("app.services.execution_service.ProcessManager")
    @patch("app.services.execution_service.BudgetService")
    @patch("app.services.execution_service.AuditLogService")
    @patch("app.services.execution_service.ExecutionLogService")
    @patch("app.services.execution_service.get_paths_for_trigger_detailed", return_value=[])
    @patch("subprocess.Popen", side_effect=RuntimeError("unexpected error"))
    def test_generic_exception_marks_failed(
        self,
        mock_popen,
        mock_paths,
        mock_log_svc,
        mock_audit,
        mock_budget,
        mock_pm,
        isolated_db,
    ):
        mock_log_svc.start_execution.return_value = "exec-002"
        mock_budget.check_budget.return_value = {"allowed": True}
        trigger = _make_trigger()

        result = ExecutionService.run_trigger(trigger, "test")

        assert result == "exec-002"
        mock_log_svc.finish_execution.assert_called_once()
        call_kwargs = mock_log_svc.finish_execution.call_args
        assert call_kwargs[1]["status"] == ExecutionState.FAILED

    @patch("app.services.execution_service.ProcessManager")
    @patch("app.services.execution_service.BudgetService")
    @patch("app.services.execution_service.AuditLogService")
    @patch("app.services.execution_service.ExecutionLogService")
    @patch("app.services.execution_service.get_paths_for_trigger_detailed", return_value=[])
    def test_budget_blocked_aborts_execution(
        self,
        mock_paths,
        mock_log_svc,
        mock_audit,
        mock_budget,
        mock_pm,
        isolated_db,
    ):
        mock_log_svc.start_execution.return_value = "exec-003"
        mock_budget.check_budget.return_value = {
            "allowed": False,
            "reason": "hard limit reached",
            "limit": {"period": "monthly", "hard_limit_usd": 10.0},
            "current_spend": 12.0,
        }
        trigger = _make_trigger()

        result = ExecutionService.run_trigger(trigger, "test")

        assert result == "exec-003"
        mock_log_svc.finish_execution.assert_called_once()
        call_kwargs = mock_log_svc.finish_execution.call_args
        assert call_kwargs[1]["status"] == ExecutionState.FAILED
        assert "Budget limit exceeded" in call_kwargs[1]["error_message"]


# ---------------------------------------------------------------------------
# run_trigger -- successful execution with token usage extraction
# ---------------------------------------------------------------------------


class TestRunTriggerSuccess:
    @patch("app.services.execution_service.GitHubService")
    @patch("app.services.execution_service.ProcessManager")
    @patch("app.services.execution_service.BudgetService")
    @patch("app.services.execution_service.AuditLogService")
    @patch("app.services.execution_service.ExecutionLogService")
    @patch("app.services.execution_service.get_paths_for_trigger_detailed", return_value=[])
    @patch("shutil.which", return_value=None)
    def test_successful_execution_records_token_usage(
        self,
        mock_which,
        mock_paths,
        mock_log_svc,
        mock_audit,
        mock_budget,
        mock_pm,
        mock_github,
        isolated_db,
    ):
        mock_log_svc.start_execution.return_value = "exec-ok"
        mock_budget.check_budget.return_value = {"allowed": True}
        mock_budget.extract_token_usage.return_value = {
            "input_tokens": 100,
            "output_tokens": 50,
        }
        mock_log_svc.get_stdout_log.return_value = '{"usage": {"input_tokens": 100}}'
        mock_pm.is_cancelled.return_value = False

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.wait.return_value = 0
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = MagicMock(return_value="")
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.readline = MagicMock(return_value="")
        mock_proc.poll.return_value = 0

        with (
            patch("subprocess.Popen", return_value=mock_proc),
            patch("threading.Thread") as mock_thread_cls,
        ):
            mock_thread = MagicMock()
            mock_thread.is_alive.return_value = False
            mock_thread_cls.return_value = mock_thread

            trigger = _make_trigger()
            result = ExecutionService.run_trigger(trigger, "scan this")

        assert result == "exec-ok"
        mock_budget.extract_token_usage.assert_called_once()
        mock_budget.record_usage.assert_called_once()
        call_kwargs = mock_budget.record_usage.call_args[1]
        assert call_kwargs["execution_id"] == "exec-ok"
        assert call_kwargs["backend_type"] == "claude"

    @patch("app.services.execution_service.GitHubService")
    @patch("app.services.execution_service.ProcessManager")
    @patch("app.services.execution_service.BudgetService")
    @patch("app.services.execution_service.AuditLogService")
    @patch("app.services.execution_service.ExecutionLogService")
    @patch("app.services.execution_service.get_paths_for_trigger_detailed", return_value=[])
    @patch("shutil.which", return_value=None)
    def test_failed_exit_code_marks_failed(
        self,
        mock_which,
        mock_paths,
        mock_log_svc,
        mock_audit,
        mock_budget,
        mock_pm,
        mock_github,
        isolated_db,
    ):
        mock_log_svc.start_execution.return_value = "exec-fail"
        mock_budget.check_budget.return_value = {"allowed": True}
        mock_pm.is_cancelled.return_value = False

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.wait.return_value = 1
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = MagicMock(return_value="")
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.readline = MagicMock(return_value="")
        mock_proc.poll.return_value = 1

        with (
            patch("subprocess.Popen", return_value=mock_proc),
            patch("threading.Thread") as mock_thread_cls,
        ):
            mock_thread = MagicMock()
            mock_thread.is_alive.return_value = False
            mock_thread_cls.return_value = mock_thread

            trigger = _make_trigger()
            result = ExecutionService.run_trigger(trigger, "test")

        assert result == "exec-fail"
        finish_call = mock_log_svc.finish_execution.call_args
        assert finish_call[1]["status"] == ExecutionState.FAILED
        assert finish_call[1]["exit_code"] == 1


# ---------------------------------------------------------------------------
# save_trigger_event / save_threat_report
# ---------------------------------------------------------------------------


class TestSaveHelpers:
    def test_save_trigger_event(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.services.execution_service.TRIGGER_LOG_DIR", str(tmp_path))
        trigger = _make_trigger()
        event = {"action": "opened"}
        event_id = ExecutionService.save_trigger_event(trigger, event)
        assert event_id

        import glob

        files = glob.glob(str(tmp_path / "trigger_*.json"))
        assert len(files) == 1
        with open(files[0]) as f:
            data = json.load(f)
        assert data["trigger_id"] == "trg-test01"

    def test_save_threat_report(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.services.execution_service.SECURITY_AUDIT_REPORT_DIR", str(tmp_path)
        )
        path = ExecutionService.save_threat_report("trg-test01", "vulnerability details")
        assert "threat_report_" in path

        with open(path) as f:
            content = f.read()
        assert content == "vulnerability details"


# ---------------------------------------------------------------------------
# ExecutionState constants
# ---------------------------------------------------------------------------


class TestExecutionState:
    def test_all_states_are_strings(self):
        states = [
            ExecutionState.RUNNING,
            ExecutionState.SUCCESS,
            ExecutionState.FAILED,
            ExecutionState.TIMEOUT,
            ExecutionState.CANCELLED,
            ExecutionState.IDLE,
            ExecutionState.PAUSED,
            ExecutionState.PAUSE_TIMEOUT,
        ]
        for state in states:
            assert isinstance(state, str)

    def test_state_values(self):
        assert ExecutionState.RUNNING == "running"
        assert ExecutionState.SUCCESS == "success"
        assert ExecutionState.FAILED == "failed"
        assert ExecutionState.TIMEOUT == "timeout"
        assert ExecutionState.CANCELLED == "cancelled"
        assert ExecutionState.IDLE == "idle"


# ---------------------------------------------------------------------------
# _fetch_pr_diff
# ---------------------------------------------------------------------------


class TestFetchPrDiff:
    def test_returns_none_for_empty_pr_url(self):
        result = ExecutionService._fetch_pr_diff({})
        assert result is None

    def test_returns_none_for_missing_pr_url(self):
        result = ExecutionService._fetch_pr_diff({"pr_url": ""})
        assert result is None

    @patch("urllib.request.urlopen")
    def test_returns_diff_text(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b"diff --git a/file.py b/file.py\n"
        mock_urlopen.return_value = mock_response

        result = ExecutionService._fetch_pr_diff({"pr_url": "https://github.com/o/r/pull/1"})
        assert result == "diff --git a/file.py b/file.py\n"

    @patch("urllib.request.urlopen", side_effect=Exception("network error"))
    def test_returns_none_on_network_error(self, mock_urlopen):
        result = ExecutionService._fetch_pr_diff({"pr_url": "https://github.com/o/r/pull/1"})
        assert result is None
