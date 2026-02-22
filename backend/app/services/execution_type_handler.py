"""ExecutionTypeHandler ABC and handler registry for extensible execution modes.

Defines the abstract interface for execution type handlers and provides concrete
implementations: DirectExecutionHandler, RalphSessionHandler, and TeamSpawnHandler.

The handler registry maps execution_type strings ("direct", "ralph_loop", "team_spawn")
to handler instances.

The registry is intentionally static (not DB-driven). The execution_type_handlers
DB table from Phase 42 stores configuration metadata only.
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from .project_session_manager import ProjectSessionManager
from .ralph_monitor_service import RalphMonitorService
from .team_monitor_service import TeamMonitorService

logger = logging.getLogger(__name__)


class ExecutionTypeHandler(ABC):
    """Interface for execution type handlers.

    Each execution type (direct, ralph_loop, team_spawn) has a handler
    that manages the session lifecycle for that type.
    """

    @abstractmethod
    def start(self, session_config: dict) -> dict:
        """Start execution.

        Args:
            session_config: Dict with keys:
                - project_id: str
                - cmd: list[str] -- command to execute
                - cwd: str -- working directory
                - phase_id: Optional[str]
                - plan_id: Optional[str]
                - agent_id: Optional[str]
                - worktree_path: Optional[str]
                - execution_mode: str -- "autonomous" or "interactive"

        Returns:
            {"session_id": str, "pid": int, "status": str}
        """
        ...

    @abstractmethod
    def monitor(self, session_id: str) -> dict:
        """Check execution status.

        Returns:
            {"alive": bool, "status": str, "output_lines": int, "last_activity_at": str}
        """
        ...

    @abstractmethod
    def stop(self, session_id: str) -> bool:
        """Stop execution. Returns True on success."""
        ...

    @abstractmethod
    def get_output(self, session_id: str, last_n: int = 100) -> list[str]:
        """Get last N lines from output buffer."""
        ...


class DirectExecutionHandler(ExecutionTypeHandler):
    """Handler for direct CLI session execution (single PTY session).

    Delegates all operations to ProjectSessionManager for full PTY lifecycle
    management including ring buffer output and SSE broadcasting.
    """

    def start(self, session_config: dict) -> dict:
        """Start a direct PTY session.

        Creates a new PTY session via ProjectSessionManager and returns
        the session ID, PID, and initial status.
        """
        session_id = ProjectSessionManager.create_session(
            project_id=session_config["project_id"],
            cmd=session_config["cmd"],
            cwd=session_config["cwd"],
            phase_id=session_config.get("phase_id"),
            plan_id=session_config.get("plan_id"),
            agent_id=session_config.get("agent_id"),
            worktree_path=session_config.get("worktree_path"),
            execution_type="direct",
            execution_mode=session_config.get("execution_mode", "autonomous"),
        )
        info = ProjectSessionManager.get_session_info(session_id)
        return {
            "session_id": session_id,
            "pid": info["pid"] if info else None,
            "status": "active",
        }

    def monitor(self, session_id: str) -> dict:
        """Check the status of a direct PTY session.

        Returns session liveness, status, output line count, and last activity.
        """
        info = ProjectSessionManager.get_session_info(session_id)
        if not info:
            return {
                "alive": False,
                "status": "unknown",
                "output_lines": 0,
                "last_activity_at": None,
            }
        return {
            "alive": info["status"] == "active",
            "status": info["status"],
            "output_lines": info.get("output_lines", 0),
            "last_activity_at": info.get("last_activity_at"),
        }

    def stop(self, session_id: str) -> bool:
        """Stop a direct PTY session.

        Delegates to ProjectSessionManager which handles SIGTERM/SIGKILL.
        """
        return ProjectSessionManager.stop_session(session_id)

    def get_output(self, session_id: str, last_n: int = 100) -> list[str]:
        """Get recent output lines from the session's ring buffer."""
        return ProjectSessionManager.get_output(session_id, last_n=last_n)


