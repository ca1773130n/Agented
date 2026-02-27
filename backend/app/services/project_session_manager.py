"""ProjectSessionManager -- persistent PTY sessions with ring-buffer output and SSE broadcasting.

Manages long-lived PTY sessions for project plan execution. Each session runs a CLI command
(e.g., `claude -p ...`) in an isolated pseudo-terminal, captures output in a fixed-size ring
buffer, and broadcasts lines in real-time via SSE to connected clients.

Key features:
- PTY-based sessions via pty.openpty()/os.fork()/os.setsid()
- Ring buffer: collections.deque(maxlen=10000) per session
- SSE broadcasting: Queue-per-subscriber, same pattern as ExecutionLogService
- Pause/resume: suppresses broadcast but process keeps running and output keeps buffering
- Resource limits: 1-hour idle timeout, 4-hour max lifetime
- Crash recovery: PID/PGID persisted to DB, dead sessions cleaned on startup
"""

import json
import logging
import os
import pty
import re
import select
import signal
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from queue import Empty, Queue
from typing import Dict, Generator, List, Optional

from ..db import (
    _get_unique_project_session_id,
    get_active_sessions,
    get_connection,
    update_project_session,
)

logger = logging.getLogger(__name__)

# Compiled regex to strip ANSI escape codes from PTY output.
# Handles CSI sequences (\x1b[...X), OSC sequences (\x1b]...BEL), and other common escapes.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b\[.*?[@-~]")


@dataclass
class SessionInfo:
    """In-memory state for an active PTY session."""

    session_id: str
    pid: int
    pgid: int
    master_fd: int
    ring_buffer: deque  # deque(maxlen=10000)
    reader_thread: threading.Thread
    status: str  # active, paused, completed, failed
    created_at: datetime
    last_activity_at: datetime
    worktree_path: Optional[str] = None
    execution_type: str = "direct"
    execution_mode: str = "autonomous"
    idle_timeout_seconds: int = 3600
    max_lifetime_seconds: int = 14400
    paused: bool = False  # When True, output buffers but SSE broadcast is suppressed


