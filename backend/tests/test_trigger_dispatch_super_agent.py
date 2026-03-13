"""Tests for super_agent dispatch routing in trigger_dispatcher."""

from unittest.mock import MagicMock, patch

import pytest


class TestTriggerDispatchSuperAgent:
    """Tests for dispatch_type=super_agent routing in dispatch_webhook_event."""

    def _make_trigger(self, **overrides):
        """Create a minimal trigger dict for testing."""
        base = {
            "id": "trig-test01",
            "name": "Test SA Trigger",
            "trigger_source": "webhook",
            "match_field_path": None,
            "match_field_value": None,
            "text_field_path": "text",
            "detection_keyword": "",
            "webhook_secret": None,
            "prompt_template": "Process: {message}",
            "dispatch_type": "bot",
            "super_agent_id": None,
        }
        base.update(overrides)
        return base

    @patch("app.services.trigger_dispatcher.check_and_insert_dedup_key", return_value=True)
    @patch("app.services.trigger_dispatcher.get_webhook_triggers")
    def test_super_agent_trigger_dispatches_to_session(
        self, mock_get_triggers, mock_dedup, isolated_db
    ):
        """When dispatch_type=super_agent, route to SuperAgentSessionService."""
        trigger = self._make_trigger(
            dispatch_type="super_agent",
            super_agent_id="sa-abc123",
        )
        mock_get_triggers.return_value = [trigger]

        mock_sa_service = MagicMock()
        mock_sa_service.get_or_create_session.return_value = "sess-001"
        mock_sa_service.send_message.return_value = (True, None)

        with (
            patch(
                "app.services.super_agent_session_service.SuperAgentSessionService",
                mock_sa_service,
            ),
            patch("app.db.triggers.create_execution_log") as mock_create_log,
            patch(
                "app.db.ids.generate_execution_id",
                return_value="exec-test-001",
            ),
        ):
            from app.services.trigger_dispatcher import dispatch_webhook_event

            result = dispatch_webhook_event(
                payload={"text": "hello world"},
                save_trigger_event_fn=MagicMock(),
            )

            assert result is True
            mock_sa_service.get_or_create_session.assert_called_once_with("sa-abc123")
            mock_sa_service.send_message.assert_called_once_with("sess-001", "Process: hello world")
            mock_create_log.assert_called_once()
            kwargs = mock_create_log.call_args.kwargs
            assert kwargs["source_type"] == "super_agent"
            assert kwargs["session_id"] == "sess-001"

    @patch("app.services.trigger_dispatcher.check_and_insert_dedup_key", return_value=True)
    @patch("app.services.trigger_dispatcher.get_webhook_triggers")
    def test_bot_trigger_still_uses_execution_queue(
        self, mock_get_triggers, mock_dedup, isolated_db
    ):
        """Default dispatch_type=bot triggers use ExecutionQueueService.enqueue."""
        trigger = self._make_trigger(dispatch_type="bot")
        mock_get_triggers.return_value = [trigger]

        mock_queue = MagicMock()

        with patch(
            "app.services.execution_queue_service.ExecutionQueueService",
            mock_queue,
        ):
            from app.services.trigger_dispatcher import dispatch_webhook_event

            result = dispatch_webhook_event(
                payload={"text": "hello world"},
                save_trigger_event_fn=MagicMock(),
            )

            assert result is True
            mock_queue.enqueue.assert_called_once_with(
                trigger_id="trig-test01",
                trigger_type="webhook",
                message_text="hello world",
                event_data={"text": "hello world"},
            )

    @patch("app.services.trigger_dispatcher.check_and_insert_dedup_key", return_value=True)
    @patch("app.services.trigger_dispatcher.get_webhook_triggers")
    def test_session_limit_error_logs_failure(self, mock_get_triggers, mock_dedup, isolated_db):
        """When SessionLimitError is raised, execution is logged as failed."""
        from app.services.super_agent_session_service import SessionLimitError

        trigger = self._make_trigger(
            dispatch_type="super_agent",
            super_agent_id="sa-abc123",
        )
        mock_get_triggers.return_value = [trigger]

        mock_sa_service = MagicMock()
        mock_sa_service.get_or_create_session.side_effect = SessionLimitError(
            "Maximum concurrent sessions reached"
        )

        with (
            patch(
                "app.services.super_agent_session_service.SuperAgentSessionService",
                mock_sa_service,
            ),
            patch("app.db.triggers.create_execution_log") as mock_create_log,
            patch("app.db.triggers.update_execution_log") as mock_update_log,
            patch(
                "app.db.ids.generate_execution_id",
                return_value="exec-test-002",
            ),
        ):
            from app.services.trigger_dispatcher import dispatch_webhook_event

            result = dispatch_webhook_event(
                payload={"text": "hello world"},
                save_trigger_event_fn=MagicMock(),
            )

            # Should not set triggered=True when session limit reached
            assert result is False
            mock_create_log.assert_called_once()
            mock_update_log.assert_called_once()
            update_kwargs = mock_update_log.call_args.kwargs
            assert update_kwargs["status"] == "failed"
            assert "Maximum concurrent sessions" in update_kwargs["error_message"]
