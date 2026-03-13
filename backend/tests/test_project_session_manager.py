"""Tests for ProjectSessionManager: PTY session lifecycle, pause/resume, output, cleanup."""

import json
import threading
from collections import deque
from datetime import datetime, timedelta
from queue import Queue
from unittest.mock import MagicMock, patch

import pytest

from app.services.project_session_manager import (
    ProjectSessionManager,
    SessionInfo,
    _extract_stream_json_text,
)


@pytest.fixture(autouse=True)
def reset_session_manager():
    """Reset ProjectSessionManager class-level state before and after each test."""
    ProjectSessionManager._sessions.clear()
    ProjectSessionManager._subscribers.clear()
    yield
    ProjectSessionManager._sessions.clear()
    ProjectSessionManager._subscribers.clear()


def _make_session_info(
    session_id="psess-test01",
    pid=1234,
    pgid=1234,
    status="active",
    paused=False,
    buffer_lines=None,
    idle_timeout_seconds=3600,
    max_lifetime_seconds=14400,
    created_at=None,
    last_activity_at=None,
    stream_json=False,
):
    """Helper to create a SessionInfo with sensible defaults."""
    now = datetime.now()
    ring_buffer = deque(maxlen=10000)
    if buffer_lines:
        ring_buffer.extend(buffer_lines)
    return SessionInfo(
        session_id=session_id,
        pid=pid,
        pgid=pgid,
        master_fd=99,
        ring_buffer=ring_buffer,
        reader_thread=MagicMock(spec=threading.Thread),
        status=status,
        created_at=created_at or now,
        last_activity_at=last_activity_at or now,
        paused=paused,
        idle_timeout_seconds=idle_timeout_seconds,
        max_lifetime_seconds=max_lifetime_seconds,
        stream_json=stream_json,
    )


# ---------------------------------------------------------------------------
# _extract_stream_json_text
# ---------------------------------------------------------------------------


class TestExtractStreamJsonText:
    def test_non_json_passthrough(self):
        assert _extract_stream_json_text("plain text line") == "plain text line"

    def test_assistant_event_with_text(self):
        event = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello world"}]},
        }
        result = _extract_stream_json_text(json.dumps(event))
        assert result == "Hello world"

    def test_assistant_event_with_tool_use(self):
        event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/tmp/x.py"}}
                ]
            },
        }
        result = _extract_stream_json_text(json.dumps(event))
        assert "Read" in result
        assert "/tmp/x.py" in result

    def test_result_event_string(self):
        event = {"type": "result", "result": "Done!"}
        assert _extract_stream_json_text(json.dumps(event)) == "Done!"

    def test_result_event_dict(self):
        event = {"type": "result", "result": {"text": "Finished"}}
        assert _extract_stream_json_text(json.dumps(event)) == "Finished"

    def test_content_block_delta_text(self):
        event = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"}}
        assert _extract_stream_json_text(json.dumps(event)) == "hi"

    def test_content_block_delta_non_text(self):
        event = {"type": "content_block_delta", "delta": {"type": "input_json_delta"}}
        assert _extract_stream_json_text(json.dumps(event)) is None

    def test_unknown_event_type_returns_none(self):
        event = {"type": "system", "data": "init"}
        assert _extract_stream_json_text(json.dumps(event)) is None

    def test_assistant_empty_content_returns_none(self):
        event = {"type": "assistant", "message": {"content": []}}
        assert _extract_stream_json_text(json.dumps(event)) is None


# ---------------------------------------------------------------------------
# SessionInfo dataclass
# ---------------------------------------------------------------------------


class TestSessionInfo:
    def test_defaults(self):
        si = _make_session_info()
        assert si.execution_type == "direct"
        assert si.execution_mode == "autonomous"
        assert si.idle_timeout_seconds == 3600
        assert si.max_lifetime_seconds == 14400
        assert si.paused is False
        assert si.stream_json is False
        assert si.worktree_path is None


# ---------------------------------------------------------------------------
# get_session_info
# ---------------------------------------------------------------------------


class TestGetSessionInfo:
    def test_returns_none_for_unknown(self):
        assert ProjectSessionManager.get_session_info("psess-nope") is None

    def test_returns_dict_for_known(self):
        si = _make_session_info(session_id="psess-abc123", pid=42, pgid=42)
        ProjectSessionManager._sessions["psess-abc123"] = si

        info = ProjectSessionManager.get_session_info("psess-abc123")
        assert info is not None
        assert info["session_id"] == "psess-abc123"
        assert info["pid"] == 42
        assert info["status"] == "active"
        assert info["paused"] is False
        assert info["execution_type"] == "direct"
        assert info["execution_mode"] == "autonomous"
        assert "created_at" in info
        assert "last_activity_at" in info


# ---------------------------------------------------------------------------
# get_output
# ---------------------------------------------------------------------------


