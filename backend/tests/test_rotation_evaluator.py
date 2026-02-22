"""Tests for RotationEvaluator: hysteresis logic, evaluation filtering, APScheduler job
registration, error handling, and status endpoint."""

import threading
from unittest.mock import MagicMock, patch

import pytest

from app.services.rotation_evaluator import RotationEvaluator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_evaluator_state():
    """Reset RotationEvaluator class-level state before each test."""
    RotationEvaluator._evaluation_state = {}
    RotationEvaluator._lock = threading.Lock()
    yield
    RotationEvaluator._evaluation_state = {}


def _mock_execution(
    execution_id="exec-1",
    account_id=1,
    trigger_id="trig-1",
    trigger_type="webhook",
    prompt="Run the task",
):
    """Create a mock execution record."""
    return {
        "id": execution_id,
        "account_id": account_id,
        "trigger_id": trigger_id,
        "trigger_type": trigger_type,
        "prompt": prompt,
        "backend_type": "claude",
    }


# ---------------------------------------------------------------------------
# 1. Hysteresis counter logic (5 tests)
# ---------------------------------------------------------------------------


class TestHysteresisCounterLogic:
    """Tests for hysteresis-damped rotation decisions."""

    @patch(
        "app.services.rotation_evaluator.RotationEvaluator._get_hysteresis_threshold",
        return_value=2,
    )
    @patch("app.database.get_trigger", return_value={"id": "trig-1", "name": "Test"})
    @patch(
        "app.services.rotation_service.RotationService.should_rotate",
        return_value={"should_rotate": True, "reason": "approaching", "utilization_pct": 85.0},
    )
    @patch("app.services.execution_log_service.ExecutionLogService.get_execution")
    @patch(
        "app.services.process_manager.ProcessManager.get_active_executions", return_value=["exec-1"]
    )
    @patch("app.services.rotation_service.RotationService.execute_rotation")
    def test_hysteresis_does_not_rotate_on_first_poll(
        self, mock_execute, mock_active, mock_get_exec, mock_should, mock_trigger, mock_threshold
    ):
        """First poll with should_rotate=True: counter=1, no rotation yet (threshold=2)."""
        mock_get_exec.return_value = _mock_execution()

        RotationEvaluator._evaluate_running_sessions()

        mock_execute.assert_not_called()
        assert RotationEvaluator._evaluation_state["exec-1"]["consecutive_rotate_polls"] == 1

    @patch(
        "app.services.rotation_evaluator.RotationEvaluator._get_hysteresis_threshold",
        return_value=2,
    )
    @patch("app.database.get_trigger", return_value={"id": "trig-1", "name": "Test"})
    @patch(
        "app.services.rotation_service.RotationService.should_rotate",
        return_value={"should_rotate": True, "reason": "approaching", "utilization_pct": 85.0},
    )
    @patch("app.services.execution_log_service.ExecutionLogService.get_execution")
    @patch(
        "app.services.process_manager.ProcessManager.get_active_executions", return_value=["exec-1"]
    )
    @patch("app.services.rotation_evaluator.threading.Thread")
    def test_hysteresis_triggers_on_threshold(
        self, mock_thread_cls, mock_active, mock_get_exec, mock_should, mock_trigger, mock_threshold
    ):
        """Two consecutive polls with should_rotate=True: rotation triggered on second."""
        mock_get_exec.return_value = _mock_execution()
        mock_thread_instance = MagicMock()
        mock_thread_cls.return_value = mock_thread_instance

        # First evaluation: counter goes to 1
        RotationEvaluator._evaluate_running_sessions()
        mock_thread_cls.assert_not_called()

        # Second evaluation: counter hits 2, rotation triggered
        RotationEvaluator._evaluate_running_sessions()
        mock_thread_cls.assert_called_once()
        mock_thread_instance.start.assert_called_once()

        # Counter reset to 0 after rotation dispatch
        assert RotationEvaluator._evaluation_state["exec-1"]["consecutive_rotate_polls"] == 0

    @patch(
        "app.services.rotation_evaluator.RotationEvaluator._get_hysteresis_threshold",
        return_value=2,
    )
    @patch("app.database.get_trigger", return_value={"id": "trig-1", "name": "Test"})
    @patch("app.services.rotation_service.RotationService.should_rotate")
    @patch("app.services.execution_log_service.ExecutionLogService.get_execution")
    @patch(
        "app.services.process_manager.ProcessManager.get_active_executions", return_value=["exec-1"]
    )
    @patch("app.services.rotation_service.RotationService.execute_rotation")
    def test_hysteresis_resets_on_safe_poll(
        self, mock_execute, mock_active, mock_get_exec, mock_should, mock_trigger, mock_threshold
    ):
        """True -> False -> True: counter resets on False poll, never reaches threshold."""
        mock_get_exec.return_value = _mock_execution()

        # Poll 1: True -> counter=1
        mock_should.return_value = {
            "should_rotate": True,
            "reason": "approaching",
            "utilization_pct": 85.0,
        }
        RotationEvaluator._evaluate_running_sessions()
        assert RotationEvaluator._evaluation_state["exec-1"]["consecutive_rotate_polls"] == 1

        # Poll 2: False -> counter resets to 0
        mock_should.return_value = {
            "should_rotate": False,
            "reason": "safe",
            "utilization_pct": 50.0,
        }
        RotationEvaluator._evaluate_running_sessions()
        assert RotationEvaluator._evaluation_state["exec-1"]["consecutive_rotate_polls"] == 0

        # Poll 3: True -> counter=1 (not 2, because it was reset)
        mock_should.return_value = {
            "should_rotate": True,
            "reason": "approaching",
            "utilization_pct": 85.0,
        }
        RotationEvaluator._evaluate_running_sessions()
        assert RotationEvaluator._evaluation_state["exec-1"]["consecutive_rotate_polls"] == 1

        # execute_rotation never called (threshold never reached)
        mock_execute.assert_not_called()

    @patch("app.database.get_trigger", return_value={"id": "trig-1", "name": "Test"})
    @patch(
        "app.services.rotation_service.RotationService.should_rotate",
        return_value={"should_rotate": True, "reason": "approaching", "utilization_pct": 90.0},
    )
    @patch("app.services.execution_log_service.ExecutionLogService.get_execution")
    @patch(
        "app.services.process_manager.ProcessManager.get_active_executions", return_value=["exec-1"]
    )
    @patch("app.services.rotation_evaluator.threading.Thread")
    @patch(
        "app.services.rotation_evaluator.RotationEvaluator._get_hysteresis_threshold",
        return_value=3,
    )
    def test_hysteresis_custom_threshold(
        self, mock_threshold, mock_thread_cls, mock_active, mock_get_exec, mock_should, mock_trigger
    ):
        """Custom threshold=3 requires 3 consecutive True polls before rotation."""
        mock_get_exec.return_value = _mock_execution()
        mock_thread_instance = MagicMock()
        mock_thread_cls.return_value = mock_thread_instance

        # Polls 1 and 2: no rotation
        RotationEvaluator._evaluate_running_sessions()
        RotationEvaluator._evaluate_running_sessions()
        mock_thread_cls.assert_not_called()
        assert RotationEvaluator._evaluation_state["exec-1"]["consecutive_rotate_polls"] == 2

        # Poll 3: threshold reached, rotation triggered
        RotationEvaluator._evaluate_running_sessions()
        mock_thread_cls.assert_called_once()

    @patch(
        "app.services.rotation_evaluator.RotationEvaluator._get_hysteresis_threshold",
        return_value=2,
    )
    @patch("app.database.get_trigger", return_value={"id": "trig-1", "name": "Test"})
    @patch("app.services.rotation_service.RotationService.should_rotate")
    @patch("app.services.execution_log_service.ExecutionLogService.get_execution")
    @patch(
        "app.services.process_manager.ProcessManager.get_active_executions",
        return_value=["exec-1", "exec-2"],
    )
    @patch("app.services.rotation_evaluator.threading.Thread")
    def test_hysteresis_counter_per_execution(
        self, mock_thread_cls, mock_active, mock_get_exec, mock_should, mock_trigger, mock_threshold
    ):
        """Two active executions: one hits threshold, other doesn't."""
        exec1 = _mock_execution("exec-1", account_id=1)
        exec2 = _mock_execution("exec-2", account_id=2)
        mock_get_exec.side_effect = lambda eid: exec1 if eid == "exec-1" else exec2
        mock_thread_instance = MagicMock()
        mock_thread_cls.return_value = mock_thread_instance

        # exec-1: should rotate=True, exec-2: should rotate=False
        def should_rotate_side_effect(eid, aid):
            if eid == "exec-1":
                return {"should_rotate": True, "reason": "approaching", "utilization_pct": 85.0}
            return {"should_rotate": False, "reason": "safe", "utilization_pct": 30.0}

        mock_should.side_effect = should_rotate_side_effect

        # Poll 1: exec-1 counter=1, exec-2 counter=0
        RotationEvaluator._evaluate_running_sessions()
        assert RotationEvaluator._evaluation_state["exec-1"]["consecutive_rotate_polls"] == 1
        assert RotationEvaluator._evaluation_state["exec-2"]["consecutive_rotate_polls"] == 0
        mock_thread_cls.assert_not_called()

        # Poll 2: exec-1 hits threshold, exec-2 still safe
        RotationEvaluator._evaluate_running_sessions()
        mock_thread_cls.assert_called_once()
        # Verify the thread was started for exec-1 (check args)
        call_args = mock_thread_cls.call_args
        assert call_args[1]["args"][0] == "exec-1"


