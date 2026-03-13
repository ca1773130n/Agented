"""Tests for SuperAgentSessionService.get_or_create_session."""

from unittest.mock import patch

import pytest

from app.services.super_agent_session_service import (
    SessionLimitError,
    SuperAgentSessionService,
)


@pytest.fixture(autouse=True)
def clear_active_sessions():
    """Reset class-level session state before and after each test."""
    SuperAgentSessionService._active_sessions.clear()
    yield
    SuperAgentSessionService._active_sessions.clear()


def test_creates_new_session_when_none_exist():
    """Should call create_session and return the new session_id when no sessions exist."""
    with patch.object(
        SuperAgentSessionService, "create_session", return_value=("session-abc", None)
    ) as mock_create:
        result = SuperAgentSessionService.get_or_create_session("agent-1")

    assert result == "session-abc"
    mock_create.assert_called_once_with("agent-1")


def test_returns_existing_active_session():
    """Should return the existing session_id without creating a new session when one is active."""
    SuperAgentSessionService._active_sessions["session-xyz"] = {
        "session_id": "session-xyz",
        "super_agent_id": "agent-1",
        "status": "active",
        "conversation_log": [],
        "summary": None,
        "token_count": 0,
    }

    with patch.object(SuperAgentSessionService, "create_session") as mock_create:
        result = SuperAgentSessionService.get_or_create_session("agent-1")

    assert result == "session-xyz"
    mock_create.assert_not_called()


def test_resumes_paused_session():
    """Should call resume_session and return the paused session_id when a paused session exists."""
    SuperAgentSessionService._active_sessions["session-paused"] = {
        "session_id": "session-paused",
        "super_agent_id": "agent-1",
        "status": "paused",
        "conversation_log": [],
        "summary": None,
        "token_count": 0,
    }

    with (
        patch.object(
            SuperAgentSessionService, "resume_session", return_value=(True, None)
        ) as mock_resume,
        patch.object(SuperAgentSessionService, "create_session") as mock_create,
    ):
        result = SuperAgentSessionService.get_or_create_session("agent-1")

    assert result == "session-paused"
    mock_resume.assert_called_once_with("session-paused")
    mock_create.assert_not_called()


def test_raises_session_limit_error():
    """Should raise SessionLimitError when create_session returns an error."""
    with patch.object(
        SuperAgentSessionService,
        "create_session",
        return_value=(None, "Maximum concurrent sessions reached"),
    ):
        with pytest.raises(SessionLimitError, match="Maximum concurrent sessions reached"):
            SuperAgentSessionService.get_or_create_session("agent-1")
