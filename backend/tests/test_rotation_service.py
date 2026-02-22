"""Tests for RotationService: decision logic, weighted scoring, continuation prompt
builder, process termination, and full rotation flow."""

import subprocess
import threading
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_rotation_state():
    """Reset RotationService class-level state before each test."""
    from app.services.rotation_service import RotationService

    RotationService._rotation_state = {}
    RotationService._lock = threading.Lock()
    yield
    RotationService._rotation_state = {}


def _mock_monitoring_status(windows):
    """Build a MonitoringService.get_monitoring_status() return value.

    windows: list of dicts with keys:
        account_id, percentage, eta_status, minutes_remaining (optional)
    """
    result_windows = []
    for w in windows:
        eta = {"status": w.get("eta_status", "safe")}
        if w.get("minutes_remaining") is not None:
            eta["minutes_remaining"] = w["minutes_remaining"]
        result_windows.append(
            {
                "account_id": w["account_id"],
                "window_type": w.get("window_type", "five_hour"),
                "percentage": w.get("percentage", 0.0),
                "eta": eta,
            }
        )
    return {
        "enabled": True,
        "polling_minutes": 5,
        "windows": result_windows,
        "threshold_alerts": [],
    }


def _default_monitoring_config():
    """Default monitoring config for tests."""
    return {
        "enabled": True,
        "polling_minutes": 5,
        "safety_margin_minutes": 5,
        "resume_hysteresis_polls": 2,
    }


# ===========================================================================
# should_rotate() Decision Logic Tests
# ===========================================================================


class TestShouldRotate:
    """Tests for RotationService.should_rotate() decision logic."""

    def test_should_rotate_true_when_utilization_high_and_eta_low(self, isolated_db):
        """High utilization (85%) + ETA projected < safety margin (3min < 5min) -> True."""
        from app.services.rotation_service import RotationService

        mock_status = _mock_monitoring_status(
            [
                {
                    "account_id": 1,
                    "percentage": 85.0,
                    "eta_status": "projected",
                    "minutes_remaining": 3.0,
                }
            ]
        )

        with (
            patch(
                "app.services.monitoring_service.MonitoringService.get_monitoring_status",
                return_value=mock_status,
            ),
            patch(
                "app.database.get_monitoring_config",
                return_value=_default_monitoring_config(),
            ),
            patch(
                "app.db.rotations.get_rotation_events_by_execution",
                return_value=[],
            ),
        ):
            result = RotationService.should_rotate("exec-001", 1)

        assert result["should_rotate"] is True
        assert result["utilization_pct"] == 85.0
        assert "exceeds threshold" in result["reason"]

    def test_should_rotate_false_when_utilization_below_threshold(self, isolated_db):
        """Low utilization (50%) -> False regardless of ETA."""
        from app.services.rotation_service import RotationService

        mock_status = _mock_monitoring_status(
            [
                {
                    "account_id": 1,
                    "percentage": 50.0,
                    "eta_status": "projected",
                    "minutes_remaining": 3.0,
                }
            ]
        )

        with (
            patch(
                "app.services.monitoring_service.MonitoringService.get_monitoring_status",
                return_value=mock_status,
            ),
            patch(
                "app.database.get_monitoring_config",
                return_value=_default_monitoring_config(),
            ),
            patch(
                "app.db.rotations.get_rotation_events_by_execution",
                return_value=[],
            ),
        ):
            result = RotationService.should_rotate("exec-001", 1)

        assert result["should_rotate"] is False
        assert result["utilization_pct"] == 50.0

    def test_should_rotate_false_when_no_monitoring_data(self, isolated_db):
        """No monitoring windows -> False (fail-safe)."""
        from app.services.rotation_service import RotationService

        mock_status = {"enabled": True, "windows": [], "threshold_alerts": []}

        with (
            patch(
                "app.services.monitoring_service.MonitoringService.get_monitoring_status",
                return_value=mock_status,
            ),
            patch(
                "app.database.get_monitoring_config",
                return_value=_default_monitoring_config(),
            ),
            patch(
                "app.db.rotations.get_rotation_events_by_execution",
                return_value=[],
            ),
        ):
            result = RotationService.should_rotate("exec-001", 1)

        assert result["should_rotate"] is False
        assert result["reason"] == "no_monitoring_data"

    def test_should_rotate_false_when_max_rotations_reached(self, isolated_db):
        """3 existing rotation events -> False regardless of utilization."""
        from app.services.rotation_service import RotationService

        # 3 existing rotation events
        existing_events = [{"id": f"rot-{i}"} for i in range(3)]

        with patch(
            "app.db.rotations.get_rotation_events_by_execution",
            return_value=existing_events,
        ):
            result = RotationService.should_rotate("exec-001", 1)

        assert result["should_rotate"] is False
        assert result["reason"] == "max_rotations_reached"

    def test_should_rotate_false_when_eta_safe(self, isolated_db):
        """High utilization but ETA status is 'safe' (window resets) -> False."""
        from app.services.rotation_service import RotationService

        mock_status = _mock_monitoring_status(
            [
                {
                    "account_id": 1,
                    "percentage": 90.0,
                    "eta_status": "safe",
                    "minutes_remaining": None,
                }
            ]
        )

        with (
            patch(
                "app.services.monitoring_service.MonitoringService.get_monitoring_status",
                return_value=mock_status,
            ),
            patch(
                "app.database.get_monitoring_config",
                return_value=_default_monitoring_config(),
            ),
            patch(
                "app.db.rotations.get_rotation_events_by_execution",
                return_value=[],
            ),
        ):
            result = RotationService.should_rotate("exec-001", 1)

        assert result["should_rotate"] is False
        assert result["utilization_pct"] == 90.0

    def test_should_rotate_false_when_no_account_windows(self, isolated_db):
        """Monitoring has windows but none for the target account -> False."""
        from app.services.rotation_service import RotationService

        mock_status = _mock_monitoring_status(
            [
                {
                    "account_id": 999,  # Different account
                    "percentage": 95.0,
                    "eta_status": "projected",
                    "minutes_remaining": 1.0,
                }
            ]
        )

        with (
            patch(
                "app.services.monitoring_service.MonitoringService.get_monitoring_status",
                return_value=mock_status,
            ),
            patch(
                "app.database.get_monitoring_config",
                return_value=_default_monitoring_config(),
            ),
            patch(
                "app.db.rotations.get_rotation_events_by_execution",
                return_value=[],
            ),
        ):
            result = RotationService.should_rotate("exec-001", 1)

        assert result["should_rotate"] is False
        assert result["reason"] == "no_account_data"


