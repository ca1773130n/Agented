"""Backend CLI service for OAuth login and usage checking via Popen + SSE streaming."""

import datetime
import json
import logging
import os
import re
import subprocess
import threading
import uuid
from queue import Empty, Queue
from typing import Dict, Generator, List, Optional

from .process_manager import ProcessManager

logger = logging.getLogger(__name__)

# Timeout for waiting on user input (5 minutes)
INPUT_TIMEOUT_SECONDS = 300

# CLI command configuration per backend type
BACKEND_CLI_COMMANDS = {
    "claude": {"login": ["claude", "/login"], "usage": ["claude", "/usage"]},
    "codex": {"login": ["codex", "login"], "usage": ["codex", "usage"]},
}

# OAuth URL detection patterns
OAUTH_URL_PATTERN = re.compile(
    r"(https?://\S+(?:auth|login|oauth|consent|accounts)\S*)", re.IGNORECASE
)


class BackendCLIService:
    """Service for running backend CLI commands with SSE streaming.

    Uses class-level state with @classmethod methods, matching the SetupExecutionService pattern.
    No DB persistence — ephemeral sessions with 5-minute TTL after completion.
    """

    # Active sessions: {session_id: {process, backend_id, backend_type, action, status, started_at}}
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

    @classmethod
    def start_session(cls, backend_id: str, backend_type: str, action: str) -> str:
        """Start a CLI session (login or usage).

        Args:
            backend_id: The backend entity ID.
            backend_type: Backend type (claude, codex).
            action: The action to perform (login, usage).

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

        # Launch subprocess
        process = subprocess.Popen(
            cmd_list,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            preexec_fn=os.setsid,
        )

        # Register with ProcessManager
        ProcessManager.register(session_id, process, trigger_id=session_id)

        started_at = datetime.datetime.now().isoformat()

        # Store in-memory state
        with cls._lock:
            cls._sessions[session_id] = {
                "process": process,
                "backend_id": backend_id,
                "backend_type": backend_type,
                "action": action,
                "status": "running",
                "started_at": started_at,
            }
            cls._subscribers[session_id] = []

        # Start streaming threads
        stdout_thread = threading.Thread(
            target=cls._stream_stdout_interactive,
            args=(session_id, process.stdout, process.stdin),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=cls._stream_stderr,
            args=(session_id, process.stderr),
            daemon=True,
        )
        wait_thread = threading.Thread(
            target=cls._wait_for_completion,
            args=(session_id, process),
            daemon=True,
        )

        stdout_thread.start()
        stderr_thread.start()
        wait_thread.start()

        # Broadcast initial status
        cls._broadcast(
            session_id,
            "status",
            {"status": "running", "started_at": started_at, "session_id": session_id},
        )

        return session_id

    @classmethod
    def _stream_stdout_interactive(cls, session_id: str, stdout, stdin):
        """Read stdout line by line, detecting interactions and OAuth URLs."""
        try:
            for line in iter(stdout.readline, ""):
                content = line.rstrip("\n")
                if not content:
                    continue

                # Check for OAuth URLs
                url_match = OAUTH_URL_PATTERN.search(content)
                if url_match:
                    cls._broadcast(
                        session_id,
                        "oauth_url",
                        {
                            "url": url_match.group(1),
                            "content": content,
                            "timestamp": datetime.datetime.now().isoformat(),
                        },
                    )

                # Try to parse as an interaction request
                interaction = cls._try_parse_interaction(content)

                if interaction:
                    interaction_id = str(uuid.uuid4())

                    # Register event BEFORE broadcasting (prevents race condition)
                    event = threading.Event()
                    with cls._lock:
                        cls._pending_events[interaction_id] = event

                    # Build question payload
                    question_data = {
                        "interaction_id": interaction_id,
                        "question_type": interaction["question_type"],
                        "prompt": interaction["prompt"],
                        "options": interaction.get("options"),
                    }

                    # Store current question for reconnect
                    with cls._lock:
                        cls._current_question[session_id] = question_data
                        if session_id in cls._sessions:
                            cls._sessions[session_id]["status"] = "waiting_input"

                    # Broadcast question to subscribers
                    cls._broadcast(session_id, "question", question_data)

                    # Block until user responds or timeout
                    responded = event.wait(timeout=INPUT_TIMEOUT_SECONDS)

                    if not responded:
                        logger.warning(
                            f"CLI {session_id}: input timeout for interaction {interaction_id}"
                        )
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
                        break

                    # Get response and clean up
                    with cls._lock:
                        response = cls._pending_responses.pop(interaction_id, {})
                        cls._pending_events.pop(interaction_id, None)
                        cls._current_question.pop(session_id, None)

                    # Write response to subprocess stdin
                    try:
                        if interaction.get("is_json_tool_use"):
                            response_json = json.dumps({"type": "tool_result", **response})
                            stdin.write(response_json + "\n")
                        else:
                            # Plain text response for regex-detected prompts
                            answer = response.get("answer", "")
                            stdin.write(str(answer) + "\n")
                        stdin.flush()
                    except (BrokenPipeError, OSError) as e:
                        logger.warning(f"CLI {session_id}: stdin write failed: {e}")
                        break

                    # Update status back to running
                    with cls._lock:
                        if session_id in cls._sessions:
                            cls._sessions[session_id]["status"] = "running"

                else:
                    # Regular log line
                    cls._broadcast(
                        session_id,
                        "log",
                        {
                            "content": content,
                            "stream": "stdout",
                            "timestamp": datetime.datetime.now().isoformat(),
                        },
                    )
        except Exception as e:
            logger.error(f"CLI {session_id}: stdout stream error: {e}")

    @classmethod
    def _stream_stderr(cls, session_id: str, stderr):
        """Read stderr line by line and broadcast as log events."""
        try:
            for line in iter(stderr.readline, ""):
                content = line.rstrip("\n")
                if not content:
                    continue

                # Check stderr for OAuth URLs too
                url_match = OAUTH_URL_PATTERN.search(content)
                if url_match:
                    cls._broadcast(
                        session_id,
                        "oauth_url",
                        {
                            "url": url_match.group(1),
                            "content": content,
                            "timestamp": datetime.datetime.now().isoformat(),
                        },
                    )

                cls._broadcast(
                    session_id,
                    "log",
                    {
                        "content": content,
                        "stream": "stderr",
                        "timestamp": datetime.datetime.now().isoformat(),
                    },
                )
        except Exception as e:
            logger.error(f"CLI {session_id}: stderr stream error: {e}")

    @classmethod
    def _wait_for_completion(cls, session_id: str, process):
        """Wait for subprocess to finish and finalize session."""
        try:
            process.wait()

            if ProcessManager.is_cancelled(session_id):
                return

            with cls._lock:
                if session_id not in cls._sessions:
                    return

            exit_code = process.returncode
            status = "completed" if exit_code == 0 else "error"
            error_message = None if exit_code == 0 else f"Process exited with code {exit_code}"
            cls._finish_session(session_id, status, exit_code, error_message)
        except Exception as e:
            logger.error(f"CLI {session_id}: wait_for_completion error: {e}")
            cls._finish_session(session_id, "error", error_message=str(e))

    @classmethod
    def _finish_session(
        cls,
        session_id: str,
        status: str,
        exit_code: int = None,
        error_message: str = None,
    ):
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

        # Cleanup process manager
        ProcessManager.cleanup(session_id)

        # Schedule cleanup of completed session after 5 minutes
        timer = threading.Timer(300, cls._cleanup_completed, args=[session_id])
        timer.daemon = True
        timer.start()
        with cls._lock:
            cls._cleanup_timers[session_id] = timer

    @classmethod
    def _cleanup_completed(cls, session_id: str):
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
            pass

        # Regex fallback: detect interactive CLI prompts (e.g., "? Enter API key:")
        match = re.match(r"^\?\s+(.+?)(?:\s*\[([^\]]+)\])?\s*$", content)
        if match:
            prompt = match.group(1).strip()
            options_str = match.group(2)
            options = [o.strip() for o in options_str.split("/")] if options_str else None
            return {
                "question_type": "select" if options else "text",
                "prompt": prompt,
                "options": options,
                "is_json_tool_use": False,
            }

        return None

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
                        pass

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
        ProcessManager.cancel(session_id)
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
        try:
            result = subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                timeout=timeout,
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
    def _broadcast(cls, session_id: str, event_type: str, data: dict):
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