class RalphSessionHandler(ExecutionTypeHandler):
    """Handler for Ralph Wiggum autonomous loop execution.

    Wraps ProjectSessionManager with Ralph-specific command construction
    (injecting /ralph-loop into the Claude Code prompt) and delegates
    iteration tracking and circuit breaking to RalphMonitorService.

    Before starting a session, checks that the ralph-wiggum plugin is
    installed in the user's Claude Code settings.
    """

    @staticmethod
    def _check_ralph_plugin() -> Optional[dict]:
        """Check if ralph-wiggum plugin is installed in Claude Code settings.

        Returns:
            None if plugin is installed, or an error dict if not.
        """
        settings_path = Path.home() / ".claude" / "settings.json"
        try:
            if not settings_path.exists():
                return {
                    "error": "ralph-wiggum plugin not installed",
                    "hint": ("Run: claude plugin install ralph-wiggum@official --scope user"),
                }
            with open(settings_path, "r") as f:
                settings = json.load(f)
            enabled = settings.get("enabledPlugins", [])
            # Check for ralph-wiggum in any form (full path or short name)
            for plugin in enabled:
                if "ralph-wiggum" in str(plugin).lower():
                    return None
            return {
                "error": "ralph-wiggum plugin not installed",
                "hint": ("Run: claude plugin install ralph-wiggum@official --scope user"),
            }
        except (json.JSONDecodeError, OSError):
            return {
                "error": "ralph-wiggum plugin not installed",
                "hint": ("Run: claude plugin install ralph-wiggum@official --scope user"),
            }

    def start(self, session_config: dict) -> dict:
        """Start a Ralph loop PTY session.

        Checks for ralph-wiggum plugin, constructs /ralph-loop CLI command,
        creates session via ProjectSessionManager, and starts RalphMonitorService.
        """
        # Prerequisite check: ralph-wiggum plugin must be installed
        plugin_error = self._check_ralph_plugin()
        if plugin_error:
            return plugin_error

        ralph_config = session_config.get("ralph_config", {})
        max_iterations = ralph_config.get("max_iterations", 50)
        completion_promise = ralph_config.get("completion_promise", "COMPLETE")
        task_description = ralph_config.get("task_description", "Complete the task.")
        no_progress_threshold = ralph_config.get("no_progress_threshold", 3)

        # Construct the prompt that invokes /ralph-loop inside Claude Code
        prompt = (
            f'/ralph-loop "{task_description}" '
            f"--max-iterations {max_iterations} "
            f'--completion-promise "{completion_promise}"'
        )

        cmd = ["claude", "-p", prompt, "--dangerously-skip-permissions"]

        session_id = ProjectSessionManager.create_session(
            project_id=session_config["project_id"],
            cmd=cmd,
            cwd=session_config["cwd"],
            phase_id=session_config.get("phase_id"),
            plan_id=session_config.get("plan_id"),
            agent_id=session_config.get("agent_id"),
            worktree_path=session_config.get("worktree_path"),
            execution_type="ralph_loop",
            execution_mode="autonomous",
        )

        # Start iteration monitor (git commit tracking + circuit breaker)
        RalphMonitorService.start_monitoring(
            session_id=session_id,
            cwd=session_config["cwd"],
            max_iterations=max_iterations,
            no_progress_threshold=no_progress_threshold,
        )

        info = ProjectSessionManager.get_session_info(session_id)
        return {
            "session_id": session_id,
            "pid": info["pid"] if info else None,
            "status": "active",
        }

    def monitor(self, session_id: str) -> dict:
        """Check Ralph session status including iteration tracking.

        Merges base session info with RalphMonitorService state.
        """
        info = ProjectSessionManager.get_session_info(session_id)
        if not info:
            base = {
                "alive": False,
                "status": "unknown",
                "output_lines": 0,
                "last_activity_at": None,
            }
        else:
            base = {
                "alive": info["status"] == "active",
                "status": info["status"],
                "output_lines": info.get("output_lines", 0),
                "last_activity_at": info.get("last_activity_at"),
            }

        ralph_state = RalphMonitorService.get_state(session_id)
        if ralph_state:
            base["iteration"] = ralph_state.get("iteration", 0)
            base["max_iterations"] = ralph_state.get("max_iterations", 0)
            base["circuit_breaker_triggered"] = ralph_state.get("triggered", False)

        return base

    def stop(self, session_id: str) -> bool:
        """Stop Ralph session and its monitor."""
        RalphMonitorService.stop_monitoring(session_id)
        return ProjectSessionManager.stop_session(session_id)

    def get_output(self, session_id: str, last_n: int = 100) -> list[str]:
        """Get recent output lines from the session's ring buffer."""
        return ProjectSessionManager.get_output(session_id, last_n=last_n)