class TestGetOutput:
    def test_empty_for_unknown_session(self):
        assert ProjectSessionManager.get_output("psess-nope") == []

    def test_returns_last_n_lines(self):
        si = _make_session_info(buffer_lines=["line1", "line2", "line3", "line4", "line5"])
        ProjectSessionManager._sessions["psess-buf"] = si

        result = ProjectSessionManager.get_output("psess-buf", last_n=3)
        assert result == ["line3", "line4", "line5"]

    def test_returns_all_if_fewer_than_n(self):
        si = _make_session_info(buffer_lines=["a", "b"])
        ProjectSessionManager._sessions["psess-buf2"] = si

        result = ProjectSessionManager.get_output("psess-buf2", last_n=100)
        assert result == ["a", "b"]


# ---------------------------------------------------------------------------
# pause_session / resume_session
# ---------------------------------------------------------------------------


class TestPauseResume:
    @patch("app.services.project_session_manager.update_project_session")
    def test_pause_session_success(self, mock_update):
        si = _make_session_info(session_id="psess-pause")
        ProjectSessionManager._sessions["psess-pause"] = si

        result = ProjectSessionManager.pause_session("psess-pause")
        assert result is True
        assert si.paused is True
        assert si.status == "paused"
        mock_update.assert_called_once_with("psess-pause", status="paused")

    def test_pause_session_not_found(self):
        assert ProjectSessionManager.pause_session("psess-nope") is False

    @patch("app.services.project_session_manager.update_project_session")
    def test_resume_session_success(self, mock_update):
        si = _make_session_info(session_id="psess-resume", paused=True, status="paused")
        ProjectSessionManager._sessions["psess-resume"] = si

        result = ProjectSessionManager.resume_session("psess-resume")
        assert result is True
        assert si.paused is False
        assert si.status == "active"
        mock_update.assert_called_once_with("psess-resume", status="active")

    def test_resume_session_not_found(self):
        assert ProjectSessionManager.resume_session("psess-nope") is False


# ---------------------------------------------------------------------------
# send_input
# ---------------------------------------------------------------------------


class TestSendInput:
    def test_send_input_not_found(self):
        assert ProjectSessionManager.send_input("psess-nope", "hello") is False

    def test_send_input_inactive_session(self):
        si = _make_session_info(session_id="psess-done", status="completed")
        ProjectSessionManager._sessions["psess-done"] = si
        assert ProjectSessionManager.send_input("psess-done", "hello") is False

    @patch("os.write")
    def test_send_input_success(self, mock_write):
        si = _make_session_info(session_id="psess-input")
        ProjectSessionManager._sessions["psess-input"] = si

        result = ProjectSessionManager.send_input("psess-input", "hello")
        assert result is True
        mock_write.assert_called_once_with(99, b"hello\n")

    @patch("os.write", side_effect=OSError("broken pipe"))
    def test_send_input_write_failure(self, mock_write):
        si = _make_session_info(session_id="psess-fail")
        ProjectSessionManager._sessions["psess-fail"] = si

        result = ProjectSessionManager.send_input("psess-fail", "hello")
        assert result is False


# ---------------------------------------------------------------------------
# stop_session
# ---------------------------------------------------------------------------


class TestStopSession:
    def test_stop_session_not_found(self):
        assert ProjectSessionManager.stop_session("psess-nope") is False

    @patch("app.services.project_session_manager.update_project_session")
    @patch("os.waitpid", return_value=(1234, 0))
    @patch("os.killpg")
    def test_stop_session_success(self, mock_killpg, mock_waitpid, mock_update):
        si = _make_session_info(session_id="psess-stop", pid=1234, pgid=1234)
        ProjectSessionManager._sessions["psess-stop"] = si

        result = ProjectSessionManager.stop_session("psess-stop")
        assert result is True
        mock_killpg.assert_called_once()
        mock_update.assert_called_once()
        assert si.status == "completed"

    @patch("app.services.project_session_manager.update_project_session")
    @patch("os.waitpid", side_effect=ChildProcessError)
    @patch("os.killpg", side_effect=ProcessLookupError)
    def test_stop_session_already_dead(self, mock_killpg, mock_waitpid, mock_update):
        si = _make_session_info(session_id="psess-dead", pid=9999, pgid=9999)
        ProjectSessionManager._sessions["psess-dead"] = si

        result = ProjectSessionManager.stop_session("psess-dead")
        assert result is True


# ---------------------------------------------------------------------------
# _format_sse
# ---------------------------------------------------------------------------


class TestFormatSse:
    def test_format(self):
        result = ProjectSessionManager._format_sse("output", {"line": "hello"})
        assert result.startswith("event: output\n")
        assert '"line": "hello"' in result
        assert result.endswith("\n\n")


# ---------------------------------------------------------------------------
# _broadcast
# ---------------------------------------------------------------------------


class TestBroadcast:
    def test_broadcast_to_subscribers(self):
        q1 = Queue()
        q2 = Queue()
        ProjectSessionManager._subscribers["psess-bc"] = [q1, q2]

        ProjectSessionManager._broadcast("psess-bc", "output", {"line": "hi"})

        msg1 = q1.get_nowait()
        msg2 = q2.get_nowait()
        assert msg1 == msg2
        assert "hi" in msg1

    def test_broadcast_no_subscribers(self):
        # Should not raise
        ProjectSessionManager._broadcast("psess-none", "output", {"line": "hi"})


