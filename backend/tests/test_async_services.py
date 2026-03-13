"""Tests for background/async services: SchedulerService, RotationService helpers,
and RotationEvaluator hysteresis logic.

Focuses on business logic with mocked DB calls, scheduler internals, and thread ops.
"""

import json
import threading
from unittest.mock import MagicMock, patch

import pytest

# ===========================================================================
# SchedulerService — _build_cron_trigger tests
# ===========================================================================


class TestBuildCronTriggerLegacy:
    """Tests for SchedulerService._build_cron_trigger() with legacy schedule fields."""

    def test_daily_trigger(self):
        from app.services.scheduler_service import SchedulerService

        result = SchedulerService._build_cron_trigger(
            {"schedule_type": "daily", "schedule_time": "14:30", "schedule_timezone": "UTC"}
        )
        assert result is not None

    def test_weekly_trigger(self):
        from app.services.scheduler_service import SchedulerService

        result = SchedulerService._build_cron_trigger(
            {
                "schedule_type": "weekly",
                "schedule_time": "09:00",
                "schedule_day": 2,
                "schedule_timezone": "UTC",
            }
        )
        assert result is not None

    def test_monthly_trigger(self):
        from app.services.scheduler_service import SchedulerService

        result = SchedulerService._build_cron_trigger(
            {
                "schedule_type": "monthly",
                "schedule_time": "00:00",
                "schedule_day": 15,
                "schedule_timezone": "UTC",
            }
        )
        assert result is not None

    def test_monthly_defaults_day_to_1_when_zero(self):
        from app.services.scheduler_service import SchedulerService

        result = SchedulerService._build_cron_trigger(
            {
                "schedule_type": "monthly",
                "schedule_time": "12:00",
                "schedule_day": 0,
                "schedule_timezone": "UTC",
            }
        )
        assert result is not None

    def test_unknown_schedule_type_returns_none(self):
        from app.services.scheduler_service import SchedulerService

        result = SchedulerService._build_cron_trigger(
            {"schedule_type": "biweekly", "schedule_time": "09:00", "schedule_timezone": "UTC"}
        )
        assert result is None

    def test_missing_schedule_type_returns_none(self):
        from app.services.scheduler_service import SchedulerService

        result = SchedulerService._build_cron_trigger(
            {"schedule_time": "09:00", "schedule_timezone": "UTC"}
        )
        assert result is None

    def test_invalid_timezone_falls_back_to_utc(self):
        from app.services.scheduler_service import SchedulerService

        result = SchedulerService._build_cron_trigger(
            {"schedule_type": "daily", "schedule_time": "09:00", "schedule_timezone": "Invalid/TZ"}
        )
        assert result is not None

    def test_bad_time_format_defaults_to_midnight(self):
        from app.services.scheduler_service import SchedulerService

        result = SchedulerService._build_cron_trigger(
            {"schedule_type": "daily", "schedule_time": "bad", "schedule_timezone": "UTC"}
        )
        # Should still build a trigger using (0, 0)
        assert result is not None

    def test_cron_expression_takes_precedence(self):
        from app.services.scheduler_service import SchedulerService

        result = SchedulerService._build_cron_trigger(
            {
                "schedule_type": "daily",
                "schedule_time": "09:00",
                "schedule_timezone": "UTC",
                "cron_expression": "*/5 * * * *",
            }
        )
        assert result is not None

    def test_invalid_cron_expression_returns_none(self):
        from app.services.scheduler_service import SchedulerService

        result = SchedulerService._build_cron_trigger(
            {
                "schedule_type": "daily",
                "schedule_time": "09:00",
                "schedule_timezone": "UTC",
                "cron_expression": "bad expression",
            }
        )
        assert result is None


# ===========================================================================
# SchedulerService — Scheduler-dependent tests (mock APScheduler)
# ===========================================================================


