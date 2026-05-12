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
    _render_tool_use,
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

    def test_system_event_is_filtered(self):
        """v0.7.48 — ``system/init`` events (with their multi-KB tool
        registry) must not surface in chat. Critical regression: when
        the reader's time-based flush kicked in on a split event, the
        partial bytes leaked through as plain text."""
        event = {
            "type": "system",
            "subtype": "init",
            "tools": ["Bash", "Read"] * 50,  # bulk it up like a real init
        }
        assert _extract_stream_json_text(json.dumps(event)) is None

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

    def test_result_event_is_suppressed(self):
        """v0.7.43 — ``result`` events are intentionally dropped because
        in ``--input-format stream-json`` interactive chat they duplicate
        the text the ``assistant`` event already emitted, producing a
        second copy of every answer in the chat panel."""
        for payload in (
            {"type": "result", "result": "Done!"},
            {"type": "result", "result": {"text": "Finished"}},
            {"type": "result", "result": {"content": "Wrapped"}},
            {"type": "result"},  # no result key at all
        ):
            assert _extract_stream_json_text(json.dumps(payload)) is None

    def test_content_block_delta_text(self):
        event = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"}}
        assert _extract_stream_json_text(json.dumps(event)) == "hi"


class TestRenderToolUse:
    """v0.7.48 — tool_use blocks render distinctly so the chat panel
    doesn't show ``Bash: ls /tmp`` as a sentence-shaped bubble."""

    def test_bash_command_uses_bash_fence(self):
        rendered = _render_tool_use(
            {"name": "Bash", "input": {"command": "ls /tmp"}}
        )
        assert "```bash" in rendered
        assert "ls /tmp" in rendered
        # Bold marker survives so MarkdownContent emphasizes the name.
        assert "**" in rendered

    def test_file_op_inlines_path(self):
        for name in ("Read", "Edit", "Write"):
            rendered = _render_tool_use(
                {"name": name, "input": {"file_path": "/etc/hosts"}}
            )
            assert name in rendered
            assert "`/etc/hosts`" in rendered
            # No code fence for short inline paths — too noisy.
            assert "```" not in rendered

    def test_grep_renders_pattern_and_path(self):
        rendered = _render_tool_use(
            {
                "name": "Grep",
                "input": {"pattern": "TODO", "path": "src/"},
            }
        )
        assert "Grep" in rendered
        assert "`TODO`" in rendered
        assert "`src/`" in rendered

    def test_mcp_tool_short_arg_inline(self):
        rendered = _render_tool_use(
            {
                "name": "mcp__plugin_context-mode__ctx_search",
                "input": {"query": "session manager"},
            }
        )
        assert "session manager" in rendered
        # Short payload stays inline rather than fenced.
        assert "```" not in rendered

    def test_mcp_tool_long_arg_uses_fence(self):
        long_query = "x" * 200
        rendered = _render_tool_use(
            {"name": "ctx_execute", "input": {"command": long_query}}
        )
        assert "```" in rendered
        # Truncated at the 600 cap; bigger payloads still serialize.
        assert "xxxx" in rendered

    def test_tool_without_input_renders_name_only(self):
        rendered = _render_tool_use({"name": "ToolSearch", "input": {}})
        assert "ToolSearch" in rendered
        assert "```" not in rendered

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

    def test_send_input_pipe_mode_writes_to_popen_stdin(self):
        """v0.7.44 — pipe-mode sessions write to ``popen.stdin`` instead
        of the PTY master fd. Reserve a session with a Popen mock and
        verify ``send_input`` routes through it."""
        fake_popen = MagicMock()
        fake_popen.stdin = MagicMock()
        si = _make_session_info(session_id="psess-pipe")
        si.popen = fake_popen
        ProjectSessionManager._sessions["psess-pipe"] = si

        with patch("os.write") as mock_pty_write:
            result = ProjectSessionManager.send_input("psess-pipe", "hello")

        assert result is True
        fake_popen.stdin.write.assert_called_once_with(b"hello\n")
        fake_popen.stdin.flush.assert_called_once()
        # PTY fd path must NOT be touched in pipe mode.
        mock_pty_write.assert_not_called()

    def test_send_input_pipe_mode_handles_broken_stdin(self):
        """A closed stdin (BrokenPipeError) should surface as a clean
        False, not a traceback into the route handler."""
        fake_popen = MagicMock()
        fake_popen.stdin = MagicMock()
        fake_popen.stdin.write.side_effect = BrokenPipeError("EPIPE")
        si = _make_session_info(session_id="psess-broken")
        si.popen = fake_popen
        ProjectSessionManager._sessions["psess-broken"] = si

        result = ProjectSessionManager.send_input("psess-broken", "hi")
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
# Pipe transport (v0.7.44, option A) — end-to-end roundtrip
# ---------------------------------------------------------------------------


class TestPipeTransport:
    """End-to-end test for ``use_pty=False`` against a real subprocess.

    Uses ``cat`` so the test does not depend on ``claude`` being on
    PATH; ``cat`` echoes stdin to stdout line-by-line which is enough
    to verify the pipe-mode plumbing (send_input → popen.stdin →
    child → popen.stdout → reader thread → ring buffer).
    """

    def test_use_pty_false_roundtrips_input(self, tmp_path):
        # ``isolated_db`` (autouse in conftest) gives us a working
        # temp DB. The session insert needs a real project row so the
        # FK is satisfied.
        from app.db.connection import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, created_at, updated_at) "
                "VALUES ('proj-pipe', 'pipe-test', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
            conn.commit()

        session_id = ProjectSessionManager.create_session(
            project_id="proj-pipe",
            cmd=["cat"],
            cwd=str(tmp_path),
            use_pty=False,
        )

        # Confirm the session is in pipe mode (not PTY).
        si = ProjectSessionManager._sessions[session_id]
        assert si.popen is not None

        sent = ProjectSessionManager.send_input(session_id, "hello-from-test")
        assert sent is True

        # The reader's select() timeout is 0.5s — poll briefly.
        import time as _time

        for _ in range(40):  # up to 4 seconds
            lines = ProjectSessionManager.get_output(session_id, last_n=10)
            if any("hello-from-test" in line for line in lines):
                break
            _time.sleep(0.1)
        else:
            pytest.fail(
                f"Pipe-mode roundtrip never surfaced the echoed line. "
                f"Buffer contents: {ProjectSessionManager.get_output(session_id)}"
            )

        ProjectSessionManager.stop_session(session_id)


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