# ---------------------------------------------------------------------------
# 2. Evaluation filtering (3 tests)
# ---------------------------------------------------------------------------


class TestEvaluationFiltering:
    """Tests for evaluation filtering logic."""

    @patch("app.services.process_manager.ProcessManager.get_active_executions", return_value=[])
    @patch("app.services.rotation_service.RotationService.should_rotate")
    def test_evaluator_skips_when_no_active_executions(self, mock_should, mock_active):
        """No active executions: should_rotate never called."""
        RotationEvaluator._evaluate_running_sessions()
        mock_should.assert_not_called()

    @patch(
        "app.services.rotation_evaluator.RotationEvaluator._get_hysteresis_threshold",
        return_value=2,
    )
    @patch("app.services.rotation_service.RotationService.should_rotate")
    @patch("app.services.execution_log_service.ExecutionLogService.get_execution")
    @patch(
        "app.services.process_manager.ProcessManager.get_active_executions", return_value=["exec-1"]
    )
    def test_evaluator_skips_executions_without_account(
        self, mock_active, mock_get_exec, mock_should, mock_threshold
    ):
        """Execution with account_id=None: should_rotate not called."""
        mock_get_exec.return_value = {
            "id": "exec-1",
            "account_id": None,
            "trigger_id": "trig-1",
            "trigger_type": "webhook",
            "prompt": "task",
        }

        RotationEvaluator._evaluate_running_sessions()
        mock_should.assert_not_called()

    @patch("app.services.process_manager.ProcessManager.get_active_executions", return_value=[])
    def test_evaluator_cleans_up_stale_state(self, mock_active):
        """Stale state entries removed when execution no longer active."""
        # Pre-populate state for an execution that is no longer active
        RotationEvaluator._evaluation_state = {
            "exec-old": {"consecutive_rotate_polls": 3, "last_evaluated": "2026-01-01T00:00:00Z"},
            "exec-old-2": {"consecutive_rotate_polls": 1, "last_evaluated": "2026-01-01T00:00:00Z"},
        }

        RotationEvaluator._evaluate_running_sessions()

        assert "exec-old" not in RotationEvaluator._evaluation_state
        assert "exec-old-2" not in RotationEvaluator._evaluation_state
        assert len(RotationEvaluator._evaluation_state) == 0


