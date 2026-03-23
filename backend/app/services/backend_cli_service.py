"""Backend CLI service for OAuth login and usage checking via PTY + SSE streaming.

Uses a pseudo-terminal so interactive CLI tools (claude, codex, gemini) produce
output even when not attached to a real terminal.
"""

import datetime
import json
import logging
import os
import pty
import re
import select
import signal
import subprocess
import threading
import time
import uuid
from queue import Empty, Queue
from typing import Dict, Generator, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from .pty_service import strip_ansi

logger = logging.getLogger(__name__)

# Timeout for waiting on user input (5 minutes)
INPUT_TIMEOUT_SECONDS = 300

# CLI command configuration per backend type
BACKEND_CLI_COMMANDS = {
    "claude": {"login": ["claude", "/login"], "usage": ["claude", "/usage"]},
    "codex": {"login": ["codex", "login", "--device-auth"], "usage": ["codex", "usage"]},
    "gemini": {"login": ["gemini", "auth", "login"]},
}

# OAuth URL detection patterns
OAUTH_URL_PATTERN = re.compile(
    r"(https?://\S*(?:auth|login|oauth|consent|accounts|codex/device)\S*)", re.IGNORECASE
)
# URL continuation: line that looks like a URL fragment (path, query params, etc.)
_URL_CONTINUATION_RE = re.compile(r"^[\w/%.=&+\-~?#@!$'()*,;:]+$")

# Env vars stripped from child processes to avoid nesting-detection failures
_ENV_STRIP = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")

# TUI row-change cursor sequences — any CSI that moves to a different row.
# Ink-based TUIs use cursor-down (B), cursor-up (A), and absolute positioning
# (H/f) instead of \n to separate lines. Pre-converting to \n ensures each
# menu option ends up on its own line for detection.
_ROW_CURSOR_RE = re.compile(r"\x1b\[\d*(?:;\d*)*[ABHfE]")

# Lines that are pure TUI decoration (box-drawing, separators, spinners) — skip in SSE output
_TUI_NOISE_RE = re.compile(
    r"^[\s│╭╰╮╯─┌┐└┘├┤┬┴┼▐▛▜▌▝▘═║╔╗╚╝╠╣╦╩╬█▀▄░▒▓\u2500-\u257f\u2580-\u259f\u2591-\u2593"
    r"✶✳✢·✻✽✦✧✹✴✵✷✸✺✼✾❃❊⊹⋆]*$"
)

# Spinner animation patterns — these lines repeat endlessly as the spinner redraws
_SPINNER_RE = re.compile(
    r"^[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏●○◉◎◌◍◐◑◒◓⣾⣽⣻⢿⡿⣟⣯⣷⠁⠂⠄⡀⢀⠠⠐⠈]?\s*(waiting|loading|spinner|connecting)",
    re.IGNORECASE,
)

# Maximum broadcast rate: suppress duplicate lines within this window (seconds)
_DEDUP_WINDOW = 2.0
_DEDUP_MAX_RECENT = 30

# Numbered menu detection: "❯ 1. Option text" or "● 1. Option text" or "  2 Option text"
# (dot optional — some TUI renders omit it; ● is gemini's selected-item marker)
_NUMBERED_OPTION_RE = re.compile(r"^\s*[❯●○◉]?\s*(\d+)\.?\s+(.+?)(?:\s*·\s*(.+))?$")

# Login success detection — when a CLI reports successful authentication
_LOGIN_SUCCESS_RE = re.compile(
    r"(?:"
    r"successfully\s+(?:logged|authenticated|signed)"
    r"|(?:now\s+)?logged\s+in\s+as\b"
    r"|authentication\s+(?:successful|complete)"
    r"|login\s+(?:successful|complete)"
    r"|you\s+are\s+(?:now\s+)?logged\s+in"
    r"|account\s+(?:added|connected|linked)"
    r")",
    re.IGNORECASE,
)