# ===========================================================================
# score_accounts() Weighted Scoring Tests
# ===========================================================================


class TestScoreAccounts:
    """Tests for RotationService.score_accounts() weighted scoring."""

    def _mock_account(self, account_id, backend_type="claude"):
        """Build a minimal account dict."""
        return {
            "id": account_id,
            "account_name": f"account-{account_id}",
            "backend_type": backend_type,
            "config_path": None,
            "api_key_env": None,
        }

    def test_score_accounts_ranks_by_remaining_capacity(self, isolated_db):
        """Account with more remaining capacity ranks higher."""
        from app.services.rotation_service import RotationService

        acct1 = self._mock_account(2)  # High utilization
        acct2 = self._mock_account(3)  # Low utilization

        # Account 2: 80% utilized (20% remaining -> 0.2)
        # Account 3: 20% utilized (80% remaining -> 0.8)
        def mock_remaining(account_id, now):
            if account_id == 2:
                return 0.2
            return 0.8

        with (
            patch(
                "app.database.get_accounts_for_backend_type",
                return_value=[self._mock_account(1), acct1, acct2],
            ),
            patch(
                "app.services.rate_limit_service.RateLimitService.is_rate_limited",
                return_value=False,
            ),
            patch(
                "app.services.agent_scheduler_service.AgentSchedulerService.check_eligibility",
                return_value={"eligible": True},
            ),
            patch(
                "app.services.provider_usage_client.CredentialResolver.get_token_fingerprint",
                return_value=None,
            ),
            patch.object(
                RotationService,
                "_get_remaining_capacity_pct",
                side_effect=mock_remaining,
            ),
        ):
            result = RotationService.score_accounts("claude", 1)

        assert len(result) == 2
        # Account 3 (80% remaining) should rank higher than account 2 (20% remaining)
        assert result[0]["account"]["id"] == 3
        assert result[1]["account"]["id"] == 2
        assert result[0]["score"] > result[1]["score"]

    def test_score_accounts_excludes_rate_limited(self, isolated_db):
        """Rate-limited accounts are excluded from candidates."""
        from app.services.rotation_service import RotationService

        acct1 = self._mock_account(2)
        acct2 = self._mock_account(3)

        def mock_rate_limited(account_id):
            return account_id == 2

        with (
            patch(
                "app.database.get_accounts_for_backend_type",
                return_value=[self._mock_account(1), acct1, acct2],
            ),
            patch(
                "app.services.rate_limit_service.RateLimitService.is_rate_limited",
                side_effect=mock_rate_limited,
            ),
            patch(
                "app.services.agent_scheduler_service.AgentSchedulerService.check_eligibility",
                return_value={"eligible": True},
            ),
            patch(
                "app.services.provider_usage_client.CredentialResolver.get_token_fingerprint",
                return_value=None,
            ),
            patch.object(
                RotationService,
                "_get_remaining_capacity_pct",
                return_value=0.5,
            ),
        ):
            result = RotationService.score_accounts("claude", 1)

        assert len(result) == 1
        assert result[0]["account"]["id"] == 3

    def test_score_accounts_excludes_current_account(self, isolated_db):
        """The current account is never in the results."""
        from app.services.rotation_service import RotationService

        with (
            patch(
                "app.database.get_accounts_for_backend_type",
                return_value=[self._mock_account(1), self._mock_account(2)],
            ),
            patch(
                "app.services.rate_limit_service.RateLimitService.is_rate_limited",
                return_value=False,
            ),
            patch(
                "app.services.agent_scheduler_service.AgentSchedulerService.check_eligibility",
                return_value={"eligible": True},
            ),
            patch(
                "app.services.provider_usage_client.CredentialResolver.get_token_fingerprint",
                return_value=None,
            ),
            patch.object(
                RotationService,
                "_get_remaining_capacity_pct",
                return_value=0.5,
            ),
        ):
            result = RotationService.score_accounts("claude", 1)

        account_ids = [r["account"]["id"] for r in result]
        assert 1 not in account_ids
        assert 2 in account_ids

    def test_score_accounts_penalizes_shared_credentials(self, isolated_db):
        """Account sharing credentials with current gets a penalty."""
        from app.services.rotation_service import RotationService

        acct_current = self._mock_account(1)
        acct_shared = self._mock_account(2)  # Shares credentials
        acct_unique = self._mock_account(3)  # Unique credentials

        def mock_fingerprint(account, backend_type):
            if account["id"] in (1, 2):
                return "same_fingerprint"  # Shared
            return "unique_fingerprint"

        with (
            patch(
                "app.database.get_accounts_for_backend_type",
                return_value=[acct_current, acct_shared, acct_unique],
            ),
            patch(
                "app.services.rate_limit_service.RateLimitService.is_rate_limited",
                return_value=False,
            ),
            patch(
                "app.services.agent_scheduler_service.AgentSchedulerService.check_eligibility",
                return_value={"eligible": True},
            ),
            patch(
                "app.services.provider_usage_client.CredentialResolver.get_token_fingerprint",
                side_effect=mock_fingerprint,
            ),
            patch.object(
                RotationService,
                "_get_remaining_capacity_pct",
                return_value=0.5,
            ),
        ):
            result = RotationService.score_accounts("claude", 1)

        assert len(result) == 2
        # Account 3 (unique creds, no penalty) should score higher than account 2 (shared, penalty)
        assert result[0]["account"]["id"] == 3
        assert result[1]["account"]["id"] == 2
        # Verify penalty: score(unique) = 0.6*0.5 + 0.2*1.0 - 0.2*0.0 = 0.50
        # score(shared) = 0.6*0.5 + 0.2*1.0 - 0.2*1.0 = 0.30
        assert abs(result[0]["score"] - 0.50) < 0.01
        assert abs(result[1]["score"] - 0.30) < 0.01

    def test_score_accounts_returns_empty_when_no_candidates(self, isolated_db):
        """All accounts rate-limited or current -> empty list."""
        from app.services.rotation_service import RotationService

        with (
            patch(
                "app.database.get_accounts_for_backend_type",
                return_value=[self._mock_account(1)],
            ),
            patch(
                "app.services.rate_limit_service.RateLimitService.is_rate_limited",
                return_value=False,
            ),
            patch(
                "app.services.agent_scheduler_service.AgentSchedulerService.check_eligibility",
                return_value={"eligible": True},
            ),
            patch(
                "app.services.provider_usage_client.CredentialResolver.get_token_fingerprint",
                return_value=None,
            ),
            patch.object(
                RotationService,
                "_get_remaining_capacity_pct",
                return_value=0.5,
            ),
        ):
            result = RotationService.score_accounts("claude", 1)

        assert result == []