# ---------------------------------------------------------------------------
# cleanup_dead_sessions
# ---------------------------------------------------------------------------


class TestCleanupDeadSessions:
    @patch("app.services.project_session_manager.update_project_session")
    @patch("os.kill", side_effect=ProcessLookupError)
    @patch(
        "app.services.project_session_manager.get_active_sessions",
        return_value=[{"id": "psess-dead1", "pid": 99999}],
    )
    def test_cleans_dead_processes(self, mock_get, mock_kill, mock_update):
        ProjectSessionManager.cleanup_dead_sessions()
        mock_update.assert_called_once()
        args, kwargs = mock_update.call_args
        assert args[0] == "psess-dead1"
        assert kwargs["status"] == "failed"

    @patch("os.kill")  # No error means process is alive
    @patch(
        "app.services.project_session_manager.get_active_sessions",
        return_value=[{"id": "psess-alive", "pid": 12345}],
    )
    def test_leaves_alive_processes(self, mock_get, mock_kill):
        with patch("app.services.project_session_manager.update_project_session") as mock_update:
            ProjectSessionManager.cleanup_dead_sessions()
            mock_update.assert_not_called()

    @patch(
        "app.services.project_session_manager.get_active_sessions",
        side_effect=Exception("DB error"),
    )
    def test_handles_db_error(self, mock_get):
        # Should not raise
        ProjectSessionManager.cleanup_dead_sessions()

    @patch("os.kill", side_effect=PermissionError)
    @patch(
        "app.services.project_session_manager.get_active_sessions",
        return_value=[{"id": "psess-perm", "pid": 1}],
    )
    def test_permission_error_leaves_session(self, mock_get, mock_kill):
        with patch("app.services.project_session_manager.update_project_session") as mock_update:
            ProjectSessionManager.cleanup_dead_sessions()
            mock_update.assert_not_called()

    @patch(
        "app.services.project_session_manager.get_active_sessions",
        return_value=[{"id": "psess-nopid", "pid": None}],
    )
    def test_skips_sessions_without_pid(self, mock_get):
        with patch("app.services.project_session_manager.update_project_session") as mock_update:
            ProjectSessionManager.cleanup_dead_sessions()
            mock_update.assert_not_called()


# ---------------------------------------------------------------------------
# check_resource_limits
# ---------------------------------------------------------------------------


class TestCheckResourceLimits:
    @patch.object(ProjectSessionManager, "stop_session")
    def test_idle_timeout(self, mock_stop):
        si = _make_session_info(
            session_id="psess-idle",
            idle_timeout_seconds=60,
            last_activity_at=datetime.now() - timedelta(seconds=120),
        )
        ProjectSessionManager._sessions["psess-idle"] = si

        ProjectSessionManager.check_resource_limits()
        mock_stop.assert_called_once_with("psess-idle")

    @patch.object(ProjectSessionManager, "stop_session")
    def test_max_lifetime(self, mock_stop):
        si = _make_session_info(
            session_id="psess-old",
            max_lifetime_seconds=60,
            created_at=datetime.now() - timedelta(seconds=120),
        )
        ProjectSessionManager._sessions["psess-old"] = si

        ProjectSessionManager.check_resource_limits()
        mock_stop.assert_called_once_with("psess-old")

    @patch.object(ProjectSessionManager, "stop_session")
    def test_within_limits(self, mock_stop):
        si = _make_session_info(session_id="psess-ok")
        ProjectSessionManager._sessions["psess-ok"] = si

        ProjectSessionManager.check_resource_limits()
        mock_stop.assert_not_called()

    @patch.object(ProjectSessionManager, "stop_session")
    def test_skips_completed_sessions(self, mock_stop):
        si = _make_session_info(
            session_id="psess-done",
            status="completed",
            idle_timeout_seconds=1,
            last_activity_at=datetime.now() - timedelta(seconds=9999),
        )
        ProjectSessionManager._sessions["psess-done"] = si

        ProjectSessionManager.check_resource_limits()
        mock_stop.assert_not_called()


# ---------------------------------------------------------------------------
# subscribe (partial — tests the non-blocking paths)
# ---------------------------------------------------------------------------


class TestSubscribe:
    def test_subscribe_completed_session(self):
        si = _make_session_info(session_id="psess-comp", status="completed", buffer_lines=["line1"])
        ProjectSessionManager._sessions["psess-comp"] = si

        events = list(ProjectSessionManager.subscribe("psess-comp"))
        # Should get catchup output + complete event
        assert len(events) == 2
        assert "line1" in events[0]
        assert "complete" in events[1]

    def test_subscribe_unknown_session(self):
        events = list(ProjectSessionManager.subscribe("psess-unknown"))
        assert len(events) == 1
        assert "error" in events[0]
        assert "Session not found" in events[0]
