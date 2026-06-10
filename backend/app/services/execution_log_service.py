"""Execution logging service with real-time streaming via SSE."""

import datetime
import json
import logging
import threading
from dataclasses import asdict, dataclass
from queue import Empty, Full, Queue
from typing import Dict, Generator, List, Optional

from app.config import SSE_KEEPALIVE_TIMEOUT, SSE_REPLAY_LIMIT, STALE_EXECUTION_THRESHOLD

logger = logging.getLogger(__name__)

from ..database import (
    count_all_execution_logs,
    count_execution_logs_for_trigger,
    create_execution_log,
    generate_execution_id,
    get_all_execution_logs,
    get_execution_log,
    get_execution_logs_for_trigger,
    get_running_execution_for_trigger,
    update_execution_log,
)
from ..db import harness_state
from ..db.execution_logs import update_execution_status_cas


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
    # Per-subscriber SSE backpressure bound (drop-oldest past this).
    _SUBSCRIBER_QUEUE_MAXSIZE = 2000
    # Harness-1 integration (P2): persist a recoverable checkpoint of the
    # externalized log ledger every N appended lines. Throttled to bound
    # SQLite write amplification on the hot streaming path.
    _CHECKPOINT_EVERY_N_LINES = 50

    @staticmethod
    def _signal_end(q: Queue) -> None:
        """Non-blocking end-of-stream signal. The queue is bounded, so a plain
        blocking ``put(None)`` on a full queue (slow client) would hang
        finalization forever while ``_lock`` is held. Drop oldest to make room."""
        try:
            q.put_nowait(None)
        except Full:
            try:
                q.get_nowait()
                q.put_nowait(None)
            except (Empty, Full):
                pass

    # Track execution start times for cleanup: {execution_id: datetime}
    _start_times: Dict[str, datetime.datetime] = {}
    # _lock guards all access to _log_buffers, _subscribers, and _start_times.
    # Acquire before any read or write to those three dicts.
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
        execution_id: str = None,
    ) -> str:
        """Create a new execution record and return execution_id.

        ``execution_id`` lets the caller pre-allocate the id synchronously so a
        background runner is trackable/cancellable immediately (06 L1)."""
        execution_id = execution_id or generate_execution_id(trigger_id)
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
    def append_log(cls, execution_id: str, stream: str, content: str) -> None:
        """Add a log line and notify subscribers."""
        log_line = LogLine(
            timestamp=datetime.datetime.now().isoformat(), stream=stream, content=content
        )

        should_checkpoint = False
        with cls._lock:
            if execution_id in cls._log_buffers:
                cls._log_buffers[execution_id].append(log_line)
                # Persist a recoverable checkpoint on a throttled cadence so a
                # crash mid-run leaves externalized state (Harness-1 P2).
                buffered = len(cls._log_buffers[execution_id])
                if buffered % cls._CHECKPOINT_EVERY_N_LINES == 0:
                    should_checkpoint = True

        # Broadcast to SSE subscribers
        cls._broadcast(execution_id, "log", asdict(log_line))

        # Checkpoint outside the lock — record_checkpoint opens its own DB
        # connection and must not contend with the hot append path.
        if should_checkpoint:
            cls.checkpoint(execution_id)

    @classmethod
    def checkpoint(cls, execution_id: str, *, status: str = "running") -> Optional[int]:
        """Persist a recoverable snapshot of the run's externalized state (the
        buffered log ledger) WITHOUT finalizing the execution. Returns the new
        step number, or None if the execution is no longer tracked.

        Best-effort: a checkpoint failure must never disrupt streaming, so all
        errors are swallowed — the in-memory buffer remains the live source."""
        with cls._lock:
            buffer = cls._log_buffers.get(execution_id)
            if buffer is None:
                return None
            lines = [asdict(line) for line in buffer]

        stdout_lines = sum(1 for line in lines if line["stream"] == "stdout")
        ledger = {
            "lines": lines,
            "stdout_lines": stdout_lines,
            "stderr_lines": len(lines) - stdout_lines,
        }
        try:
            return harness_state.record_checkpoint(execution_id, ledger=ledger, status=status)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("harness checkpoint failed for %s: %s", execution_id, e)
            return None

    @classmethod
    def finish_execution(
        cls,
        execution_id: str,
        status: str,
        exit_code: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
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

        # Post-execution notification hook (INT-01, INT-02)
        # Deferred import to avoid circular imports. NotificationService may not
        # exist yet (plans execute in parallel), so ImportError is expected and
        # logged at DEBUG. Other exceptions are unexpected and logged at WARNING.
        try:
            from .notification_service import NotificationService

            trigger_id = execution.get("trigger_id") if execution else None
            NotificationService.on_execution_complete(
                execution_id=execution_id,
                trigger_id=trigger_id,
                status=status,
                duration_ms=duration_ms,
            )
        except ImportError:
            logger.debug("NotificationService not available, skipping post-execution hook")
        except Exception as e:
            logger.warning("Post-execution hook failed: %s", e)

        # Clean up collaborative viewers for this execution (EXE-05)
        # Lazy import to avoid circular imports.
        try:
            from .collaborative_viewer_service import CollaborativeViewerService

            CollaborativeViewerService.cleanup_stale_viewers()
        except ImportError:
            logger.debug("CollaborativeViewerService not available, skipping viewer cleanup")
        except Exception as e:
            logger.warning("Collaborative viewer cleanup failed: %s", e)

        # Cleanup buffers, subscribers, and start times
        with cls._lock:
            cls._log_buffers.pop(execution_id, None)
            cls._start_times.pop(execution_id, None)
            # Close all subscriber queues
            if execution_id in cls._subscribers:
                for q in cls._subscribers[execution_id]:
                    cls._signal_end(q)
                cls._subscribers.pop(execution_id, None)

        # Mark the externalized run-state row terminal so its status tracks the
        # execution's final outcome (Harness-1 P2). Best-effort: the row only
        # exists if the run was checkpointed, and this must never fail finish.
        try:
            harness_state.mark_run_status(execution_id, status)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("harness run-state finalize failed for %s: %s", execution_id, e)

    @classmethod
    def subscribe(cls, execution_id: str) -> Generator[str, None, None]:
        """SSE generator for real-time log streaming."""
        queue: Queue = Queue(maxsize=cls._SUBSCRIBER_QUEUE_MAXSIZE)

        with cls._lock:
            # Replay buffered logs up to SSE_REPLAY_LIMIT lines to avoid flooding the client.
            # When there are more lines than the limit, only the most recent ones are sent and
            # a synthetic notice is prepended so clients know they missed earlier output.
            if execution_id in cls._log_buffers:
                buffered = cls._log_buffers[execution_id]
                if len(buffered) > SSE_REPLAY_LIMIT:
                    skipped = len(buffered) - SSE_REPLAY_LIMIT
                    notice = cls._format_sse(
                        "log",
                        {
                            "timestamp": datetime.datetime.now().isoformat(),
                            "stream": "stdout",
                            "content": f"[{skipped} earlier log lines omitted — connect sooner or increase SSE_REPLAY_LIMIT]",
                        },
                    )
                    yield notice
                    replay_lines = buffered[-SSE_REPLAY_LIMIT:]
                else:
                    replay_lines = buffered
                for line in replay_lines:
                    yield cls._format_sse("log", asdict(line))

            # Register subscriber
            if execution_id not in cls._subscribers:
                cls._subscribers[execution_id] = []
            cls._subscribers[execution_id].append(queue)

        # Check if execution is already complete
        execution = get_execution_log(execution_id)
        if execution and execution.get("status") not in ("running", "paused", None):
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
                    event = queue.get(timeout=SSE_KEEPALIVE_TIMEOUT)
                    if event is None:
                        break  # End of stream
                    yield event
                except Empty:
                    # Send SSE comment heartbeat so proxies keep the connection open.
                    # The timestamp lets operators verify liveness in debug logs.
                    yield f": heartbeat {datetime.datetime.now().isoformat()}\n\n"
        finally:
            # Unsubscribe
            with cls._lock:
                if execution_id in cls._subscribers:
                    try:
                        cls._subscribers[execution_id].remove(queue)
                    except ValueError:
                        logger.debug(
                            "Queue not found when unsubscribing from execution %s", execution_id
                        )

    @classmethod
    def _broadcast(cls, execution_id: str, event_type: str, data: dict) -> None:
        """Broadcast an event to all subscribers."""
        message = cls._format_sse(event_type, data)
        with cls._lock:
            if execution_id in cls._subscribers:
                for q in cls._subscribers[execution_id]:
                    try:
                        q.put_nowait(message)
                    except Full:
                        # Backpressure: a slow SSE client on a --verbose run must
                        # not grow the queue unbounded (single-worker OOM). Drop
                        # oldest; the full log is persisted and replayable.
                        try:
                            q.get_nowait()
                            q.put_nowait(message)
                        except (Empty, Full):
                            logger.warning(
                                "execution log: dropping event for slow subscriber %s",
                                execution_id,
                            )

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
    def count_history(
        cls,
        trigger_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        """Count total execution logs (ignores pagination). Useful for total_count responses."""
        if trigger_id:
            return count_execution_logs_for_trigger(trigger_id, status)
        return count_all_execution_logs()

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
            # Capture buffered output before discarding so the tombstone keeps it.
            stdout_lines: List[str] = []
            stderr_lines: List[str] = []
            with cls._lock:
                for line in cls._log_buffers.get(execution_id, []):
                    if line.stream == "stdout":
                        stdout_lines.append(line.content)
                    else:
                        stderr_lines.append(line.content)
                cls._log_buffers.pop(execution_id, None)
                cls._start_times.pop(execution_id, None)
                if execution_id in cls._subscribers:
                    for q in cls._subscribers[execution_id]:
                        cls._signal_end(q)
                    cls._subscribers.pop(execution_id, None)

            # A stale buffer means finish_execution was never called (crash/hang).
            # Previously this left the DB row 'running' with NULL output forever.
            # Tombstone it as failed, preserving any buffered output. CAS so we
            # never clobber a row that completed concurrently (Harness-1 P2).
            try:
                update_execution_status_cas(
                    execution_id,
                    "failed",
                    expected_status="running",
                    finished_at=datetime.datetime.now().isoformat(),
                    error_message="Execution abandoned (stale buffer cleaned up)",
                    stdout_log="\n".join(stdout_lines) if stdout_lines else None,
                    stderr_log="\n".join(stderr_lines) if stderr_lines else None,
                )
                harness_state.mark_run_status(execution_id, "failed")
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("Stale execution tombstone failed for %s: %s", execution_id, e)
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