# ===========================================================================
# build_continuation_prompt() Tests
# ===========================================================================


class TestBuildContinuationPrompt:
    """Tests for RotationService.build_continuation_prompt()."""

    def test_continuation_prompt_includes_original_and_context(self, isolated_db):
        """Prompt includes CONTINUATION header, original prompt, and last N lines."""
        from app.services.rotation_service import RotationService

        # 300 lines of output
        stdout_log = "\n".join([f"line {i}: doing work" for i in range(300)])

        with patch(
            "app.services.execution_log_service.ExecutionLogService.get_stdout_log",
            return_value=stdout_log,
        ):
            result = RotationService.build_continuation_prompt("exec-001", "Run the security audit")

        assert "CONTINUATION:" in result
        assert "Run the security audit" in result
        assert "last 200 lines" in result
        # Should contain lines from end of output
        assert "line 299: doing work" in result
        # Should NOT contain early lines (only last 200 of 300)
        assert "line 50: doing work" not in result

    def test_continuation_prompt_handles_empty_log(self, isolated_db):
        """Empty stdout log -> still contains header and original prompt."""
        from app.services.rotation_service import RotationService

        with patch(
            "app.services.execution_log_service.ExecutionLogService.get_stdout_log",
            return_value="",
        ):
            result = RotationService.build_continuation_prompt("exec-001", "Run the security audit")

        assert "CONTINUATION:" in result
        assert "Run the security audit" in result
        assert "last 0 lines" in result  # Empty string -> empty list -> 0 lines

    def test_continuation_prompt_respects_context_lines_param(self, isolated_db):
        """Custom context_lines=50 -> only last 50 lines included."""
        from app.services.rotation_service import RotationService

        stdout_log = "\n".join([f"line {i}" for i in range(100)])

        with patch(
            "app.services.execution_log_service.ExecutionLogService.get_stdout_log",
            return_value=stdout_log,
        ):
            result = RotationService.build_continuation_prompt(
                "exec-001", "test prompt", context_lines=50
            )

        assert "last 50 lines" in result
        assert "line 99" in result  # Last line present
        assert "line 49" not in result  # Lines before last 50 not present
        assert "line 50" in result  # First of last 50


