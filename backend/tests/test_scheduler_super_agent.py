import pytest
from unittest.mock import patch, MagicMock


class TestSchedulerSuperAgentDispatch:
    def test_execute_trigger_routes_super_agent(self, isolated_db):
        from app.db import triggers as trigger_db
        from app.services.scheduler_service import SchedulerService

        tid = trigger_db.create_trigger(
            name="scheduled-sa",
            prompt_template="nightly scan",
            trigger_source="scheduled",
            schedule_type="daily",
            schedule_time="02:00",
            dispatch_type="super_agent",
            super_agent_id="sa-nightly",
        )

        with (
            patch("app.services.super_agent_session_service.SuperAgentSessionService") as mock_svc,
            patch("app.db.triggers.create_execution_log", return_value=True),
        ):
            mock_svc.get_or_create_session.return_value = "sess-cron"
            mock_svc.send_message.return_value = (True, None)

            SchedulerService._execute_trigger(tid)

            mock_svc.get_or_create_session.assert_called_once_with("sa-nightly")
            mock_svc.send_message.assert_called_once()

    def test_execute_trigger_bot_unchanged(self, isolated_db):
        from app.db import triggers as trigger_db
        from app.services.scheduler_service import SchedulerService

        tid = trigger_db.create_trigger(
            name="scheduled-bot",
            prompt_template="scan",
            trigger_source="scheduled",
            schedule_type="daily",
            schedule_time="03:00",
        )

        with patch("app.services.execution_service.ExecutionService") as mock_exec:
            SchedulerService._execute_trigger(tid)
            mock_exec.run_trigger.assert_called()
