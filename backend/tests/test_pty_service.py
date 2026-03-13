"""Tests for PtyRunner and PTY helper functions.

Covers:
- strip_ansi: ANSI escape removal with cursor positioning, screen erase, CSI, OSC
- _read_chunk: reading from fd with timeout
- _read_until_done: reading until no more data or timeout
- _cleanup_child: process cleanup and fd close
- PtyRunner.run_command: command execution with mocked pty/fork
- PtyRunner.run_interactive: interactive session with mocked pty/fork
- Error handling (OSError, fork failure, process crashes)
"""

import re
from unittest.mock import MagicMock, call, patch

import pytest

from app.services.pty_service import (
    PtyRunner,
    _cleanup_child,
    _read_chunk,
    _read_until_done,
    strip_ansi,
)


# =============================================================================
# strip_ansi
# =============================================================================


class TestStripAnsi:
    """Test ANSI escape sequence removal."""

    def test_plain_text_unchanged(self):
        assert strip_ansi("hello world") == "hello world"

    def test_removes_csi_color_sequences(self):
        # ESC[31m = red foreground, ESC[0m = reset
        assert strip_ansi("\x1b[31mhello\x1b[0m") == "hello"

    def test_cursor_position_replaced_with_space(self):
        # ESC[H = cursor home, ESC[10;20H = move to row 10 col 20
        result = strip_ansi("hello\x1b[Hworld")
        assert "hello" in result
        assert "world" in result
        # Should have space between them (cursor pos -> space)
        assert "hello world" == result

    def test_cursor_forward_replaced_with_space(self):
        # ESC[5C = cursor forward 5 positions (used by TUIs like Ink)
        result = strip_ansi("word1\x1b[5Cword2")
        assert result == "word1 word2"

    def test_screen_erase_replaced_with_newline(self):
        # ESC[2J = clear entire screen
        result = strip_ansi("before\x1b[2Jafter")
        assert "before\nafter" == result

    def test_osc_sequences_removed(self):
        # OSC terminated by BEL
        text = "start\x1b]0;Window Title\x07end"
        assert strip_ansi(text) == "startend"

    def test_osc_terminated_by_st(self):
        # OSC terminated by ST (ESC \)
        text = "start\x1b]0;Title\x1b\\end"
        assert strip_ansi(text) == "startend"

    def test_charset_designators_removed(self):
        # ESC ( B = US ASCII charset
        assert strip_ansi("hello\x1b(Bworld") == "helloworld"

    def test_shift_in_out_removed(self):
        assert strip_ansi("hello\x0f\x0eworld") == "helloworld"

    def test_control_chars_stripped(self):
        # Control characters like BEL, BS, etc. removed
        assert strip_ansi("hel\x07lo") == "hello"

    def test_preserves_newlines_and_tabs(self):
        assert strip_ansi("line1\nline2\ttab") == "line1\nline2\ttab"

    def test_collapses_multiple_spaces(self):
        assert strip_ansi("hello   world") == "hello world"

    def test_complex_tui_output(self):
        # Simulate TUI output with mixed ANSI sequences
        text = "\x1b[2J\x1b[H\x1b[1;36m> Status\x1b[0m\x1b[5Cok"
        result = strip_ansi(text)
        assert "Status" in result
        assert "ok" in result

    def test_empty_string(self):
        assert strip_ansi("") == ""

    def test_cursor_horizontal_absolute(self):
        # ESC[10G = move to column 10
        result = strip_ansi("left\x1b[10Gright")
        assert "left" in result
        assert "right" in result


# =============================================================================
# _read_chunk
# =============================================================================


