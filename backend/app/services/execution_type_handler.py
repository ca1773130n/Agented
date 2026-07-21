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
from typing import Any, Optional

from .goal_loop_runner import get_runner_state, start_runner, stop_runner
from .project_session_manager import ProjectSessionManager
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
            stream_json=session_config.get("stream_json", False),
            use_pty=session_config.get("use_pty", True),
            yolo_mode=session_config.get("yolo_mode", False),
            forge_bundle=session_config.get("forge_bundle"),
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
    """Handler for Ralph autonomous loop execution (v0.6.0 unified loops).

    Ralph is now a thin profile over the goal-loop executor: it builds a
    ``LoopSpec`` legacy dict (``agent_task`` body, ``context_policy=reset``,
    git-commit stagnation circuit breaker) and drives the SAME
    ``goal_loop_runner`` that powers ``goal_loop`` sessions. The session is a
    stream-json claude process (no PTY), so a Ralph run is resumable and
    fully iteration-tracked through the shared ``goal_loop_iterations`` table.
    The retired ``RalphMonitorService`` git-progress logic now lives in
    ``loop_progress`` and is consumed by the executor's stagnation exit.

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
        """Start a Ralph loop session on the unified goal-loop executor.

        Checks for the ralph-wiggum plugin, builds a ``LoopSpec`` legacy dict
        (tagged ``_execution_type="ralph"`` so the runner parses an
        ``agent_task`` / ``context_policy=reset`` spec), spawns a stream-json
        claude session (no PTY, mirroring ``GoalLoopSessionHandler``),
        persists the config, and drives the shared ``start_runner``.
        """
        # Prerequisite check: ralph-wiggum plugin must be installed
        plugin_error = self._check_ralph_plugin()
        if plugin_error:
            return plugin_error

        ralph_config = session_config.get("ralph_config", {})
        task_description = ralph_config.get("task_description", "Complete the task.")

        # Tag the legacy dict so the runner parses it through the ralph branch
        # of LoopSpec.from_legacy_config (agent_task body, reset context,
        # git-commit stagnation circuit breaker).
        cfg = {**ralph_config, "_execution_type": "ralph"}

        # Stream-json claude session — same shape as GoalLoopSessionHandler.
        # The runner pumps the goal/continue prompts via the input route.
        cmd = session_config.get("cmd") or [
            "claude",
            "--print",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-hook-events",
            "--include-partial-messages",
        ]

        session_id = ProjectSessionManager.create_session(
            project_id=session_config["project_id"],
            cmd=cmd,
            cwd=session_config["cwd"],
            phase_id=session_config.get("phase_id"),
            plan_id=session_config.get("plan_id"),
            agent_id=session_config.get("agent_id"),
            worktree_path=session_config.get("worktree_path"),
            # Persist the registry-consistent key so the generic monitor/stop
            # endpoint (grd_routes.monitor_session -> get_handler) can resolve a
            # handler. The runner reads cfg["_execution_type"]="ralph" (set above)
            # to drive LoopSpec parsing — that tag lives on the config dict, not
            # the DB row, so the two concerns stay decoupled.
            execution_type="ralph_loop",
            execution_mode=session_config.get("execution_mode", "autonomous"),
            stream_json=True,
            use_pty=False,
            yolo_mode=session_config.get("yolo_mode", False),
            forge_bundle=session_config.get("forge_bundle"),
            super_agent_id=session_config.get("super_agent_id"),
        )

        # Persist config + spawn the shared driver thread.
        from app.db import set_goal_loop_config

        try:
            set_goal_loop_config(session_id, cfg)
        except Exception:
            logger.warning("ralph: failed to persist config for %s", session_id, exc_info=True)
        start_runner(session_id, cfg, cwd=session_config.get("cwd"))

        info = ProjectSessionManager.get_session_info(session_id)
        return {
            "session_id": session_id,
            "pid": info["pid"] if info else None,
            "status": "active",
            "goal": task_description,
        }

    def monitor(self, session_id: str) -> dict:
        """Check Ralph session status including iteration tracking.

        Merges base session info with the shared goal-loop runner state.
        """
        info = ProjectSessionManager.get_session_info(session_id)
        base = (
            {
                "alive": info["status"] == "active",
                "status": info["status"],
                "output_lines": info.get("output_lines", 0),
                "last_activity_at": info.get("last_activity_at"),
            }
            if info
            else {
                "alive": False,
                "status": "unknown",
                "output_lines": 0,
                "last_activity_at": None,
            }
        )
        runner = get_runner_state(session_id)
        if runner:
            base.update(runner)
        return base

    def stop(self, session_id: str) -> bool:
        """Stop Ralph session and its shared runner thread."""
        stop_runner(session_id)
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
            pass  # Intentionally silenced: cleanup/IO operation is best-effort

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
        team_name = f"agented-{project_id[:8]}"

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


class GoalLoopSessionHandler(ExecutionTypeHandler):
    """Handler for goal-loop autonomous sessions (v0.7.74).

    Spawns an underlying claude stream-json session (same shape as
    ``direct``), persists the goal config onto the row, and starts
    a ``GoalLoopRunner`` thread that watches turn boundaries and
    decides whether to continue. The runner owns termination
    (iteration cap, wall-time cap, judge says met); this handler
    just wires the start + stop + monitor surface.
    """

    def start(self, session_config: dict) -> dict:
        goal_config = session_config.get("goal_loop_config") or {}
        if not goal_config.get("goal", "").strip():
            return {"error": "goal_loop_config.goal is required"}

        # Reuse the direct-session command shape — chat-mode claude
        # with stream-json + hook/partial events. The runner pumps
        # user messages via the existing input route.
        cmd = session_config.get("cmd") or [
            "claude",
            "--print",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-hook-events",
            "--include-partial-messages",
        ]
        # v0.7.92 — when ``session_config["system_prompt_override"]``
        # is set (e.g. the SA Ouroboros bridge injecting the SA's
        # assembled SOUL/IDENTITY/ROLE prompt), append it to the
        # claude CLI via ``--append-system-prompt`` (the same flag
        # the ``context_renderers.claude`` renderer uses — NOT the
        # lookalike ``--system-prompt``, which in claude-cli
        # overrides rather than appends and produces silently-wrong
        # runs here). Idempotent: if a prior layer already added
        # the flag we skip. Skipped entirely when the caller
        # supplied an explicit ``cmd`` so we don't double-stack a
        # prompt the caller already encoded.
        system_prompt = session_config.get("system_prompt_override")
        if system_prompt and not session_config.get("cmd") and "--append-system-prompt" not in cmd:
            cmd = [*cmd, "--append-system-prompt", system_prompt]
        session_id = ProjectSessionManager.create_session(
            project_id=session_config["project_id"],
            cmd=cmd,
            cwd=session_config["cwd"],
            phase_id=session_config.get("phase_id"),
            plan_id=session_config.get("plan_id"),
            agent_id=session_config.get("agent_id"),
            worktree_path=session_config.get("worktree_path"),
            execution_type="goal_loop",
            execution_mode=session_config.get("execution_mode", "autonomous"),
            stream_json=True,
            use_pty=False,
            yolo_mode=session_config.get("yolo_mode", False),
            forge_bundle=session_config.get("forge_bundle"),
            super_agent_id=session_config.get("super_agent_id"),
        )

        # Persist config + spawn the driver thread.
        from app.db import set_goal_loop_config

        from .goal_loop_runner import start_runner

        try:
            set_goal_loop_config(session_id, goal_config)
        except Exception:
            logger.warning("goal_loop: failed to persist config for %s", session_id, exc_info=True)
        start_runner(session_id, goal_config, cwd=session_config.get("cwd"))

        info = ProjectSessionManager.get_session_info(session_id)
        return {
            "session_id": session_id,
            "pid": info["pid"] if info else None,
            "status": "active",
        }

    def monitor(self, session_id: str) -> dict:
        from .goal_loop_runner import get_runner_state

        info = ProjectSessionManager.get_session_info(session_id)
        base = (
            {
                "alive": info["status"] == "active",
                "status": info["status"],
                "output_lines": info.get("output_lines", 0),
                "last_activity_at": info.get("last_activity_at"),
            }
            if info
            else {
                "alive": False,
                "status": "unknown",
                "output_lines": 0,
                "last_activity_at": None,
            }
        )
        runner = get_runner_state(session_id)
        if runner:
            base.update(runner)
        return base

    def stop(self, session_id: str) -> bool:
        from .goal_loop_runner import stop_runner

        stop_runner(session_id)
        return ProjectSessionManager.stop_session(session_id)

    def get_output(self, session_id: str, last_n: int = 100) -> list[str]:
        return ProjectSessionManager.get_output(session_id, last_n=last_n)


class GrdEvolveSessionHandler(ExecutionTypeHandler):
    """Handler for ``gd evolve`` sessions (v0.7.88).

    ``gd evolve`` is GRD's self-improvement loop: discover →
    group → execute → review → repeat. Long-running (hours),
    spawns its own Claude subprocesses internally — so we drive
    it as a project session and let PSM broker stdout. The
    companion ``GrdEvolveRunner`` thread polls
    ``.planning/EVOLVE-STATE.json`` for live iteration progress.

    Required ``session_config``:
      * ``project_id`` / ``cwd`` (standard).
      * ``evolve_config`` — ``{iterations, pick_pct, dry_run,
        no_worktree, max_turns, timeout_minutes}``. All fields
        optional; defaults match the CLI defaults
        (``iterations=1, pick_pct=50``).
    """

    def start(self, session_config: dict) -> dict:
        from app.db import create_evolve_run

        from .grd_cli_service import GrdCliService
        from .grd_evolve_runner import start_evolve_state_sync

        gd_path = GrdCliService.gd_path()
        if not gd_path:
            return {
                "error": (
                    "gd binary not detected — install GRD v0.4.x "
                    "(@jokerized/getresearchdone) or set CLAUDE_PLUGIN_ROOT so "
                    "the binary detection finds it."
                )
            }

        cwd = session_config["cwd"]
        project_id = session_config["project_id"]
        evolve_config = session_config.get("evolve_config") or {}
        iterations = int(evolve_config.get("iterations") or 1)
        pick_pct = int(evolve_config.get("pick_pct") or 50)

        # Build the CLI invocation. We call ``gd evolve`` directly
        # rather than ``grd-tools.js evolve run`` because ``gd`` is
        # the v0.3.24+ unified entry point and emits the same
        # JSON progress GRD's own commands consume.
        cmd = [
            "node",
            gd_path,
            "evolve",
            "--iterations",
            str(iterations),
            "--pick-pct",
            str(pick_pct),
            "--json",
        ]
        if evolve_config.get("dry_run"):
            cmd.append("--dry-run")
        if evolve_config.get("no_worktree"):
            cmd.append("--no-worktree")
        if evolve_config.get("max_turns"):
            cmd += ["--max-turns", str(int(evolve_config["max_turns"]))]
        if evolve_config.get("timeout_minutes"):
            cmd += ["--timeout", str(int(evolve_config["timeout_minutes"]))]

        session_id = ProjectSessionManager.create_session(
            project_id=project_id,
            cmd=cmd,
            cwd=cwd,
            phase_id=session_config.get("phase_id"),
            plan_id=session_config.get("plan_id"),
            agent_id=session_config.get("agent_id"),
            worktree_path=session_config.get("worktree_path"),
            execution_type="grd_evolve",
            execution_mode=session_config.get("execution_mode", "autonomous"),
            stream_json=False,  # gd evolve emits its own JSON summary lines
            use_pty=False,
            yolo_mode=session_config.get("yolo_mode", False),
        )

        # Persist the run row first so the poller's UPDATE has
        # something to write through to. Failures here are
        # logged but don't kill the session — the operator still
        # gets stdout via PSM.
        try:
            run_id = create_evolve_run(
                project_id=project_id,
                session_id=session_id,
                config=evolve_config,
                total_iterations=iterations,
                pick_pct=pick_pct,
            )
        except Exception:
            logger.warning("grd_evolve: failed to insert run row for %s", session_id, exc_info=True)
            run_id = None

        planning_dir = str(Path(cwd).expanduser().resolve() / ".planning")
        start_evolve_state_sync(session_id, planning_dir)

        info = ProjectSessionManager.get_session_info(session_id)
        return {
            "session_id": session_id,
            "evolve_run_id": run_id,
            "pid": info["pid"] if info else None,
            "status": "active",
        }

    def monitor(self, session_id: str) -> dict:
        from app.db import get_evolve_run_by_session

        info = ProjectSessionManager.get_session_info(session_id)
        base = (
            {
                "alive": info["status"] == "active",
                "status": info["status"],
                "output_lines": info.get("output_lines", 0),
                "last_activity_at": info.get("last_activity_at"),
            }
            if info
            else {
                "alive": False,
                "status": "unknown",
                "output_lines": 0,
                "last_activity_at": None,
            }
        )
        run = get_evolve_run_by_session(session_id)
        if run:
            base["evolve_run_id"] = run["id"]
            base["iteration"] = run.get("iteration") or 0
            base["total_iterations"] = run.get("total_iterations")
            base["pick_pct"] = run.get("pick_pct")
            base["last_state_synced_at"] = run.get("last_state_synced_at")
        return base

    def stop(self, session_id: str) -> bool:
        from .grd_evolve_runner import stop_evolve_state_sync

        stop_evolve_state_sync(session_id)
        return ProjectSessionManager.stop_session(session_id)

    def get_output(self, session_id: str, last_n: int = 100) -> list[str]:
        return ProjectSessionManager.get_output(session_id, last_n=last_n)


class GrdChatSessionHandler(ExecutionTypeHandler):
    """Handler for GRD-driven chat turns (v0.8.0, REQ-11).

    Mirrors ``GoalLoopSessionHandler`` but spawns a one-shot
    ``claude -p`` stream-json session whose single prompt is a
    ``/grd:<command> "<task>"`` invocation (default ``/grd:quick``).
    The command is chosen from the classifier intent via
    ``GRD_COMMAND_MAP``. The project cwd is resolved through
    ``ProjectWorkspaceService.resolve_working_directory`` so the GRD
    command runs against the real checkout, and the phase-17 forge
    wiring (``forge_bundle`` / ``super_agent_id``) is forwarded onto
    ``create_session`` unchanged.

    The PSM→chat-SSE bridge (``grd_chat_bridge.bridge_psm_to_chat``)
    is what maps this session's stream-json output back onto the chat
    state_delta protocol; this handler only owns start + stop +
    monitor. ``stop`` stops the PSM session so a chat abort does not
    orphan the GRD subprocess (risk 5).

    Required ``session_config``:
      * ``project_id`` (standard).
      * ``task`` — the user turn text the GRD command operates on.
      * ``grd_command`` (optional) — a pre-resolved ``/grd:<cmd>``
        from the classifier; when absent it is derived from
        ``intent`` via ``GRD_COMMAND_MAP``, defaulting to
        ``/grd:quick``.
      * ``intent`` (optional) — classifier intent bucket.
      * ``cwd`` (optional) — overrides the resolved project cwd.
    """

    @staticmethod
    def _resolve_grd_command(session_config: dict) -> str:
        """Pick the ``/grd:<cmd>`` token for this turn.

        Precedence: an explicit ``grd_command`` from the classifier,
        else a map lookup on ``intent``, else the ``/grd:quick``
        default. The leading slash is normalized so the final token
        is exactly one ``/grd:<cmd>`` string regardless of whether
        the map value already carries the prefix.
        """
        from .turn_classifier_service import GRD_COMMAND_MAP

        raw = session_config.get("grd_command")
        if not raw:
            intent = session_config.get("intent")
            raw = GRD_COMMAND_MAP.get(intent or "", "/grd:quick")
        cmd = (raw or "/grd:quick").strip()
        # Normalize: strip any leading slash and the grd: prefix, then
        # re-apply exactly one "/grd:" so callers passing "quick",
        # "/quick", "grd:quick", or "/grd:quick" all converge.
        cmd = cmd.lstrip("/")
        if cmd.startswith("grd:"):
            cmd = cmd[len("grd:") :]
        return f"/grd:{cmd}"

    def start(self, session_config: dict) -> dict:
        task = (session_config.get("task") or "").strip()
        if not task:
            return {"error": "grd_chat: session_config.task is required"}

        project_id = session_config["project_id"]

        # Resolve the project cwd so the GRD command runs against the
        # real checkout. An explicit cwd wins (test seams / worktrees).
        cwd = session_config.get("cwd")
        if not cwd:
            from .project_workspace_service import ProjectWorkspaceService

            cwd = ProjectWorkspaceService.resolve_working_directory(project_id)

        grd_command = self._resolve_grd_command(session_config)

        # One-shot stream-json invocation — same shape GrdPlanningService
        # uses for /grd: commands. The task is the single prompt. ``task``
        # can arrive from non-operator sources (delegation / @mention turns,
        # 19-03), so JSON-encode it rather than naive `"{task}"` interpolation:
        # this escapes embedded quotes/newlines/backslashes and prevents the
        # task from breaking out of the `/grd:<cmd> "<task>"` prompt framing.
        cmd = [
            "claude",
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            f"{grd_command} {json.dumps(task)}",
        ]

        session_id = ProjectSessionManager.create_session(
            project_id=project_id,
            cmd=cmd,
            cwd=cwd,
            phase_id=session_config.get("phase_id"),
            plan_id=session_config.get("plan_id"),
            agent_id=session_config.get("agent_id"),
            worktree_path=session_config.get("worktree_path"),
            execution_type="grd_chat",
            execution_mode=session_config.get("execution_mode", "autonomous"),
            stream_json=True,
            use_pty=False,
            yolo_mode=session_config.get("yolo_mode", False),
            forge_bundle=session_config.get("forge_bundle"),
            super_agent_id=session_config.get("super_agent_id"),
        )

        info = ProjectSessionManager.get_session_info(session_id)
        return {
            "session_id": session_id,
            "pid": info["pid"] if info else None,
            "status": "active",
        }

    def monitor(self, session_id: str) -> dict:
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
        # Stop the PSM session so a chat abort does not orphan the GRD
        # subprocess (risk 5).
        return ProjectSessionManager.stop_session(session_id)

    def get_output(self, session_id: str, last_n: int = 100) -> list[str]:
        return ProjectSessionManager.get_output(session_id, last_n=last_n)


class GrdResearchSessionHandler(ExecutionTypeHandler):
    """Handler for the GRD autoresearch loop (v0.8.0, REQ-14).

    Mirrors ``GrdChatSessionHandler`` verbatim but spawns a one-shot
    ``claude -p`` stream-json session whose single prompt is a
    ``/grd:research <json.dumps(question)>`` invocation. Where the chat
    handler maps an intent to a ``/grd:<cmd>`` token, this handler is
    pinned to ``/grd:research`` (optionally ``/grd:research resume
    <thread_id>`` when ``thread_id`` is supplied). The project cwd is
    resolved through ``ProjectWorkspaceService.resolve_working_directory``
    so the loop runs against the real checkout (raising ``ValueError``
    when no clone exists — that behavior is preserved), and the phase-17
    forge wiring (``forge_bundle`` / ``super_agent_id``) is forwarded onto
    ``create_session`` unchanged.

    The generic ``/sessions/{session_id}/output`` SSE route is what
    streams this session back to the operator — this handler owns only
    start + stop + monitor. ``stop`` stops the PSM session so an abort
    does not orphan the GRD subprocess.

    Required ``session_config``:
      * ``project_id`` (standard).
      * ``question`` — the research question the loop investigates
        (or, when ``thread_id`` is set for a resume, optional).
      * ``thread_id`` (optional) — resume an existing research thread
        instead of starting a fresh one.
      * ``max_iterations`` (optional, int) — appends ``--max-iterations N``.
      * ``no_gates`` (optional, bool) — appends ``--no-gates``.
      * ``deep`` (optional, bool) — FRESH-RUN ONLY. Swaps the prompt to
        ``/grd:deep-research <question>`` (GRD 0.4.14 parallel KG-grounded,
        adversarially-verified research). The ``--max-iterations`` /
        ``--no-gates`` loop knobs are SKIPPED for a deep run (deep-research
        ignores them). Ignored on a resume (``thread_id`` set) — deep has
        no resume.
      * ``ultracode`` (optional, bool) — deep-run only; appends the bare
        ``ultracode`` keyword (escalates every subagent to Opus/max effort,
        significantly costlier).
      * ``cwd`` (optional) — overrides the resolved project cwd.
    """

    @staticmethod
    def _ensure_interactive_config(cwd: str, interactive: dict) -> None:
        """Merge ``research_gates.interactive`` into ``<cwd>/.planning/config.json``
        so GRD 0.5.0's ``readInteractiveConfig`` picks up the steering posture.
        Preserves every other config key; only sets the interactive knobs we manage.

        Hardened (codex review): an exclusive flock serializes the read-modify-write
        against concurrent research starts on the same project; the write is atomic
        (temp file + ``os.replace``) so a reader never sees a torn file; and a
        MALFORMED existing config FAILS CLOSED (raises) rather than being silently
        overwritten with only our block — that would destroy unrelated config keys.
        A missing file starts fresh; failures propagate (the operator asked for a
        steering mode we couldn't set up)."""
        import fcntl
        import hashlib
        import stat
        import tempfile

        cfg_dir = os.path.join(cwd, ".planning")
        cfg_path = os.path.join(cfg_dir, "config.json")
        os.makedirs(cfg_dir, exist_ok=True)
        # Keep the lock file OUT of the project worktree (a tracked .planning/
        # would otherwise gain an untracked .lock after any research start), but
        # its temp-dir name is PREDICTABLE (a hash of cfg_path), so guard against a
        # symlink/temp-file attack on a shared host: (1) a per-uid, 0700, we-own-it
        # lock dir an attacker can't plant files in, and (2) O_NOFOLLOW|0600 on the
        # lock file so a pre-placed symlink is refused rather than followed+truncated.
        lock_root = os.path.join(tempfile.gettempdir(), f"agented-grd-{os.getuid()}")
        os.makedirs(lock_root, mode=0o700, exist_ok=True)
        st = os.lstat(lock_root)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or (st.st_mode & 0o077):
            raise ValueError(f"refusing unsafe lock dir {lock_root}")
        lock_path = os.path.join(
            lock_root, hashlib.sha1(cfg_path.encode()).hexdigest() + ".lock"
        )
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                with open(cfg_path, encoding="utf-8") as fh:
                    data = json.load(fh)
                if not isinstance(data, dict):
                    data = {}
            except FileNotFoundError:
                data = {}
            except json.JSONDecodeError as e:
                # Fail closed: overwriting a corrupt-but-present config with just
                # our interactive block would silently drop every other key.
                raise ValueError(f"cannot update malformed {cfg_path}: {e}") from e
            gates = data.get("research_gates")
            if not isinstance(gates, dict):
                gates = data["research_gates"] = {}
            existing = gates.get("interactive")
            gates["interactive"] = {
                **(existing if isinstance(existing, dict) else {}),
                **interactive,
            }
            fd, tmp = tempfile.mkstemp(dir=cfg_dir, prefix=".config-", suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2)
                os.replace(tmp, cfg_path)  # atomic — no torn read by a concurrent gd
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        finally:
            os.close(lock_fd)

    def start(self, session_config: dict) -> dict:
        thread_id = (session_config.get("thread_id") or "").strip()
        question = (session_config.get("question") or "").strip()
        # A fresh run needs a question; a resume run rides on the thread_id.
        if not thread_id and not question:
            return {"error": "grd_research: session_config.question is required"}

        project_id = session_config["project_id"]

        # Resolve the project cwd so the GRD command runs against the real
        # checkout. An explicit cwd wins (test seams / worktrees). This
        # raises ValueError when no clone exists — preserved on purpose.
        cwd = session_config.get("cwd")
        if not cwd:
            from .project_workspace_service import ProjectWorkspaceService

            cwd = ProjectWorkspaceService.resolve_working_directory(project_id)

        # GRD 0.5.0 interactive checkpoints: when the operator answers a paused
        # thread's pendingCheckpoint from Agented, write the answers to a temp JSON
        # file keyed by question id ({"<qid>": {"label", "text"?}}) and pass
        # `--answers <path>` to `gd research resume`. Answers can carry freeform
        # operator text, so they go through a FILE, never argv (19-04 hardening).
        answers_path: Optional[str] = None
        raw_answers = session_config.get("answers") if thread_id else None
        if isinstance(raw_answers, list) and raw_answers:
            mapping: dict[str, dict] = {}
            for a in raw_answers:
                if not isinstance(a, dict):
                    continue
                qid = a.get("question_id") or a.get("questionId")
                if not qid or a.get("label") is None:
                    continue
                entry: dict[str, Any] = {"label": a["label"]}
                if a.get("text"):
                    entry["text"] = str(a["text"])
                mapping[str(qid)] = entry
            if mapping:
                import tempfile

                fd, answers_path = tempfile.mkstemp(prefix="gd-answers-", suffix=".json")
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(mapping, fh)

        # Build the /grd:research prompt. The question can arrive from
        # non-operator sources, so JSON-encode it (escapes embedded
        # quotes/newlines/backslashes) rather than naive `"{question}"`
        # interpolation — this is the 19-04 prompt-injection hardening.
        # ``deep`` is a fresh-run-only flag: a resume rides on the thread_id
        # loop, deep-research has no resume concept.
        deep = bool(session_config.get("deep")) and not thread_id
        if thread_id:
            prompt = f"/grd:research resume {json.dumps(thread_id)}"
            if answers_path:
                # gd research resume <id> --answers <file> — resolves the paused
                # pendingCheckpoint before the loop re-enters its gates.
                prompt = f"{prompt} --answers {json.dumps(answers_path)}"
        elif deep:
            # GRD 0.4.14 /grd:deep-research — parallel KG-grounded,
            # adversarially-verified research. json.dumps keeps the 19-04
            # injection hardening; ``ultracode`` is the bare keyword the
            # command parses (deep-research.md §1).
            prompt = f"/grd:deep-research {json.dumps(question)}"
            if session_config.get("ultracode"):
                prompt = f"{prompt} ultracode"
        else:
            prompt = f"/grd:research {json.dumps(question)}"

        # Optional loop knobs are appended to the prompt tail, only when
        # provided. ``--max-iterations N`` caps the loop; ``--no-gates``
        # runs without human-verify checkpoints. Deep-research ignores both,
        # so the tail is skipped entirely for a deep run.
        if not deep:
            max_iterations = session_config.get("max_iterations")
            if max_iterations is not None:
                prompt = f"{prompt} --max-iterations {int(max_iterations)}"
            if session_config.get("no_gates"):
                prompt = f"{prompt} --no-gates"

        cmd = [
            "claude",
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            prompt,
        ]

        # GRD 0.5.0 interactive steering posture. The checkpoint mechanism
        # (research_gates.interactive, SEED/HYPOTHESIZE/DESIGN/DECIDE) is inert
        # unless `enabled` is written into <cwd>/.planning/config.json, so the
        # posture both writes that config and sets the env. Three operator choices:
        #   autopilot (default) — headless; gd resolves each gate to its
        #     recommended default (GRD_AUTOPILOT=1). No config, never hangs.
        #   panel — headless, but each gate is resolved by GRD's multi-backend AI
        #     discussion panel (interactive.enabled + fallback=panel); degrade-safe
        #     to recommended defaults. GRD_AUTOPILOT keeps the run from ever pausing.
        #   attended — a human steers: the loop PAUSES at each gate (enabled=true,
        #     no GRD_AUTOPILOT); Agented surfaces it via /research/status
        #     pendingCheckpoint + resume --answers.
        steering = session_config.get("research_steering")
        if steering not in ("autopilot", "panel", "attended"):
            # Back-compat: derive from the legacy execution_mode flag.
            legacy = session_config.get("execution_mode", "autonomous")
            steering = "autopilot" if legacy == "autonomous" else "attended"
        if steering == "attended":
            execution_mode = "attended"
            research_env = None
            self._ensure_interactive_config(cwd, {"enabled": True})
        elif steering == "panel":
            execution_mode = "autonomous"
            research_env = {"GRD_AUTOPILOT": "1"}
            self._ensure_interactive_config(cwd, {"enabled": True, "fallback": "panel"})
        else:  # autopilot
            execution_mode = "autonomous"
            research_env = {"GRD_AUTOPILOT": "1"}
            # Neutralize ONLY the panel fallback, not `enabled`. GRD_AUTOPILOT
            # already makes the run unattended and resolve to recommended defaults
            # for every posture EXCEPT a lingering `fallback:"panel"` (panel
            # engages on enabled && !attended && fallback==='panel'). Pinning
            # fallback:"recommended" defeats a stale panel from a prior run while
            # leaving `enabled` untouched — so we don't clobber a config an
            # operator set for their own attended/manual GRD use.
            self._ensure_interactive_config(cwd, {"fallback": "recommended"})

        session_id = ProjectSessionManager.create_session(
            project_id=project_id,
            cmd=cmd,
            cwd=cwd,
            phase_id=session_config.get("phase_id"),
            plan_id=session_config.get("plan_id"),
            agent_id=session_config.get("agent_id"),
            worktree_path=session_config.get("worktree_path"),
            execution_type="grd_research",
            execution_mode=execution_mode,
            env=research_env,
            stream_json=True,
            use_pty=False,
            yolo_mode=session_config.get("yolo_mode", False),
            forge_bundle=session_config.get("forge_bundle"),
            super_agent_id=session_config.get("super_agent_id"),
        )

        info = ProjectSessionManager.get_session_info(session_id)
        return {
            "session_id": session_id,
            "pid": info["pid"] if info else None,
            "status": "active",
        }

    def monitor(self, session_id: str) -> dict:
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
        # Stop the PSM session so an abort does not orphan the GRD
        # subprocess.
        return ProjectSessionManager.stop_session(session_id)

    def get_output(self, session_id: str, last_n: int = 100) -> list[str]:
        return ProjectSessionManager.get_output(session_id, last_n=last_n)


# =============================================================================
# Handler Registry
# =============================================================================

# Static registry -- maps execution_type string to handler instance.
HANDLER_REGISTRY: dict[str, ExecutionTypeHandler] = {
    "direct": DirectExecutionHandler(),
    "ralph_loop": RalphSessionHandler(),
    "team_spawn": TeamSpawnHandler(),
    "goal_loop": GoalLoopSessionHandler(),
    "grd_evolve": GrdEvolveSessionHandler(),
    "grd_chat": GrdChatSessionHandler(),
    "grd_research": GrdResearchSessionHandler(),
}


def get_handler(execution_type: str) -> Optional[ExecutionTypeHandler]:
    """Get handler for an execution type.

    Args:
        execution_type: The execution type string (e.g., "direct").

    Returns:
        The handler instance, or None if not registered.
    """
    return HANDLER_REGISTRY.get(execution_type)