# ===========================================================================
# _terminate_process() Tests
# ===========================================================================


class TestTerminateProcess:
    """Tests for RotationService._terminate_process()."""

    def test_terminate_sends_sigterm_then_succeeds(self, isolated_db):
        """SIGTERM succeeds -> process exits -> returns True."""
        from app.services.process_manager import ProcessInfo, ProcessManager
        from app.services.rotation_service import RotationService

        mock_process = MagicMock()
        mock_process.wait.return_value = 0  # Exits after SIGTERM

        info = ProcessInfo(
            process=mock_process,
            pgid=12345,
            execution_id="exec-001",
            trigger_id="trigger-001",
        )

        with (
            patch.object(ProcessManager, "_processes", {"exec-001": info}),
            patch("os.killpg") as mock_killpg,
        ):
            result = RotationService._terminate_process("exec-001", timeout=5)

        assert result is True
        mock_killpg.assert_called_once_with(12345, 15)  # SIGTERM = 15
        mock_process.wait.assert_called_once_with(timeout=5)

    def test_terminate_falls_back_to_sigkill(self, isolated_db):
        """SIGTERM timeout -> SIGKILL sent."""
        from app.services.process_manager import ProcessInfo, ProcessManager
        from app.services.rotation_service import RotationService

        mock_process = MagicMock()
        # First wait (SIGTERM) times out, second wait (SIGKILL) succeeds
        mock_process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="test", timeout=5),
            0,
        ]

        info = ProcessInfo(
            process=mock_process,
            pgid=12345,
            execution_id="exec-001",
            trigger_id="trigger-001",
        )

        killpg_calls = []

        def mock_killpg(pgid, sig):
            killpg_calls.append((pgid, sig))

        with (
            patch.object(ProcessManager, "_processes", {"exec-001": info}),
            patch("os.killpg", side_effect=mock_killpg),
        ):
            result = RotationService._terminate_process("exec-001", timeout=5)

        assert result is True
        # SIGTERM first, then SIGKILL
        assert len(killpg_calls) == 2
        assert killpg_calls[0] == (12345, 15)  # SIGTERM
        assert killpg_calls[1] == (12345, 9)  # SIGKILL

    def test_terminate_handles_already_dead_process(self, isolated_db):
        """ProcessLookupError on killpg -> returns True (already dead = success)."""
        from app.services.process_manager import ProcessInfo, ProcessManager
        from app.services.rotation_service import RotationService

        mock_process = MagicMock()
        info = ProcessInfo(
            process=mock_process,
            pgid=12345,
            execution_id="exec-001",
            trigger_id="trigger-001",
        )

        with (
            patch.object(ProcessManager, "_processes", {"exec-001": info}),
            patch("os.killpg", side_effect=ProcessLookupError("No such process")),
        ):
            result = RotationService._terminate_process("exec-001")

        assert result is True

    def test_terminate_returns_false_when_no_process(self, isolated_db):
        """No process in ProcessManager -> returns False."""
        from app.services.process_manager import ProcessManager
        from app.services.rotation_service import RotationService

        with patch.object(ProcessManager, "_processes", {}):
            result = RotationService._terminate_process("exec-nonexistent")

        assert result is False