class TestReadChunk:
    """Test _read_chunk helper with mocked fd operations."""

    @patch("app.services.pty_service.os.read")
    @patch("app.services.pty_service.select.select")
    def test_reads_available_data(self, mock_select, mock_read):
        mock_select.return_value = ([42], [], [])
        mock_read.side_effect = [b"hello", b""]

        result = _read_chunk(42, timeout=1.0)
        assert result == "hello"

    @patch("app.services.pty_service.os.read")
    @patch("app.services.pty_service.select.select")
    def test_returns_empty_on_no_data(self, mock_select, mock_read):
        # select returns no ready fds
        mock_select.return_value = ([], [], [])

        result = _read_chunk(42, timeout=0.1)
        assert result == ""

    @patch("app.services.pty_service.select.select")
    def test_handles_oserror(self, mock_select):
        mock_select.side_effect = OSError("fd closed")
        result = _read_chunk(42, timeout=1.0)
        assert result == ""

    @patch("app.services.pty_service.os.read")
    @patch("app.services.pty_service.select.select")
    def test_reads_multiple_chunks(self, mock_select, mock_read):
        # Two chunks of data then fd becomes not ready
        mock_select.side_effect = [([42], [], []), ([42], [], []), ([], [], [])]
        mock_read.side_effect = [b"hel", b"lo"]

        result = _read_chunk(42, timeout=1.0)
        assert result == "hello"

    @patch("app.services.pty_service.os.read")
    @patch("app.services.pty_service.select.select")
    def test_decodes_with_replace(self, mock_select, mock_read):
        # Invalid UTF-8 bytes should be replaced, not raise
        mock_select.return_value = ([42], [], [])
        mock_read.side_effect = [b"hello\xff\xfeworld", b""]

        result = _read_chunk(42, timeout=1.0)
        assert "hello" in result
        assert "world" in result

    @patch("app.services.pty_service.time.monotonic")
    @patch("app.services.pty_service.select.select")
    def test_respects_timeout(self, mock_select, mock_monotonic):
        # Simulate timeout: first call within deadline, second past it
        mock_monotonic.side_effect = [0.0, 0.0, 2.0]  # start, loop check, exceeded
        mock_select.return_value = ([], [], [])

        result = _read_chunk(42, timeout=1.0)
        assert result == ""


# =============================================================================
# _read_until_done
# =============================================================================


class TestReadUntilDone:
    """Test _read_until_done helper."""

    @patch("app.services.pty_service.os.read")
    @patch("app.services.pty_service.select.select")
    def test_reads_until_empty(self, mock_select, mock_read):
        mock_select.side_effect = [([42], [], []), ([42], [], [])]
        mock_read.side_effect = [b"data", b""]

        result = _read_until_done(42, timeout=5.0)
        assert result == "data"

    @patch("app.services.pty_service.os.read")
    @patch("app.services.pty_service.select.select")
    def test_breaks_on_no_data_after_some_output(self, mock_select, mock_read):
        # Has data, then select returns nothing -> break because we have output
        mock_select.side_effect = [([42], [], []), ([], [], [])]
        mock_read.return_value = b"output"

        result = _read_until_done(42, timeout=5.0)
        assert result == "output"

    @patch("app.services.pty_service.select.select")
    def test_handles_oserror(self, mock_select):
        mock_select.side_effect = OSError("broken pipe")
        result = _read_until_done(42, timeout=1.0)
        assert result == ""

    @patch("app.services.pty_service.select.select")
    def test_returns_empty_on_timeout_with_no_output(self, mock_select):
        # No data at all, times out (select returns empty repeatedly)
        # Use side_effect to control loop iterations
        mock_select.return_value = ([], [], [])

        result = _read_until_done(42, timeout=0.1)
        assert result == ""


# =============================================================================
# _cleanup_child
# =============================================================================


class TestCleanupChild:
    """Test _cleanup_child process cleanup."""

    @patch("app.services.pty_service.os.waitpid")
    @patch("app.services.pty_service.os.kill")
    @patch("app.services.pty_service.os.close")
    def test_normal_cleanup(self, mock_close, mock_kill, mock_waitpid):
        _cleanup_child(pid=1234, master_fd=5)

        mock_close.assert_called_once_with(5)
        mock_kill.assert_called_once_with(1234, __import__("signal").SIGTERM)
        mock_waitpid.assert_called_once_with(1234, __import__("os").WNOHANG)

    @patch("app.services.pty_service.os.waitpid")
    @patch("app.services.pty_service.os.kill")
    @patch("app.services.pty_service.os.close")
    def test_close_oserror_handled(self, mock_close, mock_kill, mock_waitpid):
        mock_close.side_effect = OSError("bad fd")
        # Should not raise
        _cleanup_child(pid=1234, master_fd=5)
        mock_kill.assert_called_once()

    @patch("app.services.pty_service.os.waitpid")
    @patch("app.services.pty_service.os.kill")
    @patch("app.services.pty_service.os.close")
    def test_process_already_exited(self, mock_close, mock_kill, mock_waitpid):
        mock_kill.side_effect = ProcessLookupError("no such process")
        # Should not raise — this is the expected case
        _cleanup_child(pid=1234, master_fd=5)
        mock_close.assert_called_once()

    @patch("app.services.pty_service.os.waitpid")
    @patch("app.services.pty_service.os.kill")
    @patch("app.services.pty_service.os.close")
    def test_waitpid_child_process_error(self, mock_close, mock_kill, mock_waitpid):
        mock_waitpid.side_effect = ChildProcessError("no child")
        # Should not raise
        _cleanup_child(pid=1234, master_fd=5)


