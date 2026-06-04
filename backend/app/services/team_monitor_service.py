"""TeamMonitorService -- filesystem watcher for Claude Code agent team directories.

ALL STATE IN THIS SERVICE IS TRANSIENT (IN-MEMORY ONLY).

This service is intentionally NOT crash-recoverable. Watchdog observers and team state
(members, tasks, config) are held in class-level dicts protected by a threading lock.
If the Flask server restarts, all active watchers are lost and team monitoring must be
re-started manually for any running team sessions.

Uses watchdog to monitor ~/.claude/teams/{team_name}/ and ~/.claude/tasks/{team_name}/
for real-time updates to team configuration and task status. A fallback polling thread
(every 5s) catches missed watchdog events on macOS where FSEvents can batch/delay under
high filesystem activity.
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class TeamFileHandler(FileSystemEventHandler):
    """Watchdog event handler for team config and task file changes.

    Parses JSON files from ~/.claude/teams/ and ~/.claude/tasks/ and broadcasts
    updates via ProjectSessionManager SSE.
    """

    def __init__(self, session_id: str, team_name: str) -> None:
        super().__init__()
        self.session_id = session_id
        self.team_name = team_name

    def on_modified(self, event) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return
        self._process_event(event.src_path)

    def on_created(self, event) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return
        self._process_event(event.src_path)

    def _process_event(self, src_path: str) -> None:
        """Process a file event, broadcasting team or task updates.

        Routes through the same mtime-gated helpers as the polling loop so the
        two never double-broadcast the same change (06 M4)."""
        try:
            if src_path.endswith("config.json") and self.team_name in src_path:
                TeamMonitorService._broadcast_config_if_newer(self.session_id, src_path)
            elif "/tasks/" in src_path and self.team_name in src_path:
                import os as _os

                TeamMonitorService._broadcast_task_if_newer(
                    self.session_id, src_path, _os.path.basename(src_path)
                )
        except Exception:
            logger.warning(
                f"Error processing team file event for {src_path}",
                exc_info=True,
            )


class TeamMonitorService:
    """Monitors Claude Code agent team directories using watchdog filesystem watchers.

    Follows the classmethod singleton pattern from ProjectSessionManager.
    All state is class-level, protected by a threading lock.
    """

    _monitors: Dict[str, dict] = {}
    _lock = threading.Lock()

    @classmethod
    def start_monitoring(cls, session_id: str, team_name: str) -> None:
        """Start monitoring a team's filesystem directories.

        Creates watchdog observers for ~/.claude/teams/{team_name}/ and
        ~/.claude/tasks/{team_name}/, plus a fallback polling thread.

        Args:
            session_id: The session that owns this team.
            team_name: The team name used for directory paths.
        """
        claude_dir = Path.home() / ".claude"
        teams_dir = claude_dir / "teams" / team_name
        tasks_dir = claude_dir / "tasks" / team_name

        # Create directories if they don't exist (team may not have been created yet)
        teams_dir.mkdir(parents=True, exist_ok=True)
        tasks_dir.mkdir(parents=True, exist_ok=True)

        handler = TeamFileHandler(session_id, team_name)

        observer = Observer()
        observer.schedule(handler, str(teams_dir), recursive=True)
        observer.schedule(handler, str(tasks_dir), recursive=True)
        observer.daemon = True
        observer.start()

        # Start fallback polling thread to catch missed watchdog events on macOS
        poll_thread = threading.Thread(
            target=cls._polling_loop,
            args=(session_id, team_name, str(teams_dir), str(tasks_dir)),
            daemon=True,
        )

        state = {
            "team_name": team_name,
            "observer": observer,
            "handler": handler,
            "members": [],
            "tasks": [],
            "active": True,
            "poll_thread": poll_thread,
            "teams_dir": str(teams_dir),
            "tasks_dir": str(tasks_dir),
            "last_config_mtime": 0.0,
            "known_task_files": {},
            # Set on stop so the poll loop wakes immediately (06 M4).
            "stop_event": threading.Event(),
        }

        with cls._lock:
            cls._monitors[session_id] = state

        poll_thread.start()

        logger.info(
            f"Started team monitor for session {session_id} "
            f"(team={team_name}, teams_dir={teams_dir}, tasks_dir={tasks_dir})"
        )

    @classmethod
    def _broadcast_config_if_newer(cls, session_id: str, config_path: str) -> None:
        """Mtime-gated config broadcast shared by the watchdog handler AND the
        polling loop, so a change is broadcast at most once no matter which one
        observes it first (06 M4 — eliminates double broadcasts)."""
        from .project_session_manager import ProjectSessionManager

        try:
            if not os.path.exists(config_path):
                return
            mtime = os.path.getmtime(config_path)
        except OSError:
            return
        with cls._lock:
            state = cls._monitors.get(session_id)
            if not state or mtime <= state.get("last_config_mtime", 0):
                return
            state["last_config_mtime"] = mtime
        team_data = cls._parse_team_config(config_path)
        if team_data is not None:
            cls._update_members(session_id, team_data)
            ProjectSessionManager._broadcast(
                session_id, "team_update", {"type": "config", "data": team_data}
            )

    @classmethod
    def _broadcast_task_if_newer(cls, session_id: str, fpath: str, fname: str) -> None:
        """Mtime-gated task broadcast shared by watchdog + polling loop (06 M4)."""
        from .project_session_manager import ProjectSessionManager

        try:
            mtime = os.path.getmtime(fpath)
        except OSError:
            return
        with cls._lock:
            state = cls._monitors.get(session_id)
            if not state:
                return
            known = state.get("known_task_files", {})
            if mtime <= known.get(fname, 0):
                return
            known[fname] = mtime
        task_data = cls._parse_task(fpath)
        if task_data is not None:
            cls._update_task(session_id, task_data)
            ProjectSessionManager._broadcast(
                session_id, "team_update", {"type": "task", "data": task_data}
            )

    @classmethod
    def _polling_loop(
        cls,
        session_id: str,
        team_name: str,
        teams_dir: str,
        tasks_dir: str,
    ) -> None:
        """Fallback polling loop to catch missed watchdog events.

        Checks team config and task files every 5 seconds. Exits when
        state["active"] is False.
        """
        with cls._lock:
            s0 = cls._monitors.get(session_id)
            stop_event = s0["stop_event"] if s0 else None
        if stop_event is None:
            return

        while True:
            # Interruptible wait so stop_monitoring takes effect immediately
            # instead of after the full 5s (06 M4).
            if stop_event.wait(5):
                return
            with cls._lock:
                state = cls._monitors.get(session_id)
                if not state or not state["active"]:
                    return

            # Both checks go through the shared mtime-gated helpers, which also
            # serve the watchdog handler — so a change is broadcast once total.
            cls._broadcast_config_if_newer(session_id, os.path.join(teams_dir, "config.json"))
            try:
                if os.path.isdir(tasks_dir):
                    for fname in os.listdir(tasks_dir):
                        fpath = os.path.join(tasks_dir, fname)
                        if os.path.isfile(fpath):
                            cls._broadcast_task_if_newer(session_id, fpath, fname)
            except OSError as exc:
                logger.debug("team_monitor poll: tasks dir scan failed: %s", exc, exc_info=True)

    @classmethod
    def stop_monitoring(cls, session_id: str) -> None:
        """Stop monitoring a team session.

        Stops the watchdog observer, marks the monitor as inactive,
        and removes the entry from _monitors to prevent memory leaks.
        """
        with cls._lock:
            state = cls._monitors.pop(session_id, None)
            if not state:
                return
            state["active"] = False
        # Wake the poll loop immediately (06 M4).
        ev = state.get("stop_event")
        if ev is not None:
            ev.set()

        # Stop observer outside lock
        observer = state.get("observer")
        if observer:
            try:
                observer.stop()
                observer.join(timeout=5)
            except Exception:
                logger.warning(
                    f"Error stopping watchdog observer for session {session_id}",
                    exc_info=True,
                )

        logger.info(f"Stopped team monitor for session {session_id}")

    @classmethod
    def get_state(cls, session_id: str) -> Optional[dict]:
        """Get the current team state for a session.

        Returns:
            Dict with team_name, members, tasks. None if not monitored.
        """
        with cls._lock:
            state = cls._monitors.get(session_id)
            if not state:
                return None
            return {
                "team_name": state["team_name"],
                "members": list(state["members"]),
                "tasks": list(state["tasks"]),
            }

    @classmethod
    def _update_members(cls, session_id: str, team_data: dict) -> None:
        """Update stored members list from parsed team config."""
        with cls._lock:
            state = cls._monitors.get(session_id)
            if state:
                state["members"] = team_data.get("members", [])

    @classmethod
    def _update_task(cls, session_id: str, task_data: dict) -> None:
        """Update or add a task in the stored tasks list."""
        with cls._lock:
            state = cls._monitors.get(session_id)
            if not state:
                return
            task_id = task_data.get("id") or task_data.get("file")
            # Update existing task or append new one
            for i, t in enumerate(state["tasks"]):
                if (t.get("id") or t.get("file")) == task_id:
                    state["tasks"][i] = task_data
                    return
            state["tasks"].append(task_data)

    @staticmethod
    def _parse_team_config(path: str) -> Optional[dict]:
        """Parse a team config.json file.

        Returns:
            Dict with members list and other config data, or None on error.
        """
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return {
                "members": data.get("members", data.get("teammates", [])),
                "name": data.get("name", ""),
                "config": data,
            }
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _parse_task(path: str) -> Optional[dict]:
        """Parse a task file (JSON).

        Returns:
            Dict with task id, status, and other fields, or None on error.
        """
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return {
                "id": data.get("id", ""),
                "status": data.get("status", "unknown"),
                "assignee": data.get("assignee", ""),
                "description": data.get("description", ""),
                "file": os.path.basename(path),
            }
        except (json.JSONDecodeError, OSError):
            return None