# ---------------------------------------------------------------------------
# 3. APScheduler job registration (2 tests)
# ---------------------------------------------------------------------------


class TestJobRegistration:
    """Tests for APScheduler job registration."""

    def test_register_job_adds_to_scheduler(self):
        """init() registers job with correct parameters."""
        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = None

        with patch("app.services.scheduler_service.SchedulerService._scheduler", mock_scheduler):
            RotationEvaluator.init()

        mock_scheduler.add_job.assert_called_once()
        call_kwargs = mock_scheduler.add_job.call_args[1]
        assert call_kwargs["trigger"] == "interval"
        assert call_kwargs["seconds"] == 15
        assert call_kwargs["id"] == "rotation_evaluator"
        assert call_kwargs["replace_existing"] is True
        assert call_kwargs["coalesce"] is True
        assert call_kwargs["max_instances"] == 1

    def test_register_job_warns_when_no_scheduler(self):
        """No scheduler available: warning logged, no crash."""
        with patch("app.services.scheduler_service.SchedulerService._scheduler", None):
            with patch("app.services.rotation_evaluator.logger") as mock_logger:
                RotationEvaluator._register_job()
                mock_logger.warning.assert_called_once_with(
                    "Scheduler not available for rotation evaluator"
                )

    def test_register_job_removes_existing_before_adding(self):
        """If job already exists, remove it before adding new one."""
        mock_scheduler = MagicMock()
        mock_existing = MagicMock()
        mock_scheduler.get_job.return_value = mock_existing

        with patch("app.services.scheduler_service.SchedulerService._scheduler", mock_scheduler):
            RotationEvaluator._register_job()

        mock_scheduler.remove_job.assert_called_once_with("rotation_evaluator")
        mock_scheduler.add_job.assert_called_once()