# =============================================================================
# PtyRunner.run_command
# =============================================================================


class TestPtyRunnerRunCommand:
    """Test PtyRunner.run_command with mocked pty/fork."""

    @patch("app.services.pty_service._cleanup_child")
    @patch("app.services.pty_service._read_until_done")
    @patch("app.services.pty_service.os.close")
    @patch("app.services.pty_service.os.fork")
    @patch("app.services.pty_service.pty.openpty")
    def test_successful_command(self, mock_openpty, mock_fork, mock_close, mock_read, mock_cleanup):
        mock_openpty.return_value = (10, 11)
        mock_fork.return_value = 42  # parent (pid > 0)
        mock_read.return_value = "command output"

        result = PtyRunner.run_command(["echo", "hello"], timeout=5)

        assert result == "command output"
        mock_close.assert_called_once_with(11)  # close slave_fd in parent
        mock_read.assert_called_once_with(10, 5)
        mock_cleanup.assert_called_once_with(42, 10)

    @patch("app.services.pty_service._cleanup_child")
    @patch("app.services.pty_service._read_until_done")
    @patch("app.services.pty_service.os.close")
    @patch("app.services.pty_service.os.fork")
    @patch("app.services.pty_service.pty.openpty")
    def test_returns_none_on_empty_output(
        self, mock_openpty, mock_fork, mock_close, mock_read, mock_cleanup
    ):
        mock_openpty.return_value = (10, 11)
        mock_fork.return_value = 42
        mock_read.return_value = ""

        result = PtyRunner.run_command(["cmd"])
        assert result is None

    @patch("app.services.pty_service._cleanup_child")
    @patch("app.services.pty_service._read_until_done")
    @patch("app.services.pty_service.os.close")
    @patch("app.services.pty_service.os.fork")
    @patch("app.services.pty_service.pty.openpty")
    def test_returns_none_on_none_output(
        self, mock_openpty, mock_fork, mock_close, mock_read, mock_cleanup
    ):
        mock_openpty.return_value = (10, 11)
        mock_fork.return_value = 42
        mock_read.return_value = None

        result = PtyRunner.run_command(["cmd"])
        assert result is None

    @patch("app.services.pty_service.pty.openpty")
    def test_returns_none_on_exception(self, mock_openpty):
        mock_openpty.side_effect = OSError("no pty available")
        result = PtyRunner.run_command(["cmd"])
        assert result is None

    @patch("app.services.pty_service._cleanup_child")
    @patch("app.services.pty_service._read_until_done")
    @patch("app.services.pty_service.os.close")
    @patch("app.services.pty_service.os.fork")
    @patch("app.services.pty_service.pty.openpty")
    def test_strips_ansi_from_output(
        self, mock_openpty, mock_fork, mock_close, mock_read, mock_cleanup
    ):
        mock_openpty.return_value = (10, 11)
        mock_fork.return_value = 42
        mock_read.return_value = "\x1b[31mcolored\x1b[0m"

        result = PtyRunner.run_command(["cmd"])
        assert result == "colored"

    @patch("app.services.pty_service._cleanup_child")
    @patch("app.services.pty_service._read_until_done")
    @patch("app.services.pty_service.os.close")
    @patch("app.services.pty_service.os.fork")
    @patch("app.services.pty_service.pty.openpty")
    def test_strips_whitespace(self, mock_openpty, mock_fork, mock_close, mock_read, mock_cleanup):
        mock_openpty.return_value = (10, 11)
        mock_fork.return_value = 42
        mock_read.return_value = "  output with spaces  "

        result = PtyRunner.run_command(["cmd"])
        assert result == "output with spaces"


# =============================================================================
# PtyRunner.run_interactive
# =============================================================================