# ===========================================================================
# execute_rotation() Integration Tests
# ===========================================================================


class TestExecuteRotation:
    """Tests for RotationService.execute_rotation() full flow."""

    def _mock_trigger(self):
        """Build a minimal trigger dict."""
        return {
            "id": "trigger-001",
            "name": "Test Trigger",
            "backend_type": "claude",
            "prompt_template": "Run tests on {paths}",
        }

    def test_execute_rotation_full_flow(self, isolated_db):
        """Full rotation: evaluate -> score -> terminate -> restart -> complete."""
        from app.services.rotation_service import RotationService

        mock_execution = {
            "execution_id": "exec-001",
            "account_id": 1,
            "backend_type": "claude",
            "prompt": "Run the tests",
        }

        mock_target_account = {
            "id": 2,
            "account_name": "account-2",
            "backend_type": "claude",
            "config_path": None,
            "api_key_env": None,
        }

        with (
            patch(
                "app.services.execution_log_service.ExecutionLogService.get_execution",
                return_value=mock_execution,
            ),
            patch.object(
                RotationService,
                "should_rotate",
                return_value={
                    "should_rotate": True,
                    "reason": "utilization high",
                    "utilization_pct": 85.0,
                },
            ),
            patch.object(
                RotationService,
                "score_accounts",
                return_value=[{"account": mock_target_account, "score": 0.8}],
            ),
            patch.object(
                RotationService,
                "build_continuation_prompt",
                return_value="CONTINUATION: ...",
            ),
            patch.object(
                RotationService,
                "_terminate_process",
                return_value=True,
            ),
            patch(
                "app.services.process_manager.ProcessManager.cleanup",
            ),
            patch(
                "app.services.execution_log_service.ExecutionLogService.finish_execution",
            ),
            patch(
                "app.services.orchestration_service.OrchestrationService._build_account_env",
                return_value={"ANTHROPIC_API_KEY": "test-key"},
            ),
            patch(
                "app.services.execution_service.ExecutionService.run_trigger",
                return_value="exec-002",
            ),
            patch(
                "app.db.rotations.add_rotation_event",
                return_value="rot-test01",
            ) as mock_add_event,
            patch(
                "app.db.rotations.update_rotation_event",
                return_value=True,
            ) as mock_update_event,
        ):
            result = RotationService.execute_rotation(
                "exec-001",
                self._mock_trigger(),
                "test message",
            )

        assert result == "exec-002"
        # Verify rotation event was created
        mock_add_event.assert_called_once()
        call_kwargs = mock_add_event.call_args
        assert call_kwargs[1]["execution_id"] == "exec-001"
        assert call_kwargs[1]["from_account_id"] == 1
        assert call_kwargs[1]["to_account_id"] == 2

        # Verify rotation event was updated to completed
        update_calls = mock_update_event.call_args_list
        assert any(call[1].get("rotation_status") == "completed" for call in update_calls)

    def test_execute_rotation_skipped_when_no_candidates(self, isolated_db):
        """No available candidates -> skipped, no termination."""
        from app.services.rotation_service import RotationService

        mock_execution = {
            "execution_id": "exec-001",
            "account_id": 1,
            "backend_type": "claude",
            "prompt": "Run the tests",
        }

        with (
            patch(
                "app.services.execution_log_service.ExecutionLogService.get_execution",
                return_value=mock_execution,
            ),
            patch.object(
                RotationService,
                "should_rotate",
                return_value={
                    "should_rotate": True,
                    "reason": "utilization high",
                    "utilization_pct": 90.0,
                },
            ),
            patch.object(
                RotationService,
                "score_accounts",
                return_value=[],  # No candidates
            ),
            patch(
                "app.db.rotations.add_rotation_event",
                return_value="rot-test02",
            ),
            patch(
                "app.db.rotations.update_rotation_event",
                return_value=True,
            ) as mock_update_event,
            patch.object(
                RotationService,
                "_terminate_process",
            ) as mock_terminate,
        ):
            result = RotationService.execute_rotation(
                "exec-001",
                self._mock_trigger(),
                "test message",
            )

        assert result is None
        # Should NOT terminate the process
        mock_terminate.assert_not_called()
        # Should record as skipped
        mock_update_event.assert_called_once()
        assert mock_update_event.call_args[1]["rotation_status"] == "skipped"

    def test_execute_rotation_records_failure_on_exception(self, isolated_db):
        """Exception during rotation -> event status updated to 'failed'."""
        from app.services.rotation_service import RotationService

        mock_execution = {
            "execution_id": "exec-001",
            "account_id": 1,
            "backend_type": "claude",
            "prompt": "Run the tests",
        }

        mock_target_account = {
            "id": 2,
            "account_name": "account-2",
            "backend_type": "claude",
            "config_path": None,
            "api_key_env": None,
        }

        with (
            patch(
                "app.services.execution_log_service.ExecutionLogService.get_execution",
                return_value=mock_execution,
            ),
            patch.object(
                RotationService,
                "should_rotate",
                return_value={
                    "should_rotate": True,
                    "reason": "utilization high",
                    "utilization_pct": 85.0,
                },
            ),
            patch.object(
                RotationService,
                "score_accounts",
                return_value=[{"account": mock_target_account, "score": 0.8}],
            ),
            patch.object(
                RotationService,
                "build_continuation_prompt",
                return_value="CONTINUATION: ...",
            ),
            patch(
                "app.db.rotations.add_rotation_event",
                return_value="rot-test03",
            ),
            patch.object(
                RotationService,
                "_terminate_process",
                side_effect=RuntimeError("Termination failed!"),
            ),
            patch(
                "app.db.rotations.update_rotation_event",
                return_value=True,
            ) as mock_update_event,
        ):
            result = RotationService.execute_rotation(
                "exec-001",
                self._mock_trigger(),
                "test message",
            )

        assert result is None
        # Should update rotation event to failed
        mock_update_event.assert_called_once()
        assert mock_update_event.call_args[1]["rotation_status"] == "failed"


