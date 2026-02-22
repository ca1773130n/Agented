"""Execution logging service with real-time streaming via SSE."""

import datetime
import json
import logging
import threading
from dataclasses import asdict, dataclass
from queue import Empty, Queue
from typing import Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

# Stale execution cleanup threshold in seconds (15 minutes)
STALE_EXECUTION_THRESHOLD = 900

from ..database import (
    create_execution_log,
    generate_execution_id,
    get_all_execution_logs,
    get_execution_log,
    get_execution_logs_for_trigger,
    get_running_execution_for_trigger,
    update_execution_log,
)


@dataclass
class LogLine:
    """A single log line from execution output."""

    timestamp: str
    stream: str  # 'stdout' | 'stderr'
    content: str


class ExecutionLogService:
    """Service for execution logging with real-time SSE streaming."""

    # In-memory buffers for active executions: {execution_id: [LogLine]}
    _log_buffers: Dict[str, List[LogLine]] = {}
    # SSE subscribers: {execution_id: [Queue]}
    _subscribers: Dict[str, List[Queue]] = {}
    # Track execution start times for cleanup: {execution_id: datetime}
    _start_times: Dict[str, datetime.datetime] = {}
    # Lock for thread-safe operations
    _lock = threading.Lock()

    @classmethod
    def start_execution(
        cls,
        trigger_id: str,
        trigger_type: str,
        prompt: str,
        backend_type: str,
        command: str,
        trigger_config_snapshot: str = None,
        account_id: int = None,
    ) -> str:
        """Create a new execution record and return execution_id."""
        execution_id = generate_execution_id(trigger_id)
        started_at = datetime.datetime.now().isoformat()

        create_execution_log(
            execution_id=execution_id,
            trigger_id=trigger_id,
            trigger_type=trigger_type,
            started_at=started_at,
            prompt=prompt,
            backend_type=backend_type,
            command=command,
            trigger_config_snapshot=trigger_config_snapshot,
            account_id=account_id,
        )

        with cls._lock:
            cls._log_buffers[execution_id] = []
            cls._subscribers[execution_id] = []
            cls._start_times[execution_id] = datetime.datetime.now()

        # Notify subscribers that execution started
        cls._broadcast(
            execution_id,
            "status",
            {"status": "running", "started_at": started_at, "execution_id": execution_id},
        )

        return execution_id

    @classmethod
    def append_log(cls, execution_id: str, stream: str, content: str):
        """Add a log line and notify subscribers."""
        log_line = LogLine(
            timestamp=datetime.datetime.now().isoformat(), stream=stream, content=content
        )

        with cls._lock:
            if execution_id in cls._log_buffers:
                cls._log_buffers[execution_id].append(log_line)

        # Broadcast to SSE subscribers
        cls._broadcast(execution_id, "log", asdict(log_line))

    @classmethod
    def finish_execution(
        cls,
        execution_id: str,
        status: str,
        exit_code: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        """Finalize execution, flush logs to database, notify subscribers."""
        finished_at = datetime.datetime.now()

        # Get execution to calculate duration
        execution = get_execution_log(execution_id)
        duration_ms = None
        if execution and execution.get("started_at"):
            started = datetime.datetime.fromisoformat(execution["started_at"])
            duration_ms = int((finished_at - started).total_seconds() * 1000)

        # Get buffered logs
        stdout_lines = []
        stderr_lines = []
        with cls._lock:
            if execution_id in cls._log_buffers:
                for line in cls._log_buffers[execution_id]:
                    if line.stream == "stdout":
                        stdout_lines.append(line.content)
                    else:
                        stderr_lines.append(line.content)

        # Update database with final status and logs
        update_execution_log(
            execution_id=execution_id,
            status=status,
            finished_at=finished_at.isoformat(),
            duration_ms=duration_ms,
            exit_code=exit_code,
            error_message=error_message,
            stdout_log="\n".join(stdout_lines) if stdout_lines else None,
            stderr_log="\n".join(stderr_lines) if stderr_lines else None,
        )

        # Broadcast completion to subscribers
        cls._broadcast(
            execution_id,
            "complete",
            {
                "status": status,
                "exit_code": exit_code,
                "error_message": error_message,
                "duration_ms": duration_ms,
                "finished_at": finished_at.isoformat(),
            },
        )

        # Cleanup buffers, subscribers, and start times
        with cls._lock:
            cls._log_buffers.pop(execution_id, None)
            cls._start_times.pop(execution_id, None)
            # Close all subscriber queues
            if execution_id in cls._subscribers:
                for q in cls._subscribers[execution_id]:
                    q.put(None)  # Signal end of stream
                cls._subscribers.pop(execution_id, None)

    @classmethod
    def subscribe(cls, execution_id: str) -> Generator[str, None, None]:
        """SSE generator for real-time log streaming."""
        queue: Queue = Queue()

        with cls._lock:
            # Send existing buffered logs first
            if execution_id in cls._log_buffers:
                for line in cls._log_buffers[execution_id]:
                    yield cls._format_sse("log", asdict(line))

            # Register subscriber
            if execution_id not in cls._subscribers:
                cls._subscribers[execution_id] = []
            cls._subscribers[execution_id].append(queue)

        # Check if execution is already complete
        execution = get_execution_log(execution_id)
        if execution and execution.get("status") not in ("running", None):
            yield cls._format_sse(
                "complete",
                {
                    "status": execution["status"],
                    "exit_code": execution.get("exit_code"),
                    "error_message": execution.get("error_message"),
                    "duration_ms": execution.get("duration_ms"),
                    "finished_at": execution.get("finished_at"),
                },
            )
            return

        try:
            while True:
                try:
                    event = queue.get(timeout=30)  # 30 second timeout for keepalive
                    if event is None:
                        break  # End of stream
                    yield event
                except Empty:
                    # Send keepalive comment
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
    def _broadcast(cls, execution_id: str, event_type: str, data: dict):
        """Broadcast an event to all subscribers."""
        message = cls._format_sse(event_type, data)
        with cls._lock:
            if execution_id in cls._subscribers:
                for q in cls._subscribers[execution_id]:
                    q.put(message)

    @staticmethod
    def _format_sse(event_type: str, data: dict) -> str:
        """Format data as SSE message."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    @classmethod
    def get_history(
        cls,
        trigger_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> List[dict]:
        """Get execution history."""
        if trigger_id:
            return get_execution_logs_for_trigger(trigger_id, limit, offset, status)
        return get_all_execution_logs(limit, offset)

    @classmethod
    def get_execution(cls, execution_id: str) -> Optional[dict]:
        """Get a single execution by ID."""
        return get_execution_log(execution_id)

    @classmethod
    def get_running_for_trigger(cls, trigger_id: str) -> Optional[dict]:
        """Get currently running execution for a trigger."""
        return get_running_execution_for_trigger(trigger_id)

    @classmethod
    def is_running(cls, execution_id: str) -> bool:
        """Check if an execution is still running."""
        with cls._lock:
            return execution_id in cls._log_buffers

    @classmethod
    def get_stdout_log(cls, execution_id: str) -> str:
        """Get the stdout log for an execution (from buffer or database)."""
        # Check in-memory buffer first
        with cls._lock:
            if execution_id in cls._log_buffers:
                lines = [
                    line.content
                    for line in cls._log_buffers[execution_id]
                    if line.stream == "stdout"
                ]
                return "\n".join(lines)

        # Fall back to database
        execution = get_execution_log(execution_id)
        if execution:
            return execution.get("stdout_log") or ""
        return ""

    @classmethod
    def cleanup_stale_executions(cls) -> int:
        """Clean up stale execution buffers that have been running too long.

        This handles cases where finish_execution was never called (e.g., process crash).
        Returns the number of stale executions cleaned up.
        """
        now = datetime.datetime.now()
        stale_ids = []

        with cls._lock:
            for execution_id, start_time in list(cls._start_times.items()):
                elapsed = (now - start_time).total_seconds()
                if elapsed > STALE_EXECUTION_THRESHOLD:
                    stale_ids.append(execution_id)

        cleaned = 0
        for execution_id in stale_ids:
            logger.warning(f"Cleaning up stale execution buffer: {execution_id}")
            with cls._lock:
                cls._log_buffers.pop(execution_id, None)
                cls._start_times.pop(execution_id, None)
                if execution_id in cls._subscribers:
                    for q in cls._subscribers[execution_id]:
                        q.put(None)  # Signal end of stream
                    cls._subscribers.pop(execution_id, None)
            cleaned += 1

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} stale execution buffer(s)")
        return cleaned

    @classmethod
    def get_buffer_stats(cls) -> dict:
        """Get statistics about in-memory buffers for monitoring."""
        with cls._lock:
            return {
                "active_executions": len(cls._log_buffers),
                "total_subscribers": sum(len(subs) for subs in cls._subscribers.values()),
                "execution_ids": list(cls._log_buffers.keys()),
            }
