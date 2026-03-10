"""Team execution service with topology-based execution strategies.

This module is the public facade. It delegates execution tracking to
TeamExecutionTracker and topology strategies to the topology_strategies module.
"""

import json
import logging
import threading
from typing import Optional

from app.db.ids import generate_id

from .team_execution_tracker import TeamExecutionTracker
from .topology_strategies import (
    agent_to_trigger,
    execute_composite,
    execute_coordinator,
    execute_generator_critic,
    execute_hierarchical,
    execute_human_in_loop,
    execute_parallel,
    execute_sequential,
    get_agent_from_member,
)

logger = logging.getLogger(__name__)


class TeamExecutionService:
    """Service for executing agent teams according to their topology pattern."""

    # Backward-compatible proxies -- tests and external code may access these directly.
    _executions = TeamExecutionTracker._executions
    _lock = TeamExecutionTracker._lock

    @classmethod
    def execute_team(
        cls,
        team_id: str,
        message: str = "",
        event: dict = None,
        trigger_type: str = "manual",
        working_directory: str = None,
    ) -> str:
        """Execute a team according to its topology.

        Loads the team, validates it, dispatches to the appropriate topology
        strategy in a background daemon thread, and returns immediately with
        a tracking ID.

        Returns:
            team_exec_id: A tracking ID (team-exec-XXXXXXXX)
        """
        from ..database import get_team_detail

        team = get_team_detail(team_id)
        if not team:
            raise ValueError(f"Team not found: {team_id}")

        if not team.get("enabled", 1):
            raise ValueError(f"Team is disabled: {team_id}")

        topology = team.get("topology")
        if not topology:
            raise ValueError(f"Team has no topology configured: {team_id}")

        # Parse topology_config
        topology_config = team.get("topology_config")
        if topology_config and isinstance(topology_config, str):
            try:
                topology_config = json.loads(topology_config)
            except json.JSONDecodeError:
                topology_config = {}
        if not topology_config:
            topology_config = {}

        # Generate tracking ID
        team_exec_id = generate_id("team-exec-", 8)

        # Record tracking entry
        TeamExecutionTracker.register(team_exec_id, team_id, topology, trigger_type)

        # Strategy dispatch map
        strategy_map = {
            "sequential": execute_sequential,
            "parallel": execute_parallel,
            "coordinator": execute_coordinator,
            "generator_critic": execute_generator_critic,
            "hierarchical": execute_hierarchical,
            "human_in_loop": execute_human_in_loop,
            "composite": execute_composite,
        }

        strategy = strategy_map.get(topology)
        if not strategy:
            logger.error(f"Unknown topology '{topology}' for team {team_id}")
            TeamExecutionTracker.set_failed(team_exec_id)
            return team_exec_id

        # Run in background daemon thread
        thread = threading.Thread(
            target=cls._run_strategy,
            args=(
                team_exec_id,
                strategy,
                team,
                topology_config,
                message,
                event,
                trigger_type,
                working_directory,
            ),
            daemon=True,
        )
        thread.start()

        logger.info(
            f"Team execution started: {team_exec_id} (team={team_id}, "
            f"topology={topology}, trigger={trigger_type})"
        )
        return team_exec_id

    @classmethod
    def _run_strategy(
        cls,
        team_exec_id,
        strategy,
        team,
        config,
        message,
        event,
        trigger_type,
        working_directory=None,
    ) -> None:
        """Wrapper that runs a strategy and catches all errors."""
        try:
            # Build kwargs depending on whether the strategy needs tracker
            kwargs = {"run_agent": cls._run_agent_and_get_output}
            if strategy in (execute_human_in_loop, execute_composite):
                kwargs["tracker"] = TeamExecutionTracker

            execution_ids = strategy(
                team, config, message, event, trigger_type, working_directory, **kwargs
            )
            TeamExecutionTracker.set_completed(team_exec_id, execution_ids)
            logger.info(f"Team execution completed: {team_exec_id}")
        except Exception as e:
            logger.error(f"Team execution failed: {team_exec_id} - {e}", exc_info=True)
            TeamExecutionTracker.set_error(team_exec_id, str(e))
        finally:
            # Schedule cleanup after 5 minutes
            timer = threading.Timer(
                300, TeamExecutionTracker.cleanup_execution, args=[team_exec_id]
            )
            timer.daemon = True
            timer.start()

    @classmethod
    def get_execution_status(cls, team_exec_id: str) -> Optional[dict]:
        """Get the status of a team execution."""
        return TeamExecutionTracker.get_execution_status(team_exec_id)

    @classmethod
    def approve_execution(cls, team_exec_id: str) -> bool:
        """Approve a pending human-in-loop execution.

        Returns True if the execution was in pending_approval state and was
        successfully approved, False otherwise.
        """
        return TeamExecutionTracker.approve_execution(team_exec_id)

    @classmethod
    def _run_agent_and_get_output(
        cls,
        team: dict,
        agent_id: str,
        message: str,
        event: dict,
        trigger_type: str,
        working_directory: str = None,
    ) -> tuple:
        """Run a single agent and return (execution_id, stdout_output).

        Uses lazy import of ExecutionService to avoid circular imports.
        """
        from .execution_log_service import ExecutionLogService
        from .execution_service import ExecutionService

        agent = get_agent_from_member(team, agent_id)
        if not agent:
            logger.warning(f"Agent not found: {agent_id}")
            return None, ""

        pseudo_trigger = agent_to_trigger(agent, message, trigger_type, team_id=team.get("id"))

        # run_trigger blocks until completion (uses process.wait())
        execution_id = ExecutionService.run_trigger(
            trigger=pseudo_trigger,
            message_text=message,
            event=event or {},
            trigger_type=trigger_type,
            working_directory=working_directory,
        )

        # Retrieve output from the execution
        output = ""
        if execution_id:
            output = ExecutionLogService.get_stdout_log(execution_id)

        return execution_id, output

    # ------------------------------------------------------------------
    # Backward-compatible aliases for helpers that moved to modules
    # ------------------------------------------------------------------
    _agent_to_trigger = staticmethod(agent_to_trigger)
    _get_agent_from_member = staticmethod(get_agent_from_member)

    # ------------------------------------------------------------------
    # Backward-compatible strategy classmethods — delegate to module functions
    # ------------------------------------------------------------------

    @classmethod
    def _execute_sequential(cls, team, config, message, event, trigger_type, working_directory=None):
        return execute_sequential(
            team, config, message, event, trigger_type, working_directory,
            run_agent=cls._run_agent_and_get_output,
        )

    @classmethod
    def _execute_parallel(cls, team, config, message, event, trigger_type, working_directory=None):
        return execute_parallel(
            team, config, message, event, trigger_type, working_directory,
            run_agent=cls._run_agent_and_get_output,
        )

    @classmethod
    def _execute_coordinator(cls, team, config, message, event, trigger_type, working_directory=None):
        return execute_coordinator(
            team, config, message, event, trigger_type, working_directory,
            run_agent=cls._run_agent_and_get_output,
        )

    @classmethod
    def _execute_generator_critic(
        cls, team, config, message, event, trigger_type, working_directory=None
    ):
        return execute_generator_critic(
            team, config, message, event, trigger_type, working_directory,
            run_agent=cls._run_agent_and_get_output,
        )

    @classmethod
    def _execute_hierarchical(
        cls, team, config, message, event, trigger_type, working_directory=None
    ):
        return execute_hierarchical(
            team, config, message, event, trigger_type, working_directory,
            run_agent=cls._run_agent_and_get_output,
        )

    @classmethod
    def _execute_human_in_loop(
        cls, team, config, message, event, trigger_type, working_directory=None
    ):
        return execute_human_in_loop(
            team, config, message, event, trigger_type, working_directory,
            tracker=TeamExecutionTracker,
            run_agent=cls._run_agent_and_get_output,
        )

    @classmethod
    def _execute_composite(cls, team, config, message, event, trigger_type, working_directory=None):
        return execute_composite(
            team, config, message, event, trigger_type, working_directory,
            tracker=TeamExecutionTracker,
            run_agent=cls._run_agent_and_get_output,
        )
