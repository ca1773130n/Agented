"""Tests for post-execution notification hooks in ExecutionLogService."""

import logging
import sys
import types
from unittest.mock import MagicMock

from app.services.execution_log_service import ExecutionLogService


def _setup_mock_notification_module():
    """Create and inject a mock notification_service module."""
    mock_ns = MagicMock()
    mock_module = types.ModuleType("app.services.notification_service")
    mock_module.NotificationService = mock_ns
    sys.modules["app.services.notification_service"] = mock_module
    return mock_ns


def _cleanup_mock_notification_module():
    """Remove mock notification_service module."""
    sys.modules.pop("app.services.notification_service", None)
    # Also remove from parent module cache if cached
    parent = sys.modules.get("app.services")
    if parent and hasattr(parent, "notification_service"):
        delattr(parent, "notification_service")


def test_post_execution_hook_calls_notification_service(isolated_db):
    """finish_execution() calls NotificationService.on_execution_complete."""
    exec_id = ExecutionLogService.start_execution(
        trigger_id="bot-security",
        trigger_type="webhook",
        prompt="test prompt",
        backend_type="claude",
        command="claude -p test",
    )

    mock_ns = _setup_mock_notification_module()
    try:
        ExecutionLogService.finish_execution(exec_id, "completed", exit_code=0)
        mock_ns.on_execution_complete.assert_called_once()
        call_kwargs = mock_ns.on_execution_complete.call_args.kwargs
        assert call_kwargs["execution_id"] == exec_id
        assert call_kwargs["trigger_id"] == "bot-security"
        assert call_kwargs["status"] == "completed"
        assert "duration_ms" in call_kwargs
    finally:
        _cleanup_mock_notification_module()


def test_notification_failure_does_not_break_execution(isolated_db):
    """General exception in NotificationService does not break finish_execution()."""
    exec_id = ExecutionLogService.start_execution(
        trigger_id="bot-security",
        trigger_type="webhook",
        prompt="test prompt",
        backend_type="claude",
        command="claude -p test",
    )

    mock_ns = _setup_mock_notification_module()
    mock_ns.on_execution_complete.side_effect = RuntimeError("notification crash")
    try:
        # Should not raise
        ExecutionLogService.finish_execution(exec_id, "completed", exit_code=0)
    finally:
        _cleanup_mock_notification_module()

    # Verify execution was still properly finished in DB
    execution = ExecutionLogService.get_execution(exec_id)
    assert execution is not None
    assert execution["status"] == "completed"


def test_import_error_handled_gracefully(isolated_db, caplog):
    """ImportError is handled at DEBUG level (not WARNING) when NotificationService missing."""
    exec_id = ExecutionLogService.start_execution(
        trigger_id="bot-security",
        trigger_type="webhook",
        prompt="test prompt",
        backend_type="claude",
        command="claude -p test",
    )

    # Ensure notification_service is NOT importable
    _cleanup_mock_notification_module()

    with caplog.at_level(logging.DEBUG, logger="app.services.execution_log_service"):
        ExecutionLogService.finish_execution(exec_id, "completed", exit_code=0)

    # Verify execution still completed normally
    execution = ExecutionLogService.get_execution(exec_id)
    assert execution is not None
    assert execution["status"] == "completed"

    # Verify DEBUG log (not WARNING) was emitted
    debug_msgs = [r for r in caplog.records if r.levelname == "DEBUG"]
    assert any("NotificationService not available" in r.message for r in debug_msgs)

    # Verify no WARNING was emitted for ImportError
    warning_msgs = [
        r for r in caplog.records if r.levelname == "WARNING" and "NotificationService" in r.message
    ]
    assert len(warning_msgs) == 0


def test_correct_arguments_passed_to_notification(isolated_db):
    """Correct execution details are passed to NotificationService."""
    exec_id = ExecutionLogService.start_execution(
        trigger_id="bot-pr-review",
        trigger_type="github",
        prompt="check pr",
        backend_type="claude",
        command="claude -p check",
    )

    mock_ns = _setup_mock_notification_module()
    try:
        ExecutionLogService.finish_execution(
            exec_id, "failed", exit_code=1, error_message="process crashed"
        )

        call_kwargs = mock_ns.on_execution_complete.call_args.kwargs
        assert call_kwargs["execution_id"] == exec_id
        assert call_kwargs["trigger_id"] == "bot-pr-review"
        assert call_kwargs["status"] == "failed"
        assert isinstance(call_kwargs["duration_ms"], int)
        assert call_kwargs["duration_ms"] >= 0
    finally:
        _cleanup_mock_notification_module()