class ProjectSessionManager:
    """Service for managing persistent PTY sessions with SSE output streaming.

    Follows the classmethod singleton pattern from ExecutionLogService.
    All state is class-level, protected by a threading lock.
    """

    # In-memory session tracking: {session_id: SessionInfo}
    _sessions: Dict[str, SessionInfo] = {}
    # SSE subscribers: {session_id: [Queue]}
    _subscribers: Dict[str, List[Queue]] = {}
    _lock = threading.Lock()

    @classmethod
    def create_session(
        cls,
        project_id: str,
        cmd: list,
        cwd: str,
        phase_id: str = None,
        plan_id: str = None,
        agent_id: str = None,
        worktree_path: str = None,
        execution_type: str = "direct",
        execution_mode: str = "autonomous",
        env: dict = None,
    ) -> str:
        """Create a persistent PTY session.

        Forks a child process in a new PTY, starts a reader thread for output capture,
        and persists session metadata to the database.

        Args:
            project_id: Project this session belongs to.
            cmd: Command and arguments to execute, e.g. ["claude", "-p", "..."].
            cwd: Working directory for the command.
            phase_id: Optional phase context.
            plan_id: Optional plan context.
            agent_id: Optional agent context.
            worktree_path: Optional isolated worktree path.
            execution_type: "direct", "ralph_loop", or "team_spawn".
            execution_mode: "autonomous" or "interactive".
            env: Optional dict of environment variables to set in the child process.
                 Applied after fork, before exec. None means no changes.

        Returns:
            session_id (str): The unique session identifier (psess-XXXXXX).
        """
        # Generate session_id from DB to ensure uniqueness
        with get_connection() as conn:
            session_id = _get_unique_project_session_id(conn)

        # Create PTY pair
        master_fd, slave_fd = pty.openpty()
        pid = os.fork()

        if pid == 0:
            # --- Child process ---
            os.close(master_fd)
            os.setsid()  # New session leader (detach from parent's process group)
            os.dup2(slave_fd, 0)  # stdin
            os.dup2(slave_fd, 1)  # stdout
            os.dup2(slave_fd, 2)  # stderr
            if slave_fd > 2:
                os.close(slave_fd)
            # Apply optional environment variables before exec
            if env:
                for k, v in env.items():
                    os.environ[k] = v
            try:
                os.chdir(cwd)
            except OSError:
                os._exit(1)
            try:
                os.execvp(cmd[0], cmd)
            except OSError:
                os._exit(1)
            os._exit(1)

        # --- Parent process ---
        os.close(slave_fd)

        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            pgid = pid  # Fallback if process already exited

        now = datetime.now()
        ring_buffer = deque(maxlen=10000)

        # Start reader thread
        reader_thread = threading.Thread(
            target=cls._reader_loop,
            args=(session_id, master_fd),
            daemon=True,
        )

        session_info = SessionInfo(
            session_id=session_id,
            pid=pid,
            pgid=pgid,
            master_fd=master_fd,
            ring_buffer=ring_buffer,
            reader_thread=reader_thread,
            status="active",
            created_at=now,
            last_activity_at=now,
            worktree_path=worktree_path,
            execution_type=execution_type,
            execution_mode=execution_mode,
        )

        with cls._lock:
            cls._sessions[session_id] = session_info

        reader_thread.start()

        # Persist to database for crash recovery.
        # We insert directly with our pre-generated session_id rather than calling
        # add_project_session() (which generates its own ID internally).
        with get_connection() as conn:
            columns = ["id", "project_id", "phase_id", "plan_id", "agent_id"]
            values = [session_id, project_id, phase_id, plan_id, agent_id]
            optional_fields = {
                "pid": pid,
                "pgid": pgid,
                "worktree_path": worktree_path,
                "execution_type": execution_type,
                "execution_mode": execution_mode,
                "last_activity_at": now.isoformat(),
            }
            for col, val in optional_fields.items():
                if val is not None:
                    columns.append(col)
                    values.append(val)
            placeholders = ", ".join(["?"] * len(columns))
            col_str = ", ".join(columns)
            try:
                conn.execute(
                    f"INSERT INTO project_sessions ({col_str}) VALUES ({placeholders})",
                    values,
                )
                conn.commit()
            except Exception:
                logger.warning(
                    f"Failed to persist session {session_id} to DB",
                    exc_info=True,
                )

        logger.info(
            f"Created PTY session {session_id} (pid={pid}, pgid={pgid}, "
            f"type={execution_type}, mode={execution_mode})"
        )
        return session_id

    @classmethod
    def _reader_loop(cls, session_id: str, master_fd: int):
        """Read PTY output line by line, append to ring buffer, broadcast via SSE.

        Runs in a dedicated daemon thread. Uses select() with 1s timeout for
        non-blocking reads. Handles partial lines via byte buffer accumulation.
        """
        buffer = b""
        try:
            while True:
                with cls._lock:
                    session_info = cls._sessions.get(session_id)
                if not session_info:
                    break

                try:
                    ready, _, _ = select.select([master_fd], [], [], 1.0)
                except (ValueError, OSError):
                    break  # fd closed or invalid

                if not ready:
                    continue

                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    break  # PTY closed

                if not data:
                    break  # EOF

                buffer += data

                # Process complete lines
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    decoded = line.decode("utf-8", errors="replace")
                    decoded = _ANSI_RE.sub("", decoded)

                    with cls._lock:
                        session_info = cls._sessions.get(session_id)
                        if session_info:
                            session_info.ring_buffer.append(decoded)
                            session_info.last_activity_at = datetime.now()
                            is_paused = session_info.paused
                        else:
                            break

                    if not is_paused:
                        cls._broadcast(
                            session_id,
                            "output",
                            {
                                "line": decoded,
                                "timestamp": datetime.now().isoformat(),
                            },
                        )

                # Handle any remaining partial data (no newline) -- keep in buffer
                # Also process lines that don't end with newline (e.g., prompts)
                # We only buffer; the next read will complete the line.

        finally:
            # Close master fd
            try:
                os.close(master_fd)
            except OSError:
                pass

            # Flush remaining buffer content
            if buffer:
                decoded = buffer.decode("utf-8", errors="replace")
                decoded = _ANSI_RE.sub("", decoded)
                with cls._lock:
                    session_info = cls._sessions.get(session_id)
                    if session_info:
                        session_info.ring_buffer.append(decoded)

            cls._handle_session_exit(session_id)

    @classmethod
    def _handle_session_exit(cls, session_id: str):
        """Handle session process exit: determine status, update DB, notify subscribers."""
        with cls._lock:
            session_info = cls._sessions.get(session_id)
        if not session_info:
            return

        # Check exit status
        exit_code = None
        status = "completed"
        try:
            _, wait_status = os.waitpid(session_info.pid, os.WNOHANG)
            if os.WIFEXITED(wait_status):
                exit_code = os.WEXITSTATUS(wait_status)
                status = "completed" if exit_code == 0 else "failed"
            elif os.WIFSIGNALED(wait_status):
                exit_code = -os.WTERMSIG(wait_status)
                status = "failed"
        except ChildProcessError:
            # Process already reaped
            status = "completed"
        except OSError:
            status = "failed"

        # Update DB
        update_project_session(
            session_id,
            status=status,
            ended_at=datetime.now().isoformat(),
        )

        # Update in-memory state
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if session_info:
                session_info.status = status

        # Sync GRD .planning/ files to DB on session completion (only for GRD-initialized projects)
        try:
            from .grd_planning_service import GrdPlanningService
            from .grd_sync_service import GrdSyncService

            # Look up project_id from the DB session record
            project_id = None
            try:
                with get_connection() as conn:
                    row = conn.execute(
                        "SELECT project_id FROM project_sessions WHERE id = ?",
                        (session_id,),
                    ).fetchone()
                    if row:
                        project_id = row["project_id"]
            except Exception:
                pass

            if project_id:
                # Unregister from planning session tracker (no-op if not a planning session)
                GrdPlanningService.unregister_session(session_id)
                # Only sync if this project has GRD initialized
                from ..database import get_project

                project = get_project(project_id)
                if project and project.get("grd_init_status") in ("initializing", "ready"):
                    GrdSyncService.sync_on_session_complete(project_id, session_id)
        except Exception as e:
            logger.warning("GRD sync on session complete failed: %s", e)

        # Broadcast completion
        cls._broadcast(
            session_id,
            "complete",
            {"status": status, "exit_code": exit_code},
        )

        # Signal end to all subscribers
        with cls._lock:
            if session_id in cls._subscribers:
                for q in cls._subscribers[session_id]:
                    q.put(None)  # Signal end of stream
                del cls._subscribers[session_id]

        logger.info(f"Session {session_id} exited (status={status}, exit_code={exit_code})")

    @classmethod
    def stop_session(cls, session_id: str) -> bool:
        """Stop a running session by terminating its process group.

        Sends SIGTERM first, waits up to 5 seconds, then SIGKILL if still alive.

        Returns:
            True if session was stopped successfully, False if session not found.
        """
        with cls._lock:
            session_info = cls._sessions.get(session_id)
        if not session_info:
            return False

        pid = session_info.pid
        pgid = session_info.pgid

        # Try graceful termination first
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass  # Already dead
        except OSError as e:
            logger.warning(f"SIGTERM to pgid {pgid} failed: {e}")

        # Wait up to 5 seconds for process to exit
        for _ in range(50):  # 50 * 0.1s = 5s
            try:
                result = os.waitpid(pid, os.WNOHANG)
                if result[0] != 0:
                    # Process has exited
                    break
            except ChildProcessError:
                break  # Already reaped
            except OSError:
                break
            time.sleep(0.1)
        else:
            # Still alive after 5s -- force kill
            try:
                os.killpg(pgid, signal.SIGKILL)
                logger.warning(f"Sent SIGKILL to session {session_id} pgid {pgid}")
            except ProcessLookupError:
                pass
            except OSError as e:
                logger.error(f"SIGKILL to pgid {pgid} failed: {e}")

        # Update DB
        status = "completed"
        update_project_session(
            session_id,
            status=status,
            ended_at=datetime.now().isoformat(),
        )

        # Update in-memory
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if session_info:
                session_info.status = status

        logger.info(f"Stopped session {session_id}")
        return True

    @classmethod
    def pause_session(cls, session_id: str) -> bool:
        """Pause a session's SSE broadcasting.

        The process keeps running and output keeps buffering in the ring buffer,
        but SSE broadcast is suppressed until resume_session() is called.

        Returns:
            True if session was paused, False if session not found.
        """
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if not session_info:
                return False
            session_info.paused = True
            session_info.status = "paused"

        update_project_session(session_id, status="paused")
        logger.info(f"Paused session {session_id}")
        return True

    @classmethod
    def resume_session(cls, session_id: str) -> bool:
        """Resume a paused session's SSE broadcasting.

        Re-enables the broadcast flag so NEW output lines are broadcast.
        Does NOT replay buffered output to avoid double-delivery.
        Callers should use get_output() to fetch historical lines from the ring buffer.

        Returns:
            True if session was resumed, False if session not found.
        """
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if not session_info:
                return False
            session_info.paused = False
            session_info.status = "active"

        update_project_session(session_id, status="active")
        logger.info(f"Resumed session {session_id}")
        return True

    @classmethod
    def get_output(cls, session_id: str, last_n: int = 100) -> list:
        """Get the last N lines from the session's ring buffer.

        Args:
            session_id: Session to get output from.
            last_n: Number of recent lines to return (default 100).

        Returns:
            List of output line strings.
        """
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if not session_info:
                return []
            return list(session_info.ring_buffer)[-last_n:]

    @classmethod
    def send_input(cls, session_id: str, text: str) -> bool:
        """Send input text to a session's PTY stdin.

        Writes text (with trailing newline) to the PTY master file descriptor.
        Uses lock only for session lookup and activity update, not during the
        blocking os.write() call.

        Args:
            session_id: Target session.
            text: Text to send (a newline is appended automatically).

        Returns:
            True if the write succeeded, False if session not found/inactive or write failed.
        """
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if not session_info or session_info.status != "active":
                return False
            master_fd = session_info.master_fd

        # Write outside lock to avoid blocking other threads during I/O
        try:
            os.write(master_fd, (text + "\n").encode("utf-8"))
        except OSError:
            return False

        # Update activity timestamp
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if session_info:
                session_info.last_activity_at = datetime.now()

        return True

    @classmethod
    def subscribe(cls, session_id: str) -> Generator[str, None, None]:
        """SSE generator for real-time session output streaming.

        Ordering to avoid TOCTOU gap:
        1. Register Queue in _subscribers FIRST (under lock) -- ensures no lines lost
        2. Yield existing ring buffer contents as "output" events (catchup)
        3. Check if session already completed (yield "complete" and return)
        4. Loop: queue.get(timeout=30), yield events, keepalive on timeout

        Yields:
            SSE-formatted event strings.
        """
        queue: Queue = Queue()

        with cls._lock:
            # Step 1: Register subscriber FIRST to avoid missing lines
            if session_id not in cls._subscribers:
                cls._subscribers[session_id] = []
            cls._subscribers[session_id].append(queue)

            # Step 2: Yield existing ring buffer contents (catchup)
            session_info = cls._sessions.get(session_id)
            if session_info:
                for line in session_info.ring_buffer:
                    yield cls._format_sse(
                        "output",
                        {"line": line, "timestamp": datetime.now().isoformat()},
                    )
                current_status = session_info.status
            else:
                current_status = None

        # Step 3: Check if session already completed
        if current_status in ("completed", "failed"):
            yield cls._format_sse(
                "complete",
                {"status": current_status, "exit_code": None},
            )
            # Unsubscribe
            with cls._lock:
                if session_id in cls._subscribers:
                    try:
                        cls._subscribers[session_id].remove(queue)
                    except ValueError:
                        pass
            return

        if current_status is None:
            # Session not found in memory
            yield cls._format_sse(
                "error",
                {"message": "Session not found"},
            )
            with cls._lock:
                if session_id in cls._subscribers:
                    try:
                        cls._subscribers[session_id].remove(queue)
                    except ValueError:
                        pass
            return

        # Step 4: Stream live events
        try:
            while True:
                try:
                    event = queue.get(timeout=30)
                    if event is None:
                        break  # End of stream
                    yield event
                except Empty:
                    # Send keepalive comment
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
    def _broadcast(cls, session_id: str, event_type: str, data: dict):
        """Broadcast an SSE event to all subscribers for a session.

        Args:
            session_id: Target session.
            event_type: SSE event type (e.g., "output", "complete").
            data: Event payload dict (will be JSON-serialized).
        """
        message = cls._format_sse(event_type, data)
        with cls._lock:
            if session_id in cls._subscribers:
                for q in cls._subscribers[session_id]:
                    q.put(message)

    @staticmethod
    def _format_sse(event_type: str, data: dict) -> str:
        """Format data as an SSE message string."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    @classmethod
    def get_session_info(cls, session_id: str) -> Optional[dict]:
        """Get summary info for a session from in-memory state.

        Returns:
            Dict with status, pid, output_lines, created_at, last_activity_at.
            None if session not found.
        """
        with cls._lock:
            session_info = cls._sessions.get(session_id)
            if not session_info:
                return None
            return {
                "session_id": session_info.session_id,
                "status": session_info.status,
                "pid": session_info.pid,
                "pgid": session_info.pgid,
                "output_lines": len(session_info.ring_buffer),
                "created_at": session_info.created_at.isoformat(),
                "last_activity_at": session_info.last_activity_at.isoformat(),
                "worktree_path": session_info.worktree_path,
                "execution_type": session_info.execution_type,
                "execution_mode": session_info.execution_mode,
                "paused": session_info.paused,
            }

    @classmethod
    def cleanup_dead_sessions(cls):
        """Clean up sessions whose processes are no longer alive.

        Called on startup to handle sessions that were active when the server
        previously crashed or restarted. Queries the DB for active sessions
        and checks if their PIDs are still alive.
        """
        try:
            active_sessions = get_active_sessions()
        except Exception:
            logger.warning("Failed to query active sessions for cleanup", exc_info=True)
            return

        cleaned = 0
        for session_row in active_sessions:
            pid = session_row.get("pid")
            session_id = session_row.get("id")
            if not pid or not session_id:
                continue

            # Check if process is alive
            try:
                os.kill(pid, 0)  # Signal 0 = check existence only
            except ProcessLookupError:
                # Process is dead -- mark as failed
                update_project_session(
                    session_id,
                    status="failed",
                    ended_at=datetime.now().isoformat(),
                )
                cleaned += 1
                logger.info(f"Cleaned dead session {session_id} (pid={pid})")
            except PermissionError:
                # Process exists but we can't signal it -- leave it alone
                pass

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} dead session(s) on startup")
        else:
            logger.debug("No dead sessions found during startup cleanup")

    @classmethod
    def check_resource_limits(cls):
        """Check all active sessions for resource limit violations.

        Enforces two limits:
        - Idle timeout: session with no output for idle_timeout_seconds (default 1 hour)
        - Max lifetime: session running longer than max_lifetime_seconds (default 4 hours)

        Sessions exceeding either limit are stopped.
        """
        now = datetime.now()
        sessions_to_stop = []

        with cls._lock:
            for session_id, session_info in cls._sessions.items():
                if session_info.status not in ("active", "paused"):
                    continue

                # Check idle timeout
                idle_seconds = (now - session_info.last_activity_at).total_seconds()
                if idle_seconds > session_info.idle_timeout_seconds:
                    sessions_to_stop.append(
                        (
                            session_id,
                            f"idle timeout ({idle_seconds:.0f}s > {session_info.idle_timeout_seconds}s)",
                        )
                    )
                    continue

                # Check max lifetime
                lifetime_seconds = (now - session_info.created_at).total_seconds()
                if lifetime_seconds > session_info.max_lifetime_seconds:
                    sessions_to_stop.append(
                        (
                            session_id,
                            f"max lifetime ({lifetime_seconds:.0f}s > {session_info.max_lifetime_seconds}s)",
                        )
                    )

        for session_id, reason in sessions_to_stop:
            logger.warning(f"Stopping session {session_id}: {reason}")
            cls.stop_session(session_id)
