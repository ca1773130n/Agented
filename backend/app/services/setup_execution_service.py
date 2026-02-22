"""Interactive plugin setup execution service with threading.Event-based blocking and SSE streaming."""

import datetime
import json
import logging
import os
import re
import shlex
import subprocess
import threading
import uuid
from queue import Empty, Queue
from typing import Dict, Generator, List, Optional

from ..database import (
    create_setup_execution,
    get_setup_execution,
    update_setup_execution,
)
from .process_manager import ProcessManager
from .project_workspace_service import ProjectWorkspaceService

logger = logging.getLogger(__name__)

# Timeout for waiting on user input (5 minutes)
INPUT_TIMEOUT_SECONDS = 300


class SetupExecutionService:
    """Service for interactive plugin setup with threading.Event-based blocking and SSE streaming.

    Uses class-level state with @classmethod methods, matching the ExecutionLogService pattern.
    """

    # Active setup state: {execution_id: {process, project_id, status, command, started_at}}
    _executions: Dict[str, dict] = {}
    # Blocking events awaiting user response: {interaction_id: threading.Event}
    _pending_events: Dict[str, threading.Event] = {}
    # User responses keyed by interaction_id
    _pending_responses: Dict[str, dict] = {}
    # SSE subscriber queues per execution_id
    _subscribers: Dict[str, List[Queue]] = {}
    # Current pending question per execution_id (for reconnect)
    _current_question: Dict[str, dict] = {}
    # Lock for thread-safe operations
    _lock = threading.Lock()

    @classmethod
    def start_setup(cls, project_id: str, command: str, working_dir: str = None) -> str:
        """Start a setup execution subprocess.

        Args:
            project_id: The project to run setup in.
            command: The setup command to execute.
            working_dir: Optional working directory override.

        Returns:
            The execution_id for the new setup.
        """
        execution_id = f"setup-{uuid.uuid4().hex[:8]}"

        # Resolve working directory
        if not working_dir:
            working_dir = ProjectWorkspaceService.resolve_working_directory(project_id)

        # Split command into list
        cmd_list = shlex.split(command)

        # Launch subprocess
        process = subprocess.Popen(
            cmd_list,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=working_dir,
            bufsize=1,
            preexec_fn=os.setsid,
        )

        # Register with ProcessManager (trigger_id not applicable, use execution_id)
        ProcessManager.register(execution_id, process, trigger_id=execution_id)

        started_at = datetime.datetime.now().isoformat()

        # Store in-memory state
        with cls._lock:
            cls._executions[execution_id] = {
                "process": process,
                "project_id": project_id,
                "status": "running",
                "command": command,
                "started_at": started_at,
            }
            cls._subscribers[execution_id] = []

        # Create DB audit record
        create_setup_execution(execution_id, project_id, command, "running")

        # Start streaming threads (all daemon so they die with main process)
        stdout_thread = threading.Thread(
            target=cls._stream_stdout_interactive,
            args=(execution_id, process.stdout, process.stdin),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=cls._stream_stderr,
            args=(execution_id, process.stderr),
            daemon=True,
        )
        wait_thread = threading.Thread(
            target=cls._wait_for_completion,
            args=(execution_id, process),
            daemon=True,
        )

        stdout_thread.start()
        stderr_thread.start()
        wait_thread.start()

        # Broadcast initial status
        cls._broadcast(
            execution_id,
            "status",
            {"status": "running", "started_at": started_at, "execution_id": execution_id},
        )

        return execution_id

    @classmethod
    def _stream_stdout_interactive(cls, execution_id: str, stdout, stdin):
        """Read stdout line by line, detecting interaction requests."""
        try:
            for line in iter(stdout.readline, ""):
                content = line.rstrip("\n")
                if not content:
                    continue

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
                        cls._current_question[execution_id] = question_data
                        if execution_id in cls._executions:
                            cls._executions[execution_id]["status"] = "waiting_input"

                    # Broadcast question to subscribers
                    cls._broadcast(execution_id, "question", question_data)

                    # Block until user responds or timeout
                    responded = event.wait(timeout=INPUT_TIMEOUT_SECONDS)

                    if not responded:
                        # Timeout — broadcast error and break
                        logger.warning(
                            f"Setup {execution_id}: input timeout for interaction {interaction_id}"
                        )
                        cls._broadcast(
                            execution_id,
                            "error",
                            {"message": "Input timeout — no response received within 5 minutes"},
                        )
                        with cls._lock:
                            if execution_id in cls._executions:
                                cls._executions[execution_id]["status"] = "error"
                            cls._pending_events.pop(interaction_id, None)
                            cls._current_question.pop(execution_id, None)
                        break

                    # Get response and clean up
                    with cls._lock:
                        response = cls._pending_responses.pop(interaction_id, {})
                        cls._pending_events.pop(interaction_id, None)
                        cls._current_question.pop(execution_id, None)

                    # Write response to subprocess stdin
                    try:
                        response_json = json.dumps({"type": "tool_result", **response})
                        stdin.write(response_json + "\n")
                        stdin.flush()
                    except (BrokenPipeError, OSError) as e:
                        logger.warning(f"Setup {execution_id}: stdin write failed: {e}")
                        break

                    # Update status back to running
                    with cls._lock:
                        if execution_id in cls._executions:
                            cls._executions[execution_id]["status"] = "running"

                else:
                    # Regular log line
                    cls._broadcast(
                        execution_id,
                        "log",
                        {
                            "content": content,
                            "stream": "stdout",
                            "timestamp": datetime.datetime.now().isoformat(),
                        },
                    )
        except Exception as e:
            logger.error(f"Setup {execution_id}: stdout stream error: {e}")

    @classmethod
    def _stream_stderr(cls, execution_id: str, stderr):
        """Read stderr line by line and broadcast as log events."""
        try:
            for line in iter(stderr.readline, ""):
                content = line.rstrip("\n")
                if not content:
                    continue
                cls._broadcast(
                    execution_id,
                    "log",
                    {
                        "content": content,
                        "stream": "stderr",
                        "timestamp": datetime.datetime.now().isoformat(),
                    },
                )
        except Exception as e:
            logger.error(f"Setup {execution_id}: stderr stream error: {e}")

    @classmethod
    def _wait_for_completion(cls, execution_id: str, process):
        """Wait for subprocess to finish and finalize execution."""
        try:
            process.wait()

            # If already cancelled, don't overwrite with error status
            if ProcessManager.is_cancelled(execution_id):
                return

            # If already finished (e.g. by cancel_setup), skip
            with cls._lock:
                if execution_id not in cls._executions:
                    return

            exit_code = process.returncode
            status = "completed" if exit_code == 0 else "error"
            error_message = None if exit_code == 0 else f"Process exited with code {exit_code}"
            cls._finish_execution(execution_id, status, exit_code, error_message)
        except Exception as e:
            logger.error(f"Setup {execution_id}: wait_for_completion error: {e}")
            cls._finish_execution(execution_id, "error", error_message=str(e))

    @classmethod
    def _finish_execution(
        cls,
        execution_id: str,
        status: str,
        exit_code: int = None,
        error_message: str = None,
    ):
        """Finalize a setup execution: update DB, broadcast completion, cleanup."""
        finished_at = datetime.datetime.now().isoformat()

        # Update DB
        update_setup_execution(
            execution_id,
            status=status,
            exit_code=exit_code,
            error_message=error_message,
            finished_at=finished_at,
        )

        # Broadcast completion
        cls._broadcast(
            execution_id,
            "complete",
            {
                "status": status,
                "exit_code": exit_code,
                "error_message": error_message,
                "finished_at": finished_at,
            },
        )

        # Cleanup in-memory state
        with cls._lock:
            cls._executions.pop(execution_id, None)
            cls._current_question.pop(execution_id, None)
            # Signal all subscriber queues with None (end of stream)
            if execution_id in cls._subscribers:
                for q in cls._subscribers[execution_id]:
                    q.put(None)
                cls._subscribers.pop(execution_id, None)

        # Cleanup process manager
        ProcessManager.cleanup(execution_id)

    @classmethod
    def _try_parse_interaction(cls, content: str) -> Optional[dict]:
        """Try to parse a line as an interaction request.

        Returns:
            Dict with question_type, prompt, options or None if not an interaction.
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
            }

        return None

    @classmethod
    def submit_response(cls, execution_id: str, interaction_id: str, response: dict) -> bool:
        """Submit a user response to unblock a waiting thread.

        Args:
            execution_id: The setup execution ID.
            interaction_id: The interaction ID being responded to.
            response: The user's response dict.

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
    def subscribe(cls, execution_id: str) -> Generator[str, None, None]:
        """SSE generator for real-time setup streaming."""
        queue: Queue = Queue()

        with cls._lock:
            # Register subscriber
            if execution_id not in cls._subscribers:
                cls._subscribers[execution_id] = []
            cls._subscribers[execution_id].append(queue)

            # If there's a current question pending, re-send it (handles reconnect)
            if execution_id in cls._current_question:
                yield cls._format_sse("question", cls._current_question[execution_id])

        # Check if execution is already complete (from DB)
        execution = get_setup_execution(execution_id)
        if execution and execution.get("status") in ("completed", "error", "cancelled"):
            yield cls._format_sse(
                "complete",
                {
                    "status": execution["status"],
                    "exit_code": execution.get("exit_code"),
                    "error_message": execution.get("error_message"),
                    "finished_at": execution.get("finished_at"),
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
                if execution_id in cls._subscribers:
                    try:
                        cls._subscribers[execution_id].remove(queue)
                    except ValueError:
                        pass

    @classmethod
    def get_status(cls, execution_id: str) -> Optional[dict]:
        """Get current status of a setup execution.

        Returns in-memory state if active, otherwise queries DB.
        """
        with cls._lock:
            if execution_id in cls._executions:
                info = cls._executions[execution_id]
                result = {
                    "execution_id": execution_id,
                    "project_id": info["project_id"],
                    "status": info["status"],
                    "command": info["command"],
                    "started_at": info["started_at"],
                }
                if execution_id in cls._current_question:
                    result["current_question"] = cls._current_question[execution_id]
                return result

        # Fall back to DB
        execution = get_setup_execution(execution_id)
        if execution:
            return {
                "execution_id": execution["id"],
                "project_id": execution["project_id"],
                "status": execution["status"],
                "command": execution["command"],
                "started_at": execution["started_at"],
                "finished_at": execution.get("finished_at"),
                "exit_code": execution.get("exit_code"),
                "error_message": execution.get("error_message"),
            }
        return None

    @classmethod
    def cancel_setup(cls, execution_id: str) -> bool:
        """Cancel a running setup execution."""
        ProcessManager.cancel(execution_id)
        cls._finish_execution(execution_id, "cancelled")
        return True

    @classmethod
    def _broadcast(cls, execution_id: str, event_type: str, data: dict):
        """Broadcast an SSE event to all subscribers."""
        message = cls._format_sse(event_type, data)
        with cls._lock:
            if execution_id in cls._subscribers:
                for q in cls._subscribers[execution_id]:
                    q.put(message)

    @staticmethod
    def _format_sse(event_type: str, data: dict) -> str:
        """Format data as SSE message."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
