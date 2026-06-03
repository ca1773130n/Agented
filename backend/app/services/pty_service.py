"""PTY runner utility — runs CLI commands in a pseudo-terminal for full output capture.

Uses Python's built-in pty module (no extra dependencies). Designed for CLI tools
like codex and claude that require a TTY for interactive features like /status or /model.
"""

import logging
import os
import pty
import re
import select
import signal
import time
from typing import Optional

# Env vars that prevent CLI tools from launching (e.g. Claude nesting detection).
# These are cleared in the child process before exec.
_CHILD_ENV_CLEAR = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")

logger = logging.getLogger(__name__)

# Cursor positioning / forward-movement sequences — replaced with space to preserve word boundaries
# H = cursor position, f = horizontal/vertical position, G = cursor horizontal absolute,
# C = cursor forward (used by TUIs like Ink to space between words)
_CURSOR_POS_RE = re.compile(r"\x1b\[\d*(?:;\d*)*[HfGC]")
# Screen-erase sequences — replaced with newline
_ERASE_SCREEN_RE = re.compile(r"\x1b\[\d*J")

# Comprehensive regex for remaining ANSI/VT escape sequences (ECMA-48 + xterm/kitty)
_ANSI_RE = re.compile(
    r"\x1b"
    r"(?:"
    r"\[[\x20-\x3f]*[\x40-\x7e]"  # CSI: ESC [ (params/intermediate) final
    r"|\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC: ESC ] ... BEL or ST
    r"|[()][AB012]"  # Character set designators
    r"|[\x40-\x5f]"  # Fe sequences (ESC + 0x40-0x5f)
    r")"
    r"|\x0f|\x0e"  # SI/SO (shift in/out)
)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences, preserving word spacing.

    Cursor positioning (CSI H/f/G) is replaced with a space so that
    TUI-rendered text doesn't lose word boundaries.
    """
    text = _CURSOR_POS_RE.sub(" ", text)
    text = _ERASE_SCREEN_RE.sub("\n", text)
    text = _ANSI_RE.sub("", text)
    # Strip leftover control chars except newline, carriage return, tab
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    # Collapse runs of spaces (not newlines)
    text = re.sub(r" {2,}", " ", text)
    return text


class PtyRunner:
    """Runs commands in a PTY and captures output."""

    @staticmethod
    def run_command(cmd_list: list[str], timeout: float = 15) -> Optional[str]:
        """Run a command in a PTY and capture all output.

        Args:
            cmd_list: Command and arguments, e.g. ["codex", "--help"]
            timeout: Max seconds to wait for the command to finish

        Returns:
            Cleaned output string, or None on failure
        """
        master_fd = slave_fd = -1
        try:
            master_fd, slave_fd = pty.openpty()
            pid = os.fork()

            if pid == 0:
                # Child process
                os.close(master_fd)
                os.setsid()
                os.dup2(slave_fd, 0)
                os.dup2(slave_fd, 1)
                os.dup2(slave_fd, 2)
                if slave_fd > 2:
                    os.close(slave_fd)
                for _k in _CHILD_ENV_CLEAR:
                    os.environ.pop(_k, None)
                os.execvp(cmd_list[0], cmd_list)
                os._exit(1)

            # Parent process
            os.close(slave_fd)
            slave_fd = -1
            output = _read_until_done(master_fd, timeout)
            _cleanup_child(pid, master_fd)
            master_fd = -1
            return strip_ansi(output).strip() if output else None

        except Exception as e:
            logger.warning(f"PtyRunner.run_command failed for {cmd_list}: {e}")
            return None
        finally:
            # Close any fds still open — e.g. os.fork() raised after openpty,
            # or _read_until_done errored before _cleanup_child (01 M3).
            for _fd in (master_fd, slave_fd):
                if _fd is not None and _fd >= 0:
                    try:
                        os.close(_fd)
                    except OSError:
                        pass

    @staticmethod
    def run_interactive(
        cmd_list: list[str],
        input_lines: list[str],
        timeout: float = 20,
        ready_pattern: Optional[str] = None,
        settle_time: float = 1.0,
    ) -> Optional[str]:
        """Start an interactive session, send commands, capture output.

        Args:
            cmd_list: Command to launch, e.g. ["codex"]
            input_lines: Lines to send once the session is ready
            timeout: Max seconds for the entire interaction
            ready_pattern: Regex pattern to wait for before sending input.
                           If None, waits settle_time seconds for initial output.
            settle_time: Seconds to wait for output to settle after sending input

        Returns:
            Cleaned output string, or None on failure
        """
        try:
            master_fd, slave_fd = pty.openpty()
            pid = os.fork()

            if pid == 0:
                # Child process
                os.close(master_fd)
                os.setsid()
                os.dup2(slave_fd, 0)
                os.dup2(slave_fd, 1)
                os.dup2(slave_fd, 2)
                if slave_fd > 2:
                    os.close(slave_fd)
                for _k in _CHILD_ENV_CLEAR:
                    os.environ.pop(_k, None)
                os.execvp(cmd_list[0], cmd_list)
                os._exit(1)

            # Parent process
            os.close(slave_fd)

            deadline = time.monotonic() + timeout
            collected = ""

            # Wait for ready pattern or settle time
            if ready_pattern:
                pattern_re = re.compile(ready_pattern, re.IGNORECASE)
                while time.monotonic() < deadline:
                    chunk = _read_chunk(master_fd, min(1.0, deadline - time.monotonic()))
                    if chunk:
                        collected += chunk
                        if pattern_re.search(strip_ansi(collected)):
                            break
                else:
                    # Timeout waiting for ready pattern — try sending anyway
                    pass
            else:
                # Wait for initial output to settle
                chunk = _read_chunk(master_fd, min(settle_time, timeout))
                if chunk:
                    collected += chunk

            # Send each input line
            for line in input_lines:
                os.write(master_fd, (line + "\n").encode("utf-8"))
                time.sleep(0.3)  # Small delay between commands

            # Read remaining output until timeout
            remaining = max(0.5, deadline - time.monotonic())
            final_output = _read_until_done(master_fd, remaining)
            if final_output:
                collected += final_output

            _cleanup_child(pid, master_fd)
            return strip_ansi(collected).strip() if collected else None

        except Exception as e:
            logger.warning(f"PtyRunner.run_interactive failed for {cmd_list}: {e}")
            return None


def _read_chunk(fd: int, timeout: float) -> str:
    """Read available data from fd within timeout. Returns decoded string."""
    output = []
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            ready, _, _ = select.select([fd], [], [], min(remaining, 0.5))
            if ready:
                data = os.read(fd, 4096)
                if not data:
                    break
                output.append(data.decode("utf-8", errors="replace"))
            else:
                break
        except OSError:
            break
    return "".join(output)


def _read_until_done(fd: int, timeout: float) -> str:
    """Read from fd until no more data arrives or timeout is reached."""
    output = []
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            ready, _, _ = select.select([fd], [], [], min(remaining, 0.5))
            if ready:
                data = os.read(fd, 4096)
                if not data:
                    break
                output.append(data.decode("utf-8", errors="replace"))
            else:
                # No data available and we've waited — check if we have anything
                if output:
                    break
        except OSError:
            break
    return "".join(output)


def _cleanup_child(pid: int, master_fd: int) -> None:
    """Kill child process and close master fd, then reap it.

    A plain SIGTERM + non-blocking waitpid(WNOHANG) almost always returns
    (0, 0) because the child hasn't died yet — leaving a zombie per call (H3).
    Do a short bounded wait for the child to exit, escalate to SIGKILL, then a
    final blocking reap so no zombie accumulates.
    """
    try:
        os.close(master_fd)
    except OSError as e:
        logger.debug("PTY master fd close failed (pid=%d): %s", pid, e)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return  # Process already exited — nothing to reap

    deadline = time.monotonic() + 5.0
    try:
        while time.monotonic() < deadline:
            reaped, _ = os.waitpid(pid, os.WNOHANG)
            if reaped == pid:
                return
            time.sleep(0.05)
        # Still alive after SIGTERM — escalate and block until reaped.
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(pid, 0)
    except ChildProcessError as e:
        logger.debug("PTY waitpid failed (pid=%d): %s", pid, e)
