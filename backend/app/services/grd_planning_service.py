"""GrdPlanningService -- GRD command dispatch via PTY sessions with single-session enforcement.

Manages the lifecycle of GRD planning command invocations from the web UI.
Wraps PTY session creation with planning-specific logic: single active session
per project, command construction for /grd:{command} prompts, and grd_init_status
tracking.

Per locked decision: no reimplementation of GRD logic in Python. GRD commands
execute within an AI session (Claude Code + GRD plugin). This service ONLY
manages session lifecycle.
"""

import logging
from typing import Optional

from ..database import get_project
from .execution_type_handler import get_handler
from .project_session_manager import ProjectSessionManager

logger = logging.getLogger(__name__)


class GrdPlanningService:
    """Service for dispatching GRD planning commands via PTY sessions.

    Follows the classmethod singleton pattern used by GrdSyncService and
    ExecutionLogService. All state is class-level.
    """

    # In-memory tracking: project_id -> session_id
    _active_planning_sessions: dict[str, str] = {}

    @classmethod
    def invoke_command(cls, project_id: str, command: str, args: dict = None) -> dict:
        """Invoke a GRD planning command in a new PTY session.

        Looks up the project, checks for an existing active planning session,
        builds the /grd:{command} prompt, and creates a PTY session via the
        direct execution handler.

        Args:
            project_id: Target project ID.
            command: GRD command name (e.g., "plan-phase", "discuss-phase").
            args: Optional command arguments as key-value pairs.

        Returns:
            {"session_id": str, "status": "running"} on success,
            {"error": str} on failure.
        """
        project = get_project(project_id)
        if not project:
            return {"error": "Project not found"}

        local_path = project.get("local_path")
        if not local_path:
            return {"error": "Project has no local_path configured"}

        # Check for existing active planning session
        existing_id = cls._active_planning_sessions.get(project_id)
        if existing_id:
            info = ProjectSessionManager.get_session_info(existing_id)
            if info and info.get("status") == "active":
                return {
                    "error": "Planning session already active",
                    "session_id": existing_id,
                }
            # Stale entry -- remove and proceed
            del cls._active_planning_sessions[project_id]

        # Build the /grd:{command} prompt
        prompt = f"/grd:{command}"
        if args:
            args_str = " ".join(f"{v}" for v in args.values())
            prompt = f"{prompt} {args_str}"

        cmd = ["claude", "-p", prompt]

        # Create session via the direct execution handler
        handler = get_handler("direct")
        if not handler:
            return {"error": "Direct execution handler not registered"}

        session_config = {
            "project_id": project_id,
            "cmd": cmd,
            "cwd": local_path,
            "execution_type": "direct",
            "execution_mode": "interactive",
        }
        result = handler.start(session_config)

        session_id = result.get("session_id")
        if not session_id:
            return {"error": "Failed to create PTY session"}

        # Register in tracking dict
        cls._active_planning_sessions[project_id] = session_id
        logger.info(
            "Started GRD planning session %s for project %s (command=%s)",
            session_id,
            project_id,
            command,
        )

        return {"session_id": session_id, "status": "running"}

    @classmethod
    def get_active_planning_session(cls, project_id: str) -> Optional[str]:
        """Get the active planning session ID for a project, if any.

        Validates the session is still alive. Removes stale entries.

        Returns:
            session_id if an active planning session exists, None otherwise.
        """
        session_id = cls._active_planning_sessions.get(project_id)
        if not session_id:
            return None

        info = ProjectSessionManager.get_session_info(session_id)
        if info and info.get("status") == "active":
            return session_id

        # Stale -- clean up
        del cls._active_planning_sessions[project_id]
        return None

    @classmethod
    def unregister_session(cls, session_id: str):
        """Remove a session from the active tracking dict.

        Called when a session completes to free the project for new sessions.
        """
        to_remove = [
            pid
            for pid, sid in cls._active_planning_sessions.items()
            if sid == session_id
        ]
        for pid in to_remove:
            del cls._active_planning_sessions[pid]
            logger.info(
                "Unregistered planning session %s for project %s",
                session_id,
                pid,
            )

    @classmethod
    def get_init_status(cls, project_id: str) -> str:
        """Get the grd_init_status for a project.

        Returns:
            The grd_init_status value, defaulting to "none".
        """
        project = get_project(project_id)
        if not project:
            return "none"
        return project.get("grd_init_status") or "none"