class TeamSpawnHandler(ExecutionTypeHandler):
    """Handler for Claude Code agent team execution.

    Creates a Claude Code session with CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
    enabled, injects a team creation prompt, and monitors team progress via
    TeamMonitorService filesystem watchers.

    Before starting, checks that the agent teams feature flag is available.
    """

    @staticmethod
    def _check_agent_teams_availability() -> Optional[dict]:
        """Check if agent teams feature is likely available.

        Returns:
            None if feature appears available, or an error dict if not.
        """
        # Check if the env var is already set
        if os.environ.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS") == "1":
            return None

        # Verify Claude Code is installed and settings.json exists
        settings_path = Path.home() / ".claude" / "settings.json"
        try:
            if settings_path.exists():
                with open(settings_path, "r") as f:
                    json.load(f)
                # Settings readable — Claude Code is installed, env var will be set in child
                return None
        except (json.JSONDecodeError, OSError):
            pass

        # Claude Code settings not found — feature unavailable
        return {
            "error": "Agent teams feature unavailable",
            "hint": (
                "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 is required. "
                "Ensure you are using Claude Code v1.0.20+ which supports "
                "experimental agent teams, and that ~/.claude/settings.json exists."
            ),
        }

    def start(self, session_config: dict) -> dict:
        """Start a team spawn PTY session.

        Checks agent teams availability, constructs team creation prompt,
        creates session with AGENT_TEAMS env var, and starts TeamMonitorService.
        """
        # Feature flag check
        availability_error = self._check_agent_teams_availability()
        if availability_error:
            return availability_error

        team_config = session_config.get("team_config", {})
        team_size = team_config.get("team_size", 3)
        task_description = team_config.get("task_description", "")
        roles = team_config.get("roles", [])

        # Build team name from project ID
        project_id = session_config["project_id"]
        team_name = f"hive-{project_id[:8]}"

        # Build team creation prompt with roles
        if roles:
            roles_text = "Spawn teammates: " + ", ".join(f"one for {r}" for r in roles)
        else:
            roles_text = f"Spawn {team_size} teammates."

        prompt = (
            f"Create an agent team named '{team_name}' to work on: {task_description}. "
            f"{roles_text} "
            f"Coordinate work via the shared task list."
        )

        cmd = ["claude", "-p", prompt, "--dangerously-skip-permissions"]

        # Set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 in child environment
        env_additions = {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}

        session_id = ProjectSessionManager.create_session(
            project_id=project_id,
            cmd=cmd,
            cwd=session_config["cwd"],
            phase_id=session_config.get("phase_id"),
            plan_id=session_config.get("plan_id"),
            agent_id=session_config.get("agent_id"),
            worktree_path=session_config.get("worktree_path"),
            execution_type="team_spawn",
            execution_mode="autonomous",
            env=env_additions,
        )

        # Start team filesystem monitor
        TeamMonitorService.start_monitoring(
            session_id=session_id,
            team_name=team_name,
        )

        info = ProjectSessionManager.get_session_info(session_id)
        return {
            "session_id": session_id,
            "pid": info["pid"] if info else None,
            "status": "active",
            "team_name": team_name,
        }

    def monitor(self, session_id: str) -> dict:
        """Check team session status including team members and tasks.

        Merges base session info with TeamMonitorService state.
        """
        info = ProjectSessionManager.get_session_info(session_id)
        if not info:
            base = {
                "alive": False,
                "status": "unknown",
                "output_lines": 0,
                "last_activity_at": None,
            }
        else:
            base = {
                "alive": info["status"] == "active",
                "status": info["status"],
                "output_lines": info.get("output_lines", 0),
                "last_activity_at": info.get("last_activity_at"),
            }

        team_state = TeamMonitorService.get_state(session_id)
        if team_state:
            base["team_name"] = team_state.get("team_name")
            base["members"] = team_state.get("members", [])
            base["tasks"] = team_state.get("tasks", [])

        return base

    def stop(self, session_id: str) -> bool:
        """Stop team session and its monitor."""
        TeamMonitorService.stop_monitoring(session_id)
        return ProjectSessionManager.stop_session(session_id)

    def get_output(self, session_id: str, last_n: int = 100) -> list[str]:
        """Get recent output lines from the session's ring buffer."""
        return ProjectSessionManager.get_output(session_id, last_n=last_n)


# =============================================================================
# Handler Registry
# =============================================================================

# Static registry -- maps execution_type string to handler instance.
HANDLER_REGISTRY: dict[str, ExecutionTypeHandler] = {
    "direct": DirectExecutionHandler(),
    "ralph_loop": RalphSessionHandler(),
    "team_spawn": TeamSpawnHandler(),
}


def get_handler(execution_type: str) -> Optional[ExecutionTypeHandler]:
    """Get handler for an execution type.

    Args:
        execution_type: The execution type string (e.g., "direct").

    Returns:
        The handler instance, or None if not registered.
    """
    return HANDLER_REGISTRY.get(execution_type)