class TestPtyRunnerRunInteractive:
    """Test PtyRunner.run_interactive with mocked pty/fork."""

    @patch("app.services.pty_service._cleanup_child")
    @patch("app.services.pty_service._read_until_done")
    @patch("app.services.pty_service._read_chunk")
    @patch("app.services.pty_service.os.write")
    @patch("app.services.pty_service.os.close")
    @patch("app.services.pty_service.os.fork")
    @patch("app.services.pty_service.pty.openpty")
    @patch("app.services.pty_service.time.sleep")
    def test_interactive_no_ready_pattern(
        self,
        mock_sleep,
        mock_openpty,
        mock_fork,
        mock_close,
        mock_write,
        mock_read_chunk,
        mock_read_done,
        mock_cleanup,
    ):
        mock_openpty.return_value = (10, 11)
        mock_fork.return_value = 42
        mock_read_chunk.return_value = "prompt> "
        mock_read_done.return_value = "response output"

        result = PtyRunner.run_interactive(
            cmd_list=["cli-tool"],
            input_lines=["/status"],
            timeout=10,
        )

        assert result is not None
        assert "prompt>" in result or "response output" in result
        # Verify input was sent
        mock_write.assert_called_once_with(10, b"/status\n")
        mock_cleanup.assert_called_once_with(42, 10)

    @patch("app.services.pty_service._cleanup_child")
    @patch("app.services.pty_service._read_until_done")
    @patch("app.services.pty_service._read_chunk")
    @patch("app.services.pty_service.os.write")
    @patch("app.services.pty_service.os.close")
    @patch("app.services.pty_service.os.fork")
    @patch("app.services.pty_service.pty.openpty")
    @patch("app.services.pty_service.time.sleep")
    @patch("app.services.pty_service.time.monotonic")
    def test_interactive_with_ready_pattern(
        self,
        mock_monotonic,
        mock_sleep,
        mock_openpty,
        mock_fork,
        mock_close,
        mock_write,
        mock_read_chunk,
        mock_read_done,
        mock_cleanup,
    ):
        mock_openpty.return_value = (10, 11)
        mock_fork.return_value = 42
        # Monotonic: start, deadline calc, loop check(s), remaining calc
        mock_monotonic.side_effect = [0.0, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
        mock_read_chunk.side_effect = ["Loading...", "Ready> "]
        mock_read_done.return_value = "final output"

        result = PtyRunner.run_interactive(
            cmd_list=["cli-tool"],
            input_lines=["/model"],
            timeout=20,
            ready_pattern=r"Ready>",
        )

        assert result is not None
        mock_write.assert_called_once_with(10, b"/model\n")

    @patch("app.services.pty_service._cleanup_child")
    @patch("app.services.pty_service._read_until_done")
    @patch("app.services.pty_service._read_chunk")
    @patch("app.services.pty_service.os.write")
    @patch("app.services.pty_service.os.close")
    @patch("app.services.pty_service.os.fork")
    @patch("app.services.pty_service.pty.openpty")
    @patch("app.services.pty_service.time.sleep")
    def test_interactive_multiple_inputs(
        self,
        mock_sleep,
        mock_openpty,
        mock_fork,
        mock_close,
        mock_write,
        mock_read_chunk,
        mock_read_done,
        mock_cleanup,
    ):
        mock_openpty.return_value = (10, 11)
        mock_fork.return_value = 42
        mock_read_chunk.return_value = "prompt"
        mock_read_done.return_value = "output"

        result = PtyRunner.run_interactive(
            cmd_list=["cli"],
            input_lines=["/status", "/model", "/quit"],
            timeout=10,
        )

        assert result is not None
        assert mock_write.call_count == 3
        mock_write.assert_any_call(10, b"/status\n")
        mock_write.assert_any_call(10, b"/model\n")
        mock_write.assert_any_call(10, b"/quit\n")

    @patch("app.services.pty_service.pty.openpty")
    def test_interactive_returns_none_on_exception(self, mock_openpty):
        mock_openpty.side_effect = OSError("pty error")
        result = PtyRunner.run_interactive(["cmd"], ["/status"])
        assert result is None

    @patch("app.services.pty_service._cleanup_child")
    @patch("app.services.pty_service._read_until_done")
    @patch("app.services.pty_service._read_chunk")
    @patch("app.services.pty_service.os.write")
    @patch("app.services.pty_service.os.close")
    @patch("app.services.pty_service.os.fork")
    @patch("app.services.pty_service.pty.openpty")
    @patch("app.services.pty_service.time.sleep")
    def test_interactive_returns_none_on_empty_output(
        self,
        mock_sleep,
        mock_openpty,
        mock_fork,
        mock_close,
        mock_write,
        mock_read_chunk,
        mock_read_done,
        mock_cleanup,
    ):
        mock_openpty.return_value = (10, 11)
        mock_fork.return_value = 42
        mock_read_chunk.return_value = ""
        mock_read_done.return_value = ""

        result = PtyRunner.run_interactive(["cmd"], ["/input"])
        assert result is None


# =============================================================================
# Child env clearing
# =============================================================================


class TestChildEnvClear:
    """Verify that _CHILD_ENV_CLEAR constants are correct."""

    def test_env_clear_constants(self):
        from app.services.pty_service import _CHILD_ENV_CLEAR

        assert "CLAUDECODE" in _CHILD_ENV_CLEAR
        assert "CLAUDE_CODE_ENTRYPOINT" in _CHILD_ENV_CLEAR