# ---------------------------------------------------------------------------
# 4. Error handling (2 tests)
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error resilience."""

    @patch(
        "app.services.process_manager.ProcessManager.get_active_executions",
        side_effect=RuntimeError("DB connection failed"),
    )
    def test_evaluate_catches_exceptions(self, mock_active):
        """Unhandled exception in evaluation loop: caught, no propagation."""
        # Should NOT raise -- the try/except catches it
        RotationEvaluator._evaluate_running_sessions()

    def test_dispatch_rotation_catches_exceptions(self):
        """execute_rotation raises exception: caught, warning logged."""
        with patch(
            "app.services.rotation_service.RotationService.execute_rotation",
            side_effect=RuntimeError("Rotation failed"),
        ):
            with patch("app.services.rotation_evaluator.logger") as mock_logger:
                # Should NOT raise
                RotationEvaluator._dispatch_rotation(
                    "exec-1",
                    {"id": "trig-1"},
                    "task prompt",
                    {"trigger_type": "webhook"},
                    "webhook",
                )
                mock_logger.warning.assert_called_once()
                assert "rotation dispatch failed" in mock_logger.warning.call_args[0][0]

    @patch(
        "app.services.rotation_evaluator.RotationEvaluator._get_hysteresis_threshold",
        return_value=2,
    )
    @patch(
        "app.services.rotation_service.RotationService.should_rotate",
        side_effect=RuntimeError("Service error"),
    )
    @patch("app.services.execution_log_service.ExecutionLogService.get_execution")
    @patch(
        "app.services.process_manager.ProcessManager.get_active_executions", return_value=["exec-1"]
    )
    def test_single_execution_error_does_not_stop_others(
        self, mock_active, mock_get_exec, mock_should, mock_threshold
    ):
        """Error evaluating one execution does not prevent evaluating others."""
        mock_get_exec.return_value = _mock_execution()

        # Should NOT raise
        RotationEvaluator._evaluate_running_sessions()


# ---------------------------------------------------------------------------
# 5. Status endpoint (1 test)
# ---------------------------------------------------------------------------


class TestStatusEndpoint:
    """Tests for get_evaluator_status()."""

    @patch(
        "app.services.rotation_evaluator.RotationEvaluator._get_hysteresis_threshold",
        return_value=3,
    )
    def test_get_evaluator_status_returns_state(self, mock_threshold):
        """Status returns all expected fields."""
        RotationEvaluator._evaluation_state = {
            "exec-1": {"consecutive_rotate_polls": 1, "last_evaluated": "2026-01-01T00:00:00Z"},
            "exec-2": {"consecutive_rotate_polls": 0, "last_evaluated": "2026-01-01T00:01:00Z"},
        }

        status = RotationEvaluator.get_evaluator_status()

        assert status["job_id"] == "rotation_evaluator"
        assert status["evaluation_interval_seconds"] == 15
        assert status["hysteresis_threshold"] == 3
        assert status["active_evaluations"] == 2
        assert "exec-1" in status["evaluation_states"]
        assert "exec-2" in status["evaluation_states"]
        assert status["evaluation_states"]["exec-1"]["consecutive_rotate_polls"] == 1


# ---------------------------------------------------------------------------
# 6. Cleanup stale state (1 test)
# ---------------------------------------------------------------------------


class TestCleanupStaleState:
    """Tests for stale state cleanup."""

    def test_cleanup_preserves_active_state(self):
        """Active executions are preserved, stale ones are removed."""
        RotationEvaluator._evaluation_state = {
            "exec-active": {"consecutive_rotate_polls": 2, "last_evaluated": "2026-01-01"},
            "exec-stale": {"consecutive_rotate_polls": 5, "last_evaluated": "2026-01-01"},
        }

        RotationEvaluator._cleanup_stale_state(["exec-active"])

        assert "exec-active" in RotationEvaluator._evaluation_state
        assert "exec-stale" not in RotationEvaluator._evaluation_state