class TestScheduleTrigger:
    """Tests for SchedulerService.schedule_trigger() and unschedule_trigger()."""

    def _make_trigger_data(self, trigger_id="trig-001", **overrides):
        data = {
            "id": trigger_id,
            "name": "Test Trigger",
            "enabled": True,
            "schedule_type": "daily",
            "schedule_time": "09:00",
            "schedule_timezone": "UTC",
        }
        data.update(overrides)
        return data

    def test_schedule_trigger_adds_job(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = None

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            SchedulerService.schedule_trigger(self._make_trigger_data())
            mock_scheduler.add_job.assert_called_once()
            call_kwargs = mock_scheduler.add_job.call_args
            assert call_kwargs[1]["id"] == "trigger-trig-001"
        finally:
            SchedulerService._scheduler = original

    def test_schedule_trigger_noop_without_scheduler(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        original = SchedulerService._scheduler
        SchedulerService._scheduler = None
        try:
            SchedulerService.schedule_trigger(self._make_trigger_data())
        finally:
            SchedulerService._scheduler = original

    def test_schedule_trigger_skips_without_schedule_type(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = None

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            SchedulerService.schedule_trigger(self._make_trigger_data(schedule_type=None))
            mock_scheduler.add_job.assert_not_called()
        finally:
            SchedulerService._scheduler = original

    def test_schedule_trigger_removes_existing_job_first(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_existing = MagicMock()
        # First get_job call returns existing, second (after add_job) returns new job
        mock_scheduler.get_job.side_effect = [mock_existing, MagicMock(next_run_time=None)]

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            SchedulerService.schedule_trigger(self._make_trigger_data())
            mock_scheduler.remove_job.assert_called_once_with("trigger-trig-001")
            mock_scheduler.add_job.assert_called_once()
        finally:
            SchedulerService._scheduler = original

    def test_unschedule_trigger_removes_job(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = MagicMock()

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            with patch("app.services.scheduler_service.update_trigger_next_run") as mock_update:
                SchedulerService.unschedule_trigger("trig-001")
                mock_scheduler.remove_job.assert_called_once_with("trigger-trig-001")
                mock_update.assert_called_once_with("trig-001", None)
        finally:
            SchedulerService._scheduler = original

    def test_unschedule_trigger_noop_when_no_job(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = None

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            with patch("app.services.scheduler_service.update_trigger_next_run") as mock_update:
                SchedulerService.unschedule_trigger("trig-001")
                mock_scheduler.remove_job.assert_not_called()
                mock_update.assert_not_called()
        finally:
            SchedulerService._scheduler = original

    def test_unschedule_trigger_noop_without_scheduler(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        original = SchedulerService._scheduler
        SchedulerService._scheduler = None
        try:
            SchedulerService.unschedule_trigger("trig-001")
        finally:
            SchedulerService._scheduler = original


class TestRescheduleTrigger:
    """Tests for SchedulerService.reschedule_trigger()."""

    def test_reschedule_active_trigger(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        trigger_data = {
            "id": "trig-001",
            "trigger_source": "scheduled",
            "enabled": True,
            "schedule_type": "daily",
            "schedule_time": "10:00",
            "schedule_timezone": "UTC",
        }

        with (
            patch(
                "app.services.scheduler_service.get_trigger",
                return_value=trigger_data,
            ),
            patch.object(SchedulerService, "schedule_trigger") as mock_schedule,
        ):
            SchedulerService.reschedule_trigger("trig-001")
            mock_schedule.assert_called_once_with(trigger_data)

    def test_reschedule_disabled_trigger_unschedules(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        trigger_data = {
            "id": "trig-001",
            "trigger_source": "scheduled",
            "enabled": False,
        }

        with (
            patch(
                "app.services.scheduler_service.get_trigger",
                return_value=trigger_data,
            ),
            patch.object(SchedulerService, "unschedule_trigger") as mock_unsched,
        ):
            SchedulerService.reschedule_trigger("trig-001")
            mock_unsched.assert_called_once_with("trig-001")

    def test_reschedule_nonexistent_trigger(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        with patch(
            "app.services.scheduler_service.get_trigger",
            return_value=None,
        ):
            SchedulerService.reschedule_trigger("trig-nonexistent")

    def test_reschedule_non_scheduled_trigger_unschedules(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        trigger_data = {
            "id": "trig-001",
            "trigger_source": "webhook",
            "enabled": True,
        }

        with (
            patch(
                "app.services.scheduler_service.get_trigger",
                return_value=trigger_data,
            ),
            patch.object(SchedulerService, "unschedule_trigger") as mock_unsched,
        ):
            SchedulerService.reschedule_trigger("trig-001")
            mock_unsched.assert_called_once_with("trig-001")


class TestExecuteTrigger:
    """Tests for SchedulerService._execute_trigger()."""

    def test_execute_trigger_runs_execution_service(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        trigger_data = {
            "id": "trig-001",
            "name": "Test Trigger",
            "enabled": True,
        }

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = MagicMock(next_run_time=None)

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            with (
                patch("app.services.scheduler_service.update_trigger_last_run") as mock_last_run,
                patch(
                    "app.services.scheduler_service.get_trigger",
                    return_value=trigger_data,
                ),
                patch(
                    "app.services.execution_service.ExecutionService.run_trigger",
                ) as mock_run,
                patch("app.services.scheduler_service.update_trigger_next_run"),
            ):
                SchedulerService._execute_trigger("trig-001")
                mock_last_run.assert_called_once()
                mock_run.assert_called_once()
                call_kwargs = mock_run.call_args[1]
                assert call_kwargs["trigger_type"] == "scheduled"
        finally:
            SchedulerService._scheduler = original

    def test_execute_trigger_skips_disabled(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        trigger_data = {"id": "trig-001", "enabled": False}

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = MagicMock(next_run_time=None)

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            with (
                patch("app.services.scheduler_service.update_trigger_last_run"),
                patch(
                    "app.services.scheduler_service.get_trigger",
                    return_value=trigger_data,
                ),
                patch(
                    "app.services.execution_service.ExecutionService.run_trigger",
                ) as mock_run,
                patch("app.services.scheduler_service.update_trigger_next_run"),
            ):
                SchedulerService._execute_trigger("trig-001")
                mock_run.assert_not_called()
        finally:
            SchedulerService._scheduler = original

    def test_execute_trigger_handles_missing_trigger(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = MagicMock(next_run_time=None)

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            with (
                patch("app.services.scheduler_service.update_trigger_last_run"),
                patch(
                    "app.services.scheduler_service.get_trigger",
                    return_value=None,
                ),
                patch(
                    "app.services.execution_service.ExecutionService.run_trigger",
                ) as mock_run,
                patch("app.services.scheduler_service.update_trigger_next_run"),
            ):
                SchedulerService._execute_trigger("trig-missing")
                mock_run.assert_not_called()
        finally:
            SchedulerService._scheduler = original

    def test_execute_trigger_handles_exception(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        trigger_data = {"id": "trig-001", "enabled": True}

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = MagicMock(next_run_time=None)

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            with (
                patch("app.services.scheduler_service.update_trigger_last_run"),
                patch(
                    "app.services.scheduler_service.get_trigger",
                    return_value=trigger_data,
                ),
                patch(
                    "app.services.execution_service.ExecutionService.run_trigger",
                    side_effect=RuntimeError("boom"),
                ),
                patch("app.services.scheduler_service.update_trigger_next_run"),
            ):
                # Should not raise
                SchedulerService._execute_trigger("trig-001")
        finally:
            SchedulerService._scheduler = original


class TestScheduleTeam:
    """Tests for SchedulerService.schedule_team() and unschedule_team()."""

    def _make_team(self, team_id="team-001", enabled=True, trigger_config=None):
        return {
            "id": team_id,
            "name": "Test Team",
            "enabled": enabled,
            "trigger_config": trigger_config
            or json.dumps(
                {
                    "schedule_type": "daily",
                    "schedule_time": "08:00",
                    "schedule_timezone": "UTC",
                }
            ),
        }

    def test_schedule_team_adds_job(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_job = MagicMock()
        mock_job.next_run_time = MagicMock(isoformat=lambda: "2026-03-07T08:00:00Z")
        # get_job: first in remove check (None), then after add_job (mock_job)
        mock_scheduler.get_job.side_effect = [None, mock_job]

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            SchedulerService.schedule_team(self._make_team())
            mock_scheduler.add_job.assert_called_once()
            call_kwargs = mock_scheduler.add_job.call_args
            assert call_kwargs[1]["id"] == "team_team-001"
        finally:
            SchedulerService._scheduler = original

    def test_schedule_team_skips_without_trigger_config(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = None

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            team = self._make_team(trigger_config="{}")
            SchedulerService.schedule_team(team)
            mock_scheduler.add_job.assert_not_called()
        finally:
            SchedulerService._scheduler = original

    def test_schedule_team_skips_invalid_json_config(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = None

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            team = self._make_team(trigger_config="{bad json}")
            SchedulerService.schedule_team(team)
            mock_scheduler.add_job.assert_not_called()
        finally:
            SchedulerService._scheduler = original

    def test_schedule_team_noop_without_scheduler(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        original = SchedulerService._scheduler
        SchedulerService._scheduler = None
        try:
            SchedulerService.schedule_team(self._make_team())
        finally:
            SchedulerService._scheduler = original

    def test_unschedule_team_removes_job(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = MagicMock()

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            SchedulerService.unschedule_team("team-001")
            mock_scheduler.remove_job.assert_called_once_with("team_team-001")
        finally:
            SchedulerService._scheduler = original

    def test_unschedule_team_noop_when_no_job(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = None

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            SchedulerService.unschedule_team("team-001")
            mock_scheduler.remove_job.assert_not_called()
        finally:
            SchedulerService._scheduler = original


class TestExecuteTeam:
    """Tests for SchedulerService._execute_team()."""

    def test_execute_team_calls_team_execution(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        team_data = {"id": "team-001", "name": "Test Team", "enabled": 1}

        with (
            patch("app.services.scheduler_service.get_team", return_value=team_data),
            patch(
                "app.services.team_execution_service.TeamExecutionService.execute_team",
            ) as mock_exec,
        ):
            SchedulerService._execute_team("team-001")
            mock_exec.assert_called_once()
            call_kwargs = mock_exec.call_args[1]
            assert call_kwargs["team_id"] == "team-001"
            assert call_kwargs["trigger_type"] == "scheduled"

    def test_execute_team_skips_disabled(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        team_data = {"id": "team-001", "enabled": 0}

        with (
            patch("app.services.scheduler_service.get_team", return_value=team_data),
            patch(
                "app.services.team_execution_service.TeamExecutionService.execute_team",
            ) as mock_exec,
        ):
            SchedulerService._execute_team("team-001")
            mock_exec.assert_not_called()

    def test_execute_team_handles_missing_team(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        with (
            patch("app.services.scheduler_service.get_team", return_value=None),
            patch(
                "app.services.team_execution_service.TeamExecutionService.execute_team",
            ) as mock_exec,
        ):
            SchedulerService._execute_team("team-missing")
            mock_exec.assert_not_called()

    def test_execute_team_handles_exception(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        team_data = {"id": "team-001", "enabled": 1}

        with (
            patch("app.services.scheduler_service.get_team", return_value=team_data),
            patch(
                "app.services.team_execution_service.TeamExecutionService.execute_team",
                side_effect=RuntimeError("team boom"),
            ),
        ):
            # Should not raise
            SchedulerService._execute_team("team-001")


class TestListJobsAndGetJobInfo:
    """Tests for SchedulerService.list_jobs() and get_job_info()."""

    def test_list_jobs_returns_dicts(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_job = MagicMock()
        mock_job.id = "trigger-trig-001"
        mock_job.name = "Test Job"
        mock_job.next_run_time = None
        mock_job.trigger = MagicMock(__str__=lambda s: "cron[hour='9']")

        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = [mock_job]

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            result = SchedulerService.list_jobs()
            assert len(result) == 1
            assert result[0]["job_id"] == "trigger-trig-001"
            assert result[0]["name"] == "Test Job"
            assert result[0]["next_run_time"] is None
        finally:
            SchedulerService._scheduler = original

    def test_list_jobs_empty_without_scheduler(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        original = SchedulerService._scheduler
        SchedulerService._scheduler = None
        try:
            assert SchedulerService.list_jobs() == []
        finally:
            SchedulerService._scheduler = original

    def test_get_job_info_found(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_job = MagicMock()
        mock_job.id = "trigger-trig-001"
        mock_job.name = "Test Job"
        mock_job.next_run_time = None
        mock_job.trigger = MagicMock(__str__=lambda s: "cron")

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = mock_job

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            result = SchedulerService.get_job_info("trig-001")
            assert result is not None
            assert result["job_id"] == "trigger-trig-001"
        finally:
            SchedulerService._scheduler = original

    def test_get_job_info_not_found(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        mock_scheduler.get_job.return_value = None

        original = SchedulerService._scheduler
        SchedulerService._scheduler = mock_scheduler
        try:
            assert SchedulerService.get_job_info("trig-missing") is None
        finally:
            SchedulerService._scheduler = original

    def test_get_job_info_none_without_scheduler(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        original = SchedulerService._scheduler
        SchedulerService._scheduler = None
        try:
            assert SchedulerService.get_job_info("trig-001") is None
        finally:
            SchedulerService._scheduler = original


class TestSchedulerInitShutdown:
    """Tests for SchedulerService.init() and shutdown()."""

    def test_init_skips_when_already_initialized(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        original_scheduler = SchedulerService._scheduler
        original_initialized = SchedulerService._initialized

        SchedulerService._initialized = True
        try:
            # init() returns early when _initialized is True, so no scheduler is created
            SchedulerService.init()
            # _initialized should still be True (unchanged)
            assert SchedulerService._initialized is True
        finally:
            SchedulerService._scheduler = original_scheduler
            SchedulerService._initialized = original_initialized

    def test_shutdown_resets_initialized(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        mock_scheduler = MagicMock()
        original_scheduler = SchedulerService._scheduler
        original_initialized = SchedulerService._initialized

        SchedulerService._scheduler = mock_scheduler
        SchedulerService._initialized = True
        try:
            SchedulerService.shutdown()
            assert SchedulerService._initialized is False
            mock_scheduler.shutdown.assert_called_once_with(wait=False)
        finally:
            SchedulerService._scheduler = original_scheduler
            SchedulerService._initialized = original_initialized

    def test_shutdown_noop_when_not_initialized(self, isolated_db):
        from app.services.scheduler_service import SchedulerService

        original_scheduler = SchedulerService._scheduler
        original_initialized = SchedulerService._initialized

        SchedulerService._scheduler = None
        SchedulerService._initialized = False
        try:
            SchedulerService.shutdown()
        finally:
            SchedulerService._scheduler = original_scheduler
            SchedulerService._initialized = original_initialized


# ===========================================================================
# RotationService — _get_remaining_capacity_pct
# ===========================================================================


class TestGetRemainingCapacityPct:
    """Tests for RotationService._get_remaining_capacity_pct()."""

    def test_returns_remaining_fraction(self, isolated_db):
        from datetime import datetime, timezone

        from app.services.rotation_service import RotationService

        mock_status = {
            "windows": [
                {"account_id": 1, "percentage": 60.0},
                {"account_id": 1, "percentage": 80.0},
            ],
        }

        with patch(
            "app.services.monitoring_service.MonitoringService.get_monitoring_status",
            return_value=mock_status,
        ):
            result = RotationService._get_remaining_capacity_pct(1, datetime.now(timezone.utc))

        # (100 - 80) / 100 = 0.2
        assert abs(result - 0.2) < 0.01

    def test_returns_neutral_when_no_windows(self, isolated_db):
        from datetime import datetime, timezone

        from app.services.rotation_service import RotationService

        mock_status = {"windows": []}

        with patch(
            "app.services.monitoring_service.MonitoringService.get_monitoring_status",
            return_value=mock_status,
        ):
            result = RotationService._get_remaining_capacity_pct(1, datetime.now(timezone.utc))

        assert result == 0.5

    def test_returns_neutral_when_no_account_windows(self, isolated_db):
        from datetime import datetime, timezone

        from app.services.rotation_service import RotationService

        mock_status = {"windows": [{"account_id": 999, "percentage": 90.0}]}

        with patch(
            "app.services.monitoring_service.MonitoringService.get_monitoring_status",
            return_value=mock_status,
        ):
            result = RotationService._get_remaining_capacity_pct(1, datetime.now(timezone.utc))

        assert result == 0.5

    def test_zero_utilization_returns_full_capacity(self, isolated_db):
        from datetime import datetime, timezone

        from app.services.rotation_service import RotationService

        mock_status = {"windows": [{"account_id": 1, "percentage": 0.0}]}

        with patch(
            "app.services.monitoring_service.MonitoringService.get_monitoring_status",
            return_value=mock_status,
        ):
            result = RotationService._get_remaining_capacity_pct(1, datetime.now(timezone.utc))

        assert abs(result - 1.0) < 0.01

    def test_full_utilization_returns_zero_capacity(self, isolated_db):
        from datetime import datetime, timezone

        from app.services.rotation_service import RotationService

        mock_status = {"windows": [{"account_id": 1, "percentage": 100.0}]}

        with patch(
            "app.services.monitoring_service.MonitoringService.get_monitoring_status",
            return_value=mock_status,
        ):
            result = RotationService._get_remaining_capacity_pct(1, datetime.now(timezone.utc))

        assert abs(result - 0.0) < 0.01


# ===========================================================================
# RotationEvaluator — Hysteresis and loop logic
# ===========================================================================


@pytest.fixture(autouse=True)
def reset_evaluator_state():
    """Reset RotationEvaluator class-level state before each test."""
    from app.services.rotation_evaluator import RotationEvaluator

    RotationEvaluator._evaluation_state = {}
    RotationEvaluator._lock = threading.Lock()
    yield
    RotationEvaluator._evaluation_state = {}


class TestRotationEvaluatorHysteresis:
    """Tests for RotationEvaluator._evaluate_single_execution() hysteresis logic."""

    def _mock_execution(self, execution_id="exec-001", account_id=1, trigger_id="trig-001"):
        return {
            "execution_id": execution_id,
            "account_id": account_id,
            "trigger_id": trigger_id,
            "trigger_type": "webhook",
            "prompt": "Run tests",
        }

    def test_hysteresis_increments_on_should_rotate(self, isolated_db):
        """Consecutive should_rotate=True polls increment the counter."""
        from app.services.rotation_evaluator import RotationEvaluator

        mock_exec_log = MagicMock()
        mock_exec_log.get_execution.return_value = self._mock_execution()

        mock_rotation = MagicMock()
        mock_rotation.should_rotate.return_value = {
            "should_rotate": True,
            "reason": "high utilization",
            "utilization_pct": 85.0,
        }

        with patch("app.database.get_trigger", return_value=None):
            RotationEvaluator._evaluate_single_execution("exec-001", mock_exec_log, mock_rotation)
            assert RotationEvaluator._evaluation_state["exec-001"]["consecutive_rotate_polls"] == 1

    def test_hysteresis_resets_on_safe(self, isolated_db):
        """A safe poll resets the counter to 0."""
        from app.services.rotation_evaluator import RotationEvaluator

        RotationEvaluator._evaluation_state["exec-001"] = {
            "consecutive_rotate_polls": 1,
            "last_evaluated": "2026-03-07T00:00:00Z",
        }

        mock_exec_log = MagicMock()
        mock_exec_log.get_execution.return_value = self._mock_execution()

        mock_rotation = MagicMock()
        mock_rotation.should_rotate.return_value = {
            "should_rotate": False,
            "reason": "utilization_safe",
            "utilization_pct": 40.0,
        }

        RotationEvaluator._evaluate_single_execution("exec-001", mock_exec_log, mock_rotation)
        assert RotationEvaluator._evaluation_state["exec-001"]["consecutive_rotate_polls"] == 0

    def test_hysteresis_threshold_triggers_rotation(self, isolated_db):
        """When consecutive polls reach threshold, rotation is dispatched and counter resets."""
        from app.services.rotation_evaluator import RotationEvaluator

        RotationEvaluator._evaluation_state["exec-001"] = {
            "consecutive_rotate_polls": 1,
            "last_evaluated": "2026-03-07T00:00:00Z",
        }

        mock_exec_log = MagicMock()
        mock_exec_log.get_execution.return_value = self._mock_execution()

        mock_rotation = MagicMock()
        mock_rotation.should_rotate.return_value = {
            "should_rotate": True,
            "reason": "high utilization",
            "utilization_pct": 85.0,
        }

        with (
            patch("app.database.get_trigger", return_value=None),
            patch.object(RotationEvaluator, "_get_hysteresis_threshold", return_value=2),
            patch("threading.Thread") as mock_thread_cls,
        ):
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            RotationEvaluator._evaluate_single_execution("exec-001", mock_exec_log, mock_rotation)

            mock_thread.start.assert_called_once()
            assert RotationEvaluator._evaluation_state["exec-001"]["consecutive_rotate_polls"] == 0

    def test_below_threshold_does_not_dispatch(self, isolated_db):
        """Counter below threshold does not trigger rotation."""
        from app.services.rotation_evaluator import RotationEvaluator

        mock_exec_log = MagicMock()
        mock_exec_log.get_execution.return_value = self._mock_execution()

        mock_rotation = MagicMock()
        mock_rotation.should_rotate.return_value = {
            "should_rotate": True,
            "reason": "high utilization",
            "utilization_pct": 85.0,
        }

        with (
            patch("app.database.get_trigger", return_value=None),
            patch.object(RotationEvaluator, "_get_hysteresis_threshold", return_value=3),
            patch("threading.Thread") as mock_thread_cls,
        ):
            # First poll: counter goes to 1 (threshold=3)
            RotationEvaluator._evaluate_single_execution("exec-001", mock_exec_log, mock_rotation)
            mock_thread_cls.assert_not_called()
            assert RotationEvaluator._evaluation_state["exec-001"]["consecutive_rotate_polls"] == 1

    def test_skips_execution_without_account_id(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        mock_exec_log = MagicMock()
        mock_exec_log.get_execution.return_value = {
            "execution_id": "exec-001",
            "account_id": None,
        }

        mock_rotation = MagicMock()

        RotationEvaluator._evaluate_single_execution("exec-001", mock_exec_log, mock_rotation)
        mock_rotation.should_rotate.assert_not_called()

    def test_skips_execution_not_found(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        mock_exec_log = MagicMock()
        mock_exec_log.get_execution.return_value = None

        mock_rotation = MagicMock()

        RotationEvaluator._evaluate_single_execution("exec-001", mock_exec_log, mock_rotation)
        mock_rotation.should_rotate.assert_not_called()


class TestRotationEvaluatorCleanup:
    """Tests for RotationEvaluator._cleanup_stale_state()."""

    def test_removes_inactive_executions(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        RotationEvaluator._evaluation_state = {
            "exec-001": {"consecutive_rotate_polls": 0},
            "exec-002": {"consecutive_rotate_polls": 1},
            "exec-003": {"consecutive_rotate_polls": 0},
        }

        RotationEvaluator._cleanup_stale_state(["exec-001"])

        assert "exec-001" in RotationEvaluator._evaluation_state
        assert "exec-002" not in RotationEvaluator._evaluation_state
        assert "exec-003" not in RotationEvaluator._evaluation_state

    def test_cleanup_with_empty_active_list(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        RotationEvaluator._evaluation_state = {
            "exec-001": {"consecutive_rotate_polls": 0},
        }

        RotationEvaluator._cleanup_stale_state([])
        assert RotationEvaluator._evaluation_state == {}

    def test_cleanup_noop_when_state_empty(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        RotationEvaluator._evaluation_state = {}
        RotationEvaluator._cleanup_stale_state(["exec-001"])
        assert RotationEvaluator._evaluation_state == {}


class TestRotationEvaluatorStatus:
    """Tests for RotationEvaluator.get_evaluator_status()."""

    def test_status_returns_expected_keys(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        RotationEvaluator._evaluation_state = {
            "exec-001": {"consecutive_rotate_polls": 2, "last_evaluated": "2026-03-07T00:00:00Z"},
        }

        with patch.object(RotationEvaluator, "_get_hysteresis_threshold", return_value=2):
            status = RotationEvaluator.get_evaluator_status()

        assert status["job_id"] == "rotation_evaluator"
        assert status["evaluation_interval_seconds"] == 15
        assert status["hysteresis_threshold"] == 2
        assert status["active_evaluations"] == 1
        assert "exec-001" in status["evaluation_states"]

    def test_status_empty_when_no_evaluations(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        with patch.object(RotationEvaluator, "_get_hysteresis_threshold", return_value=2):
            status = RotationEvaluator.get_evaluator_status()

        assert status["active_evaluations"] == 0
        assert status["evaluation_states"] == {}


class TestRotationEvaluatorDispatchRotation:
    """Tests for RotationEvaluator._dispatch_rotation()."""

    def test_dispatch_calls_execute_rotation(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        with patch(
            "app.services.rotation_service.RotationService.execute_rotation",
            return_value="exec-002",
        ) as mock_exec:
            RotationEvaluator._dispatch_rotation(
                "exec-001", {"id": "trig-001"}, "test message", {}, "webhook"
            )
            mock_exec.assert_called_once_with(
                execution_id="exec-001",
                trigger={"id": "trig-001"},
                message_text="test message",
                event={},
                trigger_type="webhook",
            )

    def test_dispatch_handles_exception_gracefully(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        with patch(
            "app.services.rotation_service.RotationService.execute_rotation",
            side_effect=RuntimeError("rotation failed"),
        ):
            RotationEvaluator._dispatch_rotation(
                "exec-001", {"id": "trig-001"}, "test message", {}, "webhook"
            )

    def test_dispatch_handles_none_continuation(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        with patch(
            "app.services.rotation_service.RotationService.execute_rotation",
            return_value=None,
        ):
            RotationEvaluator._dispatch_rotation(
                "exec-001", {"id": "trig-001"}, "test message", {}, "webhook"
            )


class TestEvaluateRunningSessions:
    """Tests for RotationEvaluator._evaluate_running_sessions() main loop."""

    def test_with_no_active_executions_cleans_stale(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        RotationEvaluator._evaluation_state = {
            "exec-stale": {"consecutive_rotate_polls": 1},
        }

        with patch(
            "app.services.process_manager.ProcessManager.get_active_executions",
            return_value=[],
        ):
            RotationEvaluator._evaluate_running_sessions()

        assert RotationEvaluator._evaluation_state == {}

    def test_iterates_active_executions(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        with (
            patch(
                "app.services.process_manager.ProcessManager.get_active_executions",
                return_value=["exec-001", "exec-002"],
            ),
            patch.object(RotationEvaluator, "_evaluate_single_execution") as mock_eval_fn,
        ):
            RotationEvaluator._evaluate_running_sessions()
            assert mock_eval_fn.call_count == 2

    def test_continues_on_single_exception(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        call_log = []

        def mock_eval_fn(execution_id, els, rs):
            call_log.append(execution_id)
            if execution_id == "exec-001":
                raise RuntimeError("boom")

        with (
            patch(
                "app.services.process_manager.ProcessManager.get_active_executions",
                return_value=["exec-001", "exec-002"],
            ),
            patch.object(RotationEvaluator, "_evaluate_single_execution", side_effect=mock_eval_fn),
        ):
            RotationEvaluator._evaluate_running_sessions()

        assert call_log == ["exec-001", "exec-002"]


class TestGetHysteresisThreshold:
    """Tests for RotationEvaluator._get_hysteresis_threshold()."""

    def test_reads_from_monitoring_config(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        with patch(
            "app.database.get_monitoring_config",
            return_value={"rotation_hysteresis_polls": 5},
        ):
            assert RotationEvaluator._get_hysteresis_threshold() == 5

    def test_falls_back_to_default_on_missing_key(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        with patch(
            "app.database.get_monitoring_config",
            return_value={},
        ):
            assert RotationEvaluator._get_hysteresis_threshold() == 2

    def test_falls_back_to_default_on_exception(self, isolated_db):
        from app.services.rotation_evaluator import RotationEvaluator

        with patch(
            "app.database.get_monitoring_config",
            side_effect=RuntimeError("db error"),
        ):
            assert RotationEvaluator._get_hysteresis_threshold() == 2
