"""RalphMonitorService -- git-commit-based iteration tracking and circuit breaker for Ralph loop sessions.

ALL STATE IN THIS SERVICE IS TRANSIENT (IN-MEMORY ONLY).

This service is intentionally NOT crash-recoverable. All monitor state (iteration counts,
commit hashes, circuit breaker status) is held in class-level dicts protected by a threading
lock. If the Flask server restarts, all active monitors are lost. Sessions must be re-checked
manually after a server restart.

The circuit breaker halts a Ralph session after N consecutive no-progress checks (default 3).
Progress is detected by comparing the latest git commit hash in the working directory. A
secondary signal (PTY output activity) is also considered -- if the session is still producing
output, it is assumed to be working even without new commits (e.g., during compilation).
"""

import logging
import subprocess
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class RalphMonitorService:
    """Monitors Ralph loop progress via git commit frequency with circuit breaker.

    Follows the classmethod singleton pattern from ProjectSessionManager.
    All state is class-level, protected by a threading lock.
    """

    _monitors: Dict[str, dict] = {}
    _lock = threading.Lock()

    @classmethod
    def start_monitoring(
        cls,
        session_id: str,
        cwd: str,
        max_iterations: int,
        no_progress_threshold: int = 3,
    ):
        """Start monitoring a Ralph loop session for iteration progress.

        Records the initial git commit hash and starts a daemon thread that
        polls for new commits every 30 seconds.

        Args:
            session_id: The session to monitor.
            cwd: Working directory (git repo) for commit tracking.
            max_iterations: Maximum iterations configured for the Ralph loop.
            no_progress_threshold: Consecutive no-progress checks before circuit break.
        """
        initial_hash = cls._get_latest_commit(cwd)

        state = {
            "iteration": 0,
            "max_iterations": max_iterations,
            "last_commit_hash": initial_hash,
            "no_progress_count": 0,
            "triggered": False,
            "active": True,
            "thread": None,
        }

        monitor_thread = threading.Thread(
            target=cls._monitor_loop,
            args=(session_id, cwd, max_iterations, no_progress_threshold),
            daemon=True,
        )
        state["thread"] = monitor_thread

        with cls._lock:
            cls._monitors[session_id] = state

        monitor_thread.start()
        logger.info(
            f"Started Ralph monitor for session {session_id} "
            f"(max_iterations={max_iterations}, threshold={no_progress_threshold})"
        )

    @classmethod
    def _monitor_loop(
        cls,
        session_id: str,
        cwd: str,
        max_iterations: int,
        threshold: int,
    ):
        """Poll git commits every 30s, track iterations, trigger circuit breaker.

        Runs in a daemon thread. Exits when state["active"] is set to False
        or when the circuit breaker triggers.
        """
        # Import here to avoid circular imports at module level
        from .project_session_manager import ProjectSessionManager

        while True:
            time.sleep(30)

            with cls._lock:
                state = cls._monitors.get(session_id)
                if not state or not state["active"]:
                    return

            current_hash = cls._get_latest_commit(cwd)
            session_info = ProjectSessionManager.get_session_info(session_id)

            with cls._lock:
                state = cls._monitors.get(session_id)
                if not state or not state["active"]:
                    return

                if current_hash and current_hash != state["last_commit_hash"]:
                    # Progress detected -- new commit
                    state["iteration"] += 1
                    state["last_commit_hash"] = current_hash
                    state["no_progress_count"] = 0

                    ProjectSessionManager._broadcast(
                        session_id,
                        "ralph_iteration",
                        {
                            "iteration": state["iteration"],
                            "max_iterations": max_iterations,
                        },
                    )
                    logger.debug(f"Ralph session {session_id}: iteration {state['iteration']}")
                elif session_info and session_info.get("status") == "active":
                    # No new commit -- check secondary signal (PTY output)
                    output_lines = session_info.get("output_lines", 0)
                    if output_lines > 0:
                        # Output is being produced, assume still working
                        state["no_progress_count"] = 0
                    else:
                        state["no_progress_count"] += 1
                else:
                    # Session no longer active
                    state["active"] = False
                    return

                # Check circuit breaker
                if state["no_progress_count"] >= threshold:
                    state["triggered"] = True
                    state["active"] = False

                    logger.warning(
                        f"Circuit breaker triggered for Ralph session {session_id} "
                        f"after {state['no_progress_count']} consecutive no-progress checks"
                    )

                    ProjectSessionManager._broadcast(
                        session_id,
                        "circuit_breaker",
                        {
                            "reason": "no_progress",
                            "iterations_without_progress": state["no_progress_count"],
                        },
                    )

            # Stop session outside lock to avoid deadlock
            if state.get("triggered"):
                ProjectSessionManager.stop_session(session_id)
                return

    @classmethod
    def stop_monitoring(cls, session_id: str):
        """Stop monitoring a Ralph loop session.

        Sets active=False so the monitor thread will exit on its next cycle,
        then removes the entry from _monitors to prevent memory leaks.
        """
        with cls._lock:
            state = cls._monitors.pop(session_id, None)
            if state:
                state["active"] = False
                logger.info(f"Stopped Ralph monitor for session {session_id}")

    @classmethod
    def get_state(cls, session_id: str) -> Optional[dict]:
        """Get a copy of the monitor state for a session.

        Returns:
            Dict with iteration, max_iterations, no_progress_count, triggered, active.
            None if session is not being monitored.
        """
        with cls._lock:
            state = cls._monitors.get(session_id)
            if not state:
                return None
            # Return a copy without the thread reference
            return {
                "iteration": state["iteration"],
                "max_iterations": state["max_iterations"],
                "last_commit_hash": state["last_commit_hash"],
                "no_progress_count": state["no_progress_count"],
                "triggered": state["triggered"],
                "active": state["active"],
            }

    @staticmethod
    def _get_latest_commit(cwd: str) -> str:
        """Get the latest git commit hash from the working directory.

        Returns:
            The commit hash string, or empty string on error.
        """
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%H"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            return ""