# ===========================================================================
# get_rotation_history() Tests
# ===========================================================================


class TestGetRotationHistory:
    """Tests for RotationService.get_rotation_history()."""

    def test_get_history_by_execution(self, isolated_db):
        """With execution_id -> delegates to get_rotation_events_by_execution."""
        from app.services.rotation_service import RotationService

        mock_events = [{"id": "rot-001", "execution_id": "exec-001"}]

        with patch(
            "app.db.rotations.get_rotation_events_by_execution",
            return_value=mock_events,
        ) as mock_fn:
            result = RotationService.get_rotation_history(execution_id="exec-001")

        assert result == mock_events
        mock_fn.assert_called_once_with("exec-001")

    def test_get_history_all(self, isolated_db):
        """Without execution_id -> delegates to get_all_rotation_events."""
        from app.services.rotation_service import RotationService

        mock_events = [{"id": "rot-001"}, {"id": "rot-002"}]

        with patch(
            "app.db.rotations.get_all_rotation_events",
            return_value=mock_events,
        ) as mock_fn:
            result = RotationService.get_rotation_history(limit=25)

        assert result == mock_events
        mock_fn.assert_called_once_with(25)


# ===========================================================================
# reset_rotation_state() Tests
# ===========================================================================


class TestResetRotationState:
    """Tests for RotationService.reset_rotation_state()."""

    def test_reset_removes_execution_state(self, isolated_db):
        """Removes execution from _rotation_state dict."""
        from app.services.rotation_service import RotationService

        RotationService._rotation_state["exec-001"] = {"consecutive_polls": 3}
        assert "exec-001" in RotationService._rotation_state

        RotationService.reset_rotation_state("exec-001")

        assert "exec-001" not in RotationService._rotation_state

    def test_reset_noop_for_missing_execution(self, isolated_db):
        """No error when resetting non-existent execution."""
        from app.services.rotation_service import RotationService

        RotationService.reset_rotation_state("exec-nonexistent")
        # Should not raise