class BackendCLIService:
    """Service for running backend CLI commands with SSE streaming.

    Uses class-level state with @classmethod methods, matching the SetupExecutionService pattern.
    No DB persistence — ephemeral sessions with 5-minute TTL after completion.
    """

    # Active sessions: {session_id: {child_pid, master_fd, backend_id, ...}}
    _sessions: Dict[str, dict] = {}
    # Recently completed sessions (5-min TTL): {session_id: {status, finished_at, ...}}
    _completed: Dict[str, dict] = {}
    # Blocking events awaiting user response: {interaction_id: threading.Event}
    _pending_events: Dict[str, threading.Event] = {}
    # User responses keyed by interaction_id
    _pending_responses: Dict[str, dict] = {}
    # SSE subscriber queues per session_id
    _subscribers: Dict[str, List[Queue]] = {}
    # Current pending question per session_id (for reconnect)
    _current_question: Dict[str, dict] = {}
    # Lock for thread-safe operations
    _lock = threading.Lock()
    # Cleanup timers: {session_id: Timer}
    _cleanup_timers: Dict[str, threading.Timer] = {}

    # Backend type → environment variable for config directory override
    _CONFIG_ENV_MAP = {
        "claude": "CLAUDE_CONFIG_DIR",
        "codex": "CODEX_HOME",
        "gemini": "GEMINI_CLI_HOME",
    }

    @classmethod
    def start_session(
        cls,
        backend_id: str,
        backend_type: str,
        action: str,
        config_path: Optional[str] = None,
    ) -> str:
        """Start a CLI session in a PTY (login or usage).

        Args:
            backend_id: The backend entity ID.
            backend_type: Backend type (claude, codex, gemini).
            action: The action to perform (login, usage).
            config_path: Optional config directory for the target account.
                         Sets CLAUDE_CONFIG_DIR / GEMINI_CLI_HOME so the CLI
                         saves credentials to this account's directory.

        Returns:
            The session_id for the new session.
        """
        commands = BACKEND_CLI_COMMANDS.get(backend_type)
        if not commands:
            raise ValueError(f"Unsupported backend type: {backend_type}")

        cmd_list = commands.get(action)
        if not cmd_list:
            raise ValueError(f"Unsupported action '{action}' for backend '{backend_type}'")

        session_id = f"cli-{uuid.uuid4().hex[:8]}"
        logger.info(
            "Starting CLI session %s: type=%s action=%s config_path=%r",
            session_id,
            backend_type,
            action,
            config_path,
        )

        # Open a pseudo-terminal so the CLI sees a real TTY
        master_fd, slave_fd = pty.openpty()
        pid = os.fork()

        if pid == 0:
            # ── Child process ──
            os.close(master_fd)
            os.setsid()
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            for k in _ENV_STRIP:
                os.environ.pop(k, None)
            # Prevent CLI tools from opening a browser on the server.
            # BROWSER=echo makes them print the OAuth URL to stdout instead,
            # which we capture and forward to the user's browser via SSE.
            os.environ["BROWSER"] = "echo"
            os.environ.pop("DISPLAY", None)
            # Set config directory for the target account so credentials
            # are saved to the correct location.
            if config_path:
                env_var = cls._CONFIG_ENV_MAP.get(backend_type)
                if env_var:
                    expanded = os.path.expanduser(config_path)
                    os.makedirs(expanded, exist_ok=True)
                    os.environ[env_var] = expanded
            os.execvp(cmd_list[0], cmd_list)
            os._exit(1)

        # ── Parent process ──
        os.close(slave_fd)
        started_at = datetime.datetime.now().isoformat()

        # Capture the host URL from the Flask request context so the PTY
        # reader thread (which runs outside request context) can rewrite
        # OAuth redirect_uris to point back through our proxy.
        host_url = None
        try:
            from flask import request as flask_request

            host_url = flask_request.host_url.rstrip("/")
        except RuntimeError:
            pass  # Outside request context — host_url stays None

        with cls._lock:
            cls._sessions[session_id] = {
                "master_fd": master_fd,
                "child_pid": pid,
                "backend_id": backend_id,
                "backend_type": backend_type,
                "action": action,
                "status": "running",
                "started_at": started_at,
                "host_url": host_url,
            }
            cls._subscribers[session_id] = []

        # Single reader thread handles PTY output + child completion
        reader = threading.Thread(
            target=cls._pty_reader,
            args=(session_id, master_fd, pid),
            daemon=True,
        )
        reader.start()

        # Broadcast initial status
        cls._broadcast(
            session_id,
            "status",
            {"status": "running", "started_at": started_at, "session_id": session_id},
        )

        return session_id

    @classmethod
    def _pty_reader(cls, session_id: str, master_fd: int, pid: int) -> None:
        """Read from PTY master fd, detect URLs/interactions, and handle completion."""
        buffer = ""
        # Accumulate recent lines for multi-line interaction detection (numbered menus)
        recent_lines: list[str] = []
        idle_ticks = 0  # consecutive 1s timeouts with non-empty buffer
        # Track whether we've re-sent the action command after onboarding
        resent_action = False
        # Track whether the action command is already running (to avoid re-sending)
        action_started = False
        # OAuth URL accumulation: URL can span multiple wrapped lines
        pending_oauth_url: Optional[str] = None
        # Track login completion: explicit success message or post-interaction idle
        login_completed = False
        interaction_count = 0
        # Dedup: {line_text: last_broadcast_time} — suppress repeated lines within window
        _recent_broadcasts: dict[str, float] = {}
        try:
            while True:
                try:
                    ready, _, _ = select.select([master_fd], [], [], 1.0)
                except (ValueError, OSError):
                    break  # fd closed

                if not ready:
                    idle_ticks += 1
                    # Flush any pending OAuth URL on idle
                    if pending_oauth_url is not None and idle_ticks >= 2:
                        rewritten_url = cls._rewrite_oauth_url(session_id, pending_oauth_url)
                        logger.info(
                            "CLI %s: OAuth URL (flushed): %s…", session_id, rewritten_url[:80]
                        )
                        cls._broadcast(
                            session_id,
                            "oauth_url",
                            {
                                "url": rewritten_url,
                                "content": rewritten_url,
                                "timestamp": datetime.datetime.now().isoformat(),
                            },
                        )
                        pending_oauth_url = None
                    # After 2s of idle with accumulated lines, check for multi-line menus
                    if idle_ticks >= 2 and recent_lines:
                        interaction = cls._try_parse_menu(recent_lines)
                        if interaction:
                            logger.info(
                                "CLI %s: detected menu: prompt=%r opts=%r",
                                session_id,
                                interaction["prompt"],
                                [o[:30] for o in interaction.get("options", [])],
                            )
                            recent_lines.clear()
                            cls._handle_interaction(session_id, master_fd, interaction)
                            interaction_count += 1
                            logger.info(
                                "CLI %s: menu interaction completed, resuming reader", session_id
                            )
                            idle_ticks = 0
                            continue
                    # Check single-line prompt in buffer (no trailing \n)
                    if buffer.strip():
                        content = strip_ansi(buffer.rstrip("\r")).strip()
                        if content and not _TUI_NOISE_RE.match(content):
                            interaction = cls._try_parse_interaction(content)
                            if interaction:
                                buffer = ""
                                cls._handle_interaction(session_id, master_fd, interaction)
                                interaction_count += 1
                                idle_ticks = 0
                            elif idle_ticks >= 3:
                                # After 3s idle, flush buffer as log line so user sees it
                                recent_lines.append(content)
                                if len(recent_lines) > 15:
                                    recent_lines.pop(0)
                                cls._broadcast(
                                    session_id,
                                    "log",
                                    {
                                        "content": content,
                                        "stream": "stdout",
                                        "timestamp": datetime.datetime.now().isoformat(),
                                    },
                                )
                                buffer = ""
                    # Detect idle REPL prompt: if CLI landed at its main input prompt
                    # (e.g. after onboarding), re-send the action command (e.g. /login).
                    # Only fire if recent_lines has no pending menu options (to avoid
                    # sending \n that would accidentally confirm a menu selection).
                    has_pending_options = any(_NUMBERED_OPTION_RE.match(rl) for rl in recent_lines)
                    # Force-complete login sessions when:
                    # (a) explicit success pattern detected + 2s idle, or
                    # (b) at least 1 interaction handled + 10s idle (CLI returned to REPL)
                    if action_started and not has_pending_options and interaction_count >= 1:
                        with cls._lock:
                            session = cls._sessions.get(session_id, {})
                        if session.get("action") == "login":
                            if (login_completed and idle_ticks >= 2) or idle_ticks >= 10:
                                logger.info(
                                    "CLI %s: login done (success_detected=%s, "
                                    "interactions=%d, idle=%ds), terminating",
                                    session_id,
                                    login_completed,
                                    interaction_count,
                                    idle_ticks,
                                )
                                try:
                                    os.close(master_fd)
                                except OSError:
                                    pass  # Intentionally silenced: cleanup/IO operation is best-effort
                                try:
                                    os.kill(pid, signal.SIGTERM)
                                except ProcessLookupError:
                                    pass  # Intentionally silenced: process already terminated
                                try:
                                    os.waitpid(pid, os.WNOHANG)
                                except ChildProcessError:
                                    pass  # Intentionally silenced: child process already reaped
                                cls._finish_session(session_id, "completed", 0, None)
                                return
                    if (
                        not resent_action
                        and not action_started
                        and not has_pending_options
                        and idle_ticks >= 5
                    ):
                        with cls._lock:
                            session = cls._sessions.get(session_id, {})
                        action = session.get("action")
                        if action:
                            action_cmd = cls._get_repl_command(
                                session.get("backend_type", ""), action
                            )
                            if action_cmd:
                                logger.info(
                                    "CLI %s: idle %ds at REPL, re-sending %r",
                                    session_id,
                                    idle_ticks,
                                    action_cmd,
                                )
                                try:
                                    os.write(master_fd, (action_cmd + "\n").encode())
                                except OSError:
                                    pass  # Intentionally silenced: cleanup/IO operation is best-effort
                                resent_action = True
                                idle_ticks = 0
                    continue

                idle_ticks = 0

                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    break  # EIO — child exited
                if not data:
                    break  # EOF

                raw_text = data.decode("utf-8", errors="replace")
                # TUI cursor-positioning (ESC[...H/f) starts a new row —
                # convert to \n so menu options land on separate lines.
                raw_text = _ROW_CURSOR_RE.sub("\n", raw_text)
                buffer += raw_text

                # Process complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    content = strip_ansi(line.replace("\r", " "))

                    # strip_ansi can introduce \n (from screen-erase replacement),
                    # so re-split to handle each sub-line individually.
                    for stripped_raw in content.split("\n"):
                        stripped = stripped_raw.strip()
                        if not stripped:
                            continue

                        # Skip TUI decoration lines (box-drawing, separators)
                        if _TUI_NOISE_RE.match(stripped):
                            continue

                        # Skip spinner animation lines
                        if _SPINNER_RE.match(stripped):
                            continue

                        # Track recent lines for multi-line menu detection
                        recent_lines.append(stripped)
                        if len(recent_lines) > 15:
                            recent_lines.pop(0)

                        # Detect that the action command has started running.
                        # Use specific phrases to avoid false positives from
                        # onboarding text like "Claude account with subscription".
                        if not action_started:
                            lower = stripped.lower()
                            if any(
                                kw in lower
                                for kw in (
                                    "login method",
                                    "select login",
                                    "sign in",
                                    "authenticat",
                                    "opening browser",
                                    "usage",
                                    "waiting for auth",
                                    "trust",
                                )
                            ):
                                action_started = True

                        # OAuth URL accumulation
                        if pending_oauth_url is not None:
                            if _URL_CONTINUATION_RE.match(stripped):
                                pending_oauth_url += stripped
                                continue
                            else:
                                rewritten_url = cls._rewrite_oauth_url(
                                    session_id, pending_oauth_url
                                )
                                logger.info(
                                    "CLI %s: OAuth URL (assembled): %s…",
                                    session_id,
                                    rewritten_url[:80],
                                )
                                cls._broadcast(
                                    session_id,
                                    "oauth_url",
                                    {
                                        "url": rewritten_url,
                                        "content": rewritten_url,
                                        "timestamp": datetime.datetime.now().isoformat(),
                                    },
                                )
                                pending_oauth_url = None

                        # Check for OAuth URLs (start of a new URL)
                        url_match = OAUTH_URL_PATTERN.search(stripped)
                        if url_match:
                            pending_oauth_url = url_match.group(1)
                            continue

                        # Try to parse as single-line interaction
                        interaction = cls._try_parse_interaction(stripped)
                        if interaction:
                            logger.info("CLI %s: detected interaction: %r", session_id, interaction)
                            recent_lines.clear()
                            cls._handle_interaction(session_id, master_fd, interaction)
                            interaction_count += 1
                            continue

                        # Dedup: suppress lines repeated within the window
                        now_ts = time.monotonic()
                        last_seen = _recent_broadcasts.get(stripped)
                        if last_seen is not None and (now_ts - last_seen) < _DEDUP_WINDOW:
                            continue  # skip duplicate
                        _recent_broadcasts[stripped] = now_ts
                        # Prune old entries to avoid memory growth
                        if len(_recent_broadcasts) > _DEDUP_MAX_RECENT:
                            cutoff = now_ts - _DEDUP_WINDOW
                            _recent_broadcasts = {
                                k: v for k, v in _recent_broadcasts.items() if v > cutoff
                            }

                        # Broadcast as log line
                        cls._broadcast(
                            session_id,
                            "log",
                            {
                                "content": stripped,
                                "stream": "stdout",
                                "timestamp": datetime.datetime.now().isoformat(),
                            },
                        )

                        # Check for login success patterns
                        if not login_completed and _LOGIN_SUCCESS_RE.search(stripped):
                            login_completed = True
                            logger.info(
                                "CLI %s: login success detected: %s",
                                session_id,
                                stripped[:80],
                            )

                # After processing all lines from this chunk, check if
                # recent_lines contains numbered menu options.
                opt_count = sum(1 for rl in recent_lines if _NUMBERED_OPTION_RE.match(rl))

                if opt_count >= 2:
                    # Brief peek for more data — CLI may still be writing options.
                    try:
                        peek_ready, _, _ = select.select([master_fd], [], [], 0.3)
                        if peek_ready:
                            extra = os.read(master_fd, 4096)
                            if extra:
                                buffer += extra.decode("utf-8", errors="replace")
                                while "\n" in buffer:
                                    ln, buffer = buffer.split("\n", 1)
                                    c = strip_ansi(ln.rstrip("\r"))
                                    for sr in c.split("\n"):
                                        s = sr.strip()
                                        if not s or _TUI_NOISE_RE.match(s):
                                            continue
                                        recent_lines.append(s)
                                        if len(recent_lines) > 15:
                                            recent_lines.pop(0)
                                        cls._broadcast(
                                            session_id,
                                            "log",
                                            {
                                                "content": s,
                                                "stream": "stdout",
                                                "timestamp": datetime.datetime.now().isoformat(),
                                            },
                                        )
                    except (ValueError, OSError):
                        pass  # Intentionally silenced: cleanup/IO operation is best-effort

                    interaction = cls._try_parse_menu(recent_lines)
                    if interaction:
                        recent_lines.clear()
                        cls._handle_interaction(session_id, master_fd, interaction)
                        interaction_count += 1
        except Exception as e:
            logger.error(f"CLI {session_id}: PTY reader error: {e}", exc_info=True)

        # Flush remaining buffer
        if buffer.strip():
            content = strip_ansi(buffer.rstrip("\r\n")).strip()
            if content and not _TUI_NOISE_RE.match(content):
                cls._broadcast(
                    session_id,
                    "log",
                    {
                        "content": content,
                        "stream": "stdout",
                        "timestamp": datetime.datetime.now().isoformat(),
                    },
                )

        # Wait for child and finalize
        exit_code = cls._reap_child(pid)

        # Close master fd
        try:
            os.close(master_fd)
        except OSError:
            pass  # Intentionally silenced: cleanup/IO operation is best-effort

        # Check if already cancelled
        with cls._lock:
            if session_id not in cls._sessions:
                return

        status = "completed" if exit_code == 0 else "error"
        error_message = None if exit_code == 0 else f"Process exited with code {exit_code}"
        cls._finish_session(session_id, status, exit_code, error_message)

    @classmethod
    def _handle_interaction(cls, session_id: str, master_fd: int, interaction: dict) -> None:
        """Handle an interactive question from the CLI."""
        interaction_id = str(uuid.uuid4())

        event = threading.Event()
        with cls._lock:
            cls._pending_events[interaction_id] = event

        question_data = {
            "interaction_id": interaction_id,
            "question_type": interaction["question_type"],
            "prompt": interaction["prompt"],
            "options": interaction.get("options"),
        }

        with cls._lock:
            cls._current_question[session_id] = question_data
            if session_id in cls._sessions:
                cls._sessions[session_id]["status"] = "waiting_input"

        cls._broadcast(session_id, "question", question_data)

        responded = event.wait(timeout=INPUT_TIMEOUT_SECONDS)

        if not responded:
            logger.warning(f"CLI {session_id}: input timeout for {interaction_id}")
            cls._broadcast(
                session_id,
                "error",
                {"message": "Input timeout — no response received within 5 minutes"},
            )
            with cls._lock:
                if session_id in cls._sessions:
                    cls._sessions[session_id]["status"] = "error"
                cls._pending_events.pop(interaction_id, None)
                cls._current_question.pop(session_id, None)
            return

        with cls._lock:
            response = cls._pending_responses.pop(interaction_id, {})
            cls._pending_events.pop(interaction_id, None)
            cls._current_question.pop(session_id, None)

        # Write response to PTY
        logger.info(
            "CLI %s: writing response: %r (is_json=%s, has_option_nums=%s)",
            session_id,
            response,
            interaction.get("is_json_tool_use"),
            bool(interaction.get("_option_numbers")),
        )
        try:
            if interaction.get("is_json_tool_use"):
                response_json = json.dumps({"type": "tool_result", **response})
                os.write(master_fd, (response_json + "\n").encode("utf-8"))
            elif interaction.get("_option_numbers"):
                # Numbered menu: navigate to the selected option using arrow keys + Enter
                answer = response.get("answer", "")
                options = interaction.get("options", [])
                interaction["_option_numbers"]
                try:
                    idx = options.index(answer)
                    logger.info(
                        "CLI %s: menu selection idx=%d, sending %d down arrows + Enter",
                        session_id,
                        idx,
                        idx,
                    )
                    # Arrow down to reach the option (first option is index 0, already selected)
                    for _ in range(idx):
                        os.write(master_fd, b"\x1b[B")  # Down arrow
                        time.sleep(0.05)
                    os.write(master_fd, b"\r")  # Enter to select
                except (ValueError, IndexError):
                    logger.warning(
                        "CLI %s: option not found, sending raw answer: %r", session_id, answer
                    )
                    # Fallback: just send the answer text
                    os.write(master_fd, (str(answer) + "\n").encode("utf-8"))
            else:
                answer = response.get("answer", "")
                os.write(master_fd, (str(answer) + "\n").encode("utf-8"))
        except OSError as e:
            logger.warning(f"CLI {session_id}: PTY write failed: {e}")

        with cls._lock:
            if session_id in cls._sessions:
                cls._sessions[session_id]["status"] = "running"

    @staticmethod
    def _reap_child(pid: int) -> int:
        """Wait for child process and return exit code."""
        try:
            _, wait_status = os.waitpid(pid, 0)
            if os.WIFEXITED(wait_status):
                return os.WEXITSTATUS(wait_status)
            if os.WIFSIGNALED(wait_status):
                return -(os.WTERMSIG(wait_status))
            return -1
        except ChildProcessError:
            return -1

    @classmethod
    def _finish_session(
        cls,
        session_id: str,
        status: str,
        exit_code: int = None,
        error_message: str = None,
    ) -> None:
        """Finalize a CLI session: broadcast completion, move to completed, schedule cleanup."""
        finished_at = datetime.datetime.now().isoformat()

        # Broadcast completion
        cls._broadcast(
            session_id,
            "complete",
            {
                "status": status,
                "exit_code": exit_code,
                "error_message": error_message,
                "finished_at": finished_at,
            },
        )

        # Move from active to completed
        with cls._lock:
            session_info = cls._sessions.pop(session_id, {})
            cls._current_question.pop(session_id, None)

            cls._completed[session_id] = {
                "session_id": session_id,
                "backend_id": session_info.get("backend_id"),
                "backend_type": session_info.get("backend_type"),
                "action": session_info.get("action"),
                "status": status,
                "exit_code": exit_code,
                "error_message": error_message,
                "started_at": session_info.get("started_at"),
                "finished_at": finished_at,
            }

            # Signal all subscriber queues with None (end of stream)
            if session_id in cls._subscribers:
                for q in cls._subscribers[session_id]:
                    q.put(None)
                cls._subscribers.pop(session_id, None)

        # Schedule cleanup of completed session after 5 minutes
        timer = threading.Timer(300, cls._cleanup_completed, args=[session_id])
        timer.daemon = True
        timer.start()
        with cls._lock:
            cls._cleanup_timers[session_id] = timer

    @classmethod
    def _cleanup_completed(cls, session_id: str) -> None:
        """Remove a completed session from the completed dict after TTL."""
        with cls._lock:
            cls._completed.pop(session_id, None)
            cls._cleanup_timers.pop(session_id, None)

    @classmethod
    def _try_parse_interaction(cls, content: str) -> Optional[dict]:
        """Try to parse a line as an interaction request.

        Returns:
            Dict with question_type, prompt, options, is_json_tool_use or None.
        """
        # Try JSON tool_use parsing
        try:
            data = json.loads(content)
            if isinstance(data, dict) and data.get("type") == "tool_use":
                name = data.get("name", "")
                if name in ("AskUserQuestion", "ask_user", "UserInput"):
                    input_data = data.get("input", {})
                    return {
                        "question_type": input_data.get("type", "text"),
                        "prompt": input_data.get("question") or input_data.get("prompt", ""),
                        "options": input_data.get("options"),
                        "is_json_tool_use": True,
                    }
        except (json.JSONDecodeError, TypeError):
            pass  # Intentionally silenced: malformed data handled gracefully

        # Regex fallback: detect interactive CLI prompts.
        # Pattern: "? <prompt text>:" or "? <prompt text> [option1/option2]"
        # Must end with colon, question mark, or bracket options to distinguish from
        # help hints like "? for shortcuts" which are NOT interactive prompts.
        match = re.match(
            r"^\?\s+(.+?)\s*(?:\[([^\]]+)\])\s*$"  # "? text [opt/opt]"
            r"|^\?\s+(.+?[?:])\s*$",  # "? text:" or "? text?"
            content,
        )
        if match:
            prompt = (match.group(1) or match.group(3) or "").strip()
            options_str = match.group(2)
            options = [o.strip() for o in options_str.split("/")] if options_str else None
            return {
                "question_type": "select" if options else "text",
                "prompt": prompt,
                "options": options,
                "is_json_tool_use": False,
            }

        # Detect text input prompts ending with ">" (e.g. "Paste code here if prompted >")
        match = re.match(r"^(.+?)\s*>\s*$", content)
        if match:
            prompt_text = match.group(1).strip()
            # Must be a reasonably long prompt to avoid false positives
            if len(prompt_text) > 10:
                return {
                    "question_type": "text",
                    "prompt": prompt_text,
                    "options": None,
                    "is_json_tool_use": False,
                }

        return None

    @classmethod
    def _try_parse_menu(cls, recent_lines: list[str]) -> Optional[dict]:
        """Detect numbered selection menus from recent TUI output.

        Searches backwards for the most recent consecutive run of numbered
        options (1, 2, 3, ..., n). When the sequence breaks (gaps, duplicates,
        or out-of-order numbers), discards and restarts from the current number.
        This handles mixed output like code line numbers + menu options.

        Requires at least one option line to have a TUI menu marker (❯ or ·)
        to distinguish real menus from code line numbers.
        """
        options: list[tuple[int, str]] = []
        option_lines: list[str] = []  # original lines for marker check
        prompt_line = None
        expected_num = None  # next expected number going backwards

        for line in reversed(recent_lines):
            m = _NUMBERED_OPTION_RE.match(line)
            if m:
                num = int(m.group(1))
                if expected_num is not None and num != expected_num:
                    # Sequence broken (gap, duplicate, or restart) — discard
                    # collected options and start fresh from this number.
                    options = []
                    option_lines = []
                label = m.group(2).strip()
                if m.group(3):
                    label += f" ({m.group(3).strip()})"
                options.insert(0, (num, label))
                option_lines.insert(0, line)
                expected_num = num - 1
            elif options:
                # First non-option line above the options is the prompt
                prompt_line = line.rstrip(":").strip()
                break

        if len(options) < 2 or not prompt_line:
            return None

        # Must start from 1
        if options[0][0] != 1:
            return None

        # Anti-false-positive: at least one option line must have a TUI menu
        # marker (❯ cursor or · separator) to distinguish from code line numbers
        if not any("❯" in ln or "·" in ln for ln in option_lines):
            return None

        return {
            "question_type": "select",
            "prompt": prompt_line,
            "options": [label for _, label in options],
            "_option_numbers": [num for num, _ in options],
            "is_json_tool_use": False,
        }

    @staticmethod
    def _get_repl_command(backend_type: str, action: str) -> Optional[str]:
        """Get the REPL slash-command for a given action.

        When a CLI tool lands at its interactive REPL prompt (e.g. after onboarding),
        we need to re-send the action as a slash-command. Returns the command string
        to type into the REPL, or None if not applicable.
        """
        repl_commands = {
            "claude": {"login": "/login", "usage": "/usage"},
            "codex": {"login": "/login"},
        }
        return repl_commands.get(backend_type, {}).get(action)

    @classmethod
    def submit_response(cls, session_id: str, interaction_id: str, response: dict) -> bool:
        """Submit a user response to unblock a waiting thread.

        Returns:
            True if the event was found and set, False otherwise.
        """
        with cls._lock:
            event = cls._pending_events.get(interaction_id)
            if not event:
                return False
            cls._pending_responses[interaction_id] = response

        # Set the event outside the lock (unblocks the waiting thread)
        event.set()
        return True

    @classmethod
    def subscribe(cls, session_id: str) -> Generator[str, None, None]:
        """SSE generator for real-time CLI streaming."""
        queue: Queue = Queue()

        with cls._lock:
            # Register subscriber
            if session_id not in cls._subscribers:
                cls._subscribers[session_id] = []
            cls._subscribers[session_id].append(queue)

            # If there's a current question pending, re-send it (handles reconnect)
            if session_id in cls._current_question:
                yield cls._format_sse("question", cls._current_question[session_id])

        # Check if session is already complete
        with cls._lock:
            completed = cls._completed.get(session_id)
        if completed:
            yield cls._format_sse(
                "complete",
                {
                    "status": completed["status"],
                    "exit_code": completed.get("exit_code"),
                    "error_message": completed.get("error_message"),
                    "finished_at": completed.get("finished_at"),
                },
            )
            return

        try:
            while True:
                try:
                    event = queue.get(timeout=30)  # 30 second keepalive timeout
                    if event is None:
                        break  # End of stream
                    yield event
                except Empty:
                    yield ": keepalive\n\n"
        finally:
            # Unsubscribe
            with cls._lock:
                if session_id in cls._subscribers:
                    try:
                        cls._subscribers[session_id].remove(queue)
                    except ValueError:
                        pass  # Intentionally silenced: invalid value handled gracefully

    @classmethod
    def get_status(cls, session_id: str) -> Optional[dict]:
        """Get current status of a CLI session."""
        with cls._lock:
            if session_id in cls._sessions:
                info = cls._sessions[session_id]
                result = {
                    "session_id": session_id,
                    "backend_id": info["backend_id"],
                    "backend_type": info["backend_type"],
                    "action": info["action"],
                    "status": info["status"],
                    "started_at": info["started_at"],
                }
                if session_id in cls._current_question:
                    result["current_question"] = cls._current_question[session_id]
                return result

            if session_id in cls._completed:
                return cls._completed[session_id]

        return None

    @classmethod
    def cancel_session(cls, session_id: str) -> bool:
        """Cancel a running CLI session."""
        with cls._lock:
            session = cls._sessions.get(session_id)
            if not session:
                return False
            pid = session.get("child_pid")
            master_fd = session.get("master_fd")

        # Kill the process group
        if pid:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass  # Intentionally silenced: process already terminated

        # Close the master fd to unblock the reader thread
        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass  # Intentionally silenced: cleanup/IO operation is best-effort

        cls._finish_session(session_id, "cancelled")
        return True

    @classmethod
    def run_usage_oneshot(cls, backend_type: str, timeout: int = 30) -> dict:
        """Run a one-shot usage check command synchronously.

        Returns:
            Dict with success, output, error fields.
        """
        commands = BACKEND_CLI_COMMANDS.get(backend_type)
        if not commands or "usage" not in commands:
            return {
                "success": False,
                "output": None,
                "error": f"No usage command for {backend_type}",
            }

        cmd_list = commands["usage"]
        env = {k: v for k, v in os.environ.items() if k not in _ENV_STRIP}
        try:
            result = subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            if result.returncode == 0:
                return {"success": True, "output": result.stdout.strip(), "error": None}
            else:
                return {
                    "success": False,
                    "output": result.stdout.strip() or None,
                    "error": result.stderr.strip() or f"Exit code {result.returncode}",
                }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": None,
                "error": f"Command timed out after {timeout}s",
            }
        except FileNotFoundError:
            return {"success": False, "output": None, "error": f"CLI not found: {cmd_list[0]}"}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}

    @classmethod
    def _rewrite_oauth_url(cls, session_id: str, oauth_url: str) -> str:
        """Rewrite an OAuth URL's redirect_uri to route through our proxy.

        Also extracts and stores the callback port from the original
        redirect_uri so the proxy route knows where to forward.

        Args:
            session_id: The CLI session that produced this URL.
            oauth_url: The raw OAuth URL from the CLI output.

        Returns:
            The rewritten OAuth URL (or the original if rewriting fails).
        """
        with cls._lock:
            session = cls._sessions.get(session_id)
        if not session or not session.get("host_url"):
            return oauth_url

        host_url = session["host_url"]

        try:
            parsed = urlparse(oauth_url)
            qs = parse_qs(parsed.query, keep_blank_values=True)
            redirect_uri_list = qs.get("redirect_uri")
            if not redirect_uri_list:
                return oauth_url

            original_redirect = redirect_uri_list[0]
            redirect_parsed = urlparse(original_redirect)

            # Extract and store the callback port
            callback_port = redirect_parsed.port or 54545
            with cls._lock:
                if session_id in cls._sessions:
                    cls._sessions[session_id]["callback_port"] = callback_port

            # Build the new redirect_uri through our proxy
            # Original: http://localhost:54545/callback
            # New:      {host_url}/api/oauth-callback/callback
            redirect_path = redirect_parsed.path.lstrip("/")
            new_redirect = f"{host_url}/api/oauth-callback/{redirect_path}"

            # Replace redirect_uri in the query string
            qs["redirect_uri"] = [new_redirect]

            # Rebuild the URL — urlencode with doseq=True for list values
            new_query = urlencode(qs, doseq=True)
            new_url = urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    new_query,
                    parsed.fragment,
                )
            )

            logger.info(
                "CLI %s: rewrote redirect_uri: port=%d, new=%s",
                session_id,
                callback_port,
                new_redirect,
            )
            return new_url
        except Exception as exc:
            logger.warning("CLI %s: failed to rewrite OAuth URL: %s", session_id, exc)
            return oauth_url

    @classmethod
    def _broadcast(cls, session_id: str, event_type: str, data: dict) -> None:
        """Broadcast an SSE event to all subscribers."""
        message = cls._format_sse(event_type, data)
        with cls._lock:
            if session_id in cls._subscribers:
                for q in cls._subscribers[session_id]:
                    q.put(message)

    @staticmethod
    def _format_sse(event_type: str, data: dict) -> str:
        """Format data as SSE message."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
