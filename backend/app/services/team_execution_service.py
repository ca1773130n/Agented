"""Team execution service with topology-based execution strategies."""

import json
import logging
import random
import string
import threading
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class TeamExecutionService:
    """Service for executing agent teams according to their topology pattern."""

    # In-memory tracking of team executions: {team_exec_id: status_dict}
    _executions: Dict[str, dict] = {}
    _lock = threading.Lock()

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
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        team_exec_id = f"team-exec-{suffix}"

        # Record tracking entry
        with cls._lock:
            cls._executions[team_exec_id] = {
                "team_id": team_id,
                "topology": topology,
                "trigger_type": trigger_type,
                "status": "running",
                "execution_ids": [],
            }

        # Strategy dispatch map
        strategy_map = {
            "sequential": cls._execute_sequential,
            "parallel": cls._execute_parallel,
            "coordinator": cls._execute_coordinator,
            "generator_critic": cls._execute_generator_critic,
            "hierarchical": cls._execute_hierarchical,
            "human_in_loop": cls._execute_human_in_loop,
            "composite": cls._execute_composite,
        }

        strategy = strategy_map.get(topology)
        if not strategy:
            logger.error(f"Unknown topology '{topology}' for team {team_id}")
            with cls._lock:
                cls._executions[team_exec_id]["status"] = "failed"
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
    def _cleanup_execution(cls, team_exec_id: str):
        with cls._lock:
            cls._executions.pop(team_exec_id, None)

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
    ):
        """Wrapper that runs a strategy and catches all errors."""
        try:
            execution_ids = strategy(team, config, message, event, trigger_type, working_directory)
            with cls._lock:
                exec_entry = cls._executions.get(team_exec_id, {})
                exec_entry["execution_ids"] = execution_ids or []
                # Don't overwrite approval_timeout status set by human_in_loop
                if exec_entry.get("status") != "approval_timeout":
                    exec_entry["status"] = "completed"
            logger.info(f"Team execution completed: {team_exec_id}")
        except Exception as e:
            logger.error(f"Team execution failed: {team_exec_id} - {e}")
            with cls._lock:
                cls._executions[team_exec_id]["status"] = "failed"
                cls._executions[team_exec_id]["error"] = str(e)
        finally:
            # Schedule cleanup after 5 minutes
            timer = threading.Timer(300, cls._cleanup_execution, args=[team_exec_id])
            timer.daemon = True
            timer.start()

    @classmethod
    def get_execution_status(cls, team_exec_id: str) -> Optional[dict]:
        """Get the status of a team execution."""
        with cls._lock:
            return cls._executions.get(team_exec_id)

    @classmethod
    def _agent_to_trigger(
        cls,
        agent: dict,
        message: str,
        trigger_type: str = "manual",
        team_id: str = None,
    ) -> dict:
        """Create a trigger-compatible dict from agent data.

        Maps agent fields to the trigger dict format expected by ExecutionService.run_trigger().
        Injects _entity_type='agent' and _entity_id so token usage is attributed
        to the correct agent rather than a non-existent trigger ID.
        """
        system_prompt = agent.get("system_prompt") or ""
        prompt_template = f"{system_prompt}\n{message}" if system_prompt else message

        agent_id = agent.get("id", agent.get("agent_id", ""))

        pseudo_trigger = {
            "id": agent_id,
            "name": agent.get("name", "Unknown Agent"),
            "prompt_template": prompt_template,
            "backend_type": agent.get("backend_type", "claude"),
            "model": agent.get("model"),
            "trigger_source": trigger_type,
            "skill_command": None,
            "auto_resolve": False,
            # Entity attribution: ensures run_trigger records tokens as agent, not trigger
            "_entity_type": "agent",
            "_entity_id": agent_id,
        }

        if team_id:
            pseudo_trigger["_team_id"] = team_id

        return pseudo_trigger

    @classmethod
    def _get_agent_from_member(cls, team: dict, agent_id: str) -> Optional[dict]:
        """Get agent data from team members list by agent_id."""
        from ..database import get_agent

        # Try to get the full agent record from DB
        agent = get_agent(agent_id)
        if agent:
            return agent

        # Fall back to member data if agent record not found
        members = team.get("members", [])
        for member in members:
            if member.get("agent_id") == agent_id:
                return {
                    "id": agent_id,
                    "name": member.get("agent_name") or member.get("name", "Unknown"),
                    "backend_type": "claude",
                    "system_prompt": "",
                }
        return None

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

        agent = cls._get_agent_from_member(team, agent_id)
        if not agent:
            logger.warning(f"Agent not found: {agent_id}")
            return None, ""

        pseudo_trigger = cls._agent_to_trigger(agent, message, trigger_type, team_id=team.get("id"))

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

    @classmethod
    def _execute_sequential(
        cls,
        team: dict,
        config: dict,
        message: str,
        event: dict,
        trigger_type: str,
        working_directory: str = None,
    ) -> List[str]:
        """Execute agents in order, passing output from one to the next.

        Config expects: {"order": ["agent-id-1", "agent-id-2", ...]}
        """
        order = config.get("order", [])
        if not order:
            logger.warning(f"Sequential topology has no 'order' config for team {team['id']}")
            return []

        execution_ids = []
        current_message = message

        for agent_id in order:
            logger.info(
                f"Sequential: executing agent {agent_id} with message length={len(current_message)}"
            )
            execution_id, output = cls._run_agent_and_get_output(
                team, agent_id, current_message, event, trigger_type, working_directory
            )
            if execution_id:
                execution_ids.append(execution_id)
            # Pass output to next agent
            if output:
                current_message = output

        return execution_ids

    @classmethod
    def _execute_parallel(
        cls,
        team: dict,
        config: dict,
        message: str,
        event: dict,
        trigger_type: str,
        working_directory: str = None,
    ) -> List[str]:
        """Execute all agents simultaneously in threads.

        Config expects: {"agents": ["agent-id-1", "agent-id-2", ...]}
        """
        agents = config.get("agents", [])
        if not agents:
            logger.warning(f"Parallel topology has no 'agents' config for team {team['id']}")
            return []

        execution_ids = []
        exec_lock = threading.Lock()
        threads = []

        def _run_one(aid):
            eid, _ = cls._run_agent_and_get_output(
                team, aid, message, event, trigger_type, working_directory
            )
            if eid:
                with exec_lock:
                    execution_ids.append(eid)

        for agent_id in agents:
            t = threading.Thread(target=_run_one, args=(agent_id,), daemon=True)
            threads.append(t)
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        return execution_ids

    @classmethod
    def _execute_coordinator(
        cls,
        team: dict,
        config: dict,
        message: str,
        event: dict,
        trigger_type: str,
        working_directory: str = None,
    ) -> List[str]:
        """Execute coordinator first, then workers in parallel with coordinator's output.

        Config expects: {"coordinator": "agent-id", "workers": ["agent-id-1", ...]}
        """
        coordinator_id = config.get("coordinator")
        workers = config.get("workers", [])
        if not coordinator_id or not workers:
            logger.warning(
                f"Coordinator topology missing coordinator/workers for team {team['id']}"
            )
            return []

        execution_ids = []

        # Step 1: Execute coordinator with original message
        logger.info(f"Coordinator: executing coordinator agent {coordinator_id}")
        coord_eid, coord_output = cls._run_agent_and_get_output(
            team, coordinator_id, message, event, trigger_type, working_directory
        )
        if coord_eid:
            execution_ids.append(coord_eid)

        worker_message = coord_output if coord_output else message

        # Step 2: Execute workers in parallel with coordinator's output
        worker_eids = []
        exec_lock = threading.Lock()
        threads = []

        def _run_worker(aid):
            eid, _ = cls._run_agent_and_get_output(
                team, aid, worker_message, event, trigger_type, working_directory
            )
            if eid:
                with exec_lock:
                    worker_eids.append(eid)

        for worker_id in workers:
            t = threading.Thread(target=_run_worker, args=(worker_id,), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        execution_ids.extend(worker_eids)
        return execution_ids

    @classmethod
    def _execute_generator_critic(
        cls,
        team: dict,
        config: dict,
        message: str,
        event: dict,
        trigger_type: str,
        working_directory: str = None,
    ) -> List[str]:
        """Execute generator-critic loop until critic approves or max iterations.

        Config expects: {"generator": "agent-id", "critic": "agent-id", "max_iterations": 3}
        """
        generator_id = config.get("generator")
        critic_id = config.get("critic")
        max_iterations = config.get("max_iterations", 3)
        if not generator_id or not critic_id:
            logger.warning(
                f"Generator-critic topology missing generator/critic for team {team['id']}"
            )
            return []

        execution_ids = []
        current_message = message

        for iteration in range(max_iterations):
            logger.info(f"Generator-critic iteration {iteration + 1}/{max_iterations}")

            # Execute generator
            gen_eid, gen_output = cls._run_agent_and_get_output(
                team, generator_id, current_message, event, trigger_type, working_directory
            )
            if gen_eid:
                execution_ids.append(gen_eid)

            if not gen_output:
                logger.warning("Generator produced no output, stopping loop")
                break

            # Execute critic with generator's output
            critic_eid, critic_output = cls._run_agent_and_get_output(
                team, critic_id, gen_output, event, trigger_type, working_directory
            )
            if critic_eid:
                execution_ids.append(critic_eid)

            # Check if critic approved
            if critic_output and "APPROVED" in critic_output.upper():
                logger.info("Critic approved generator output, stopping loop")
                break

            # Use critic feedback as next generator input
            if critic_output:
                current_message = critic_output

        return execution_ids

    # ------------------------------------------------------------------
    # Hierarchical execution strategy
    # ------------------------------------------------------------------

    @classmethod
    def _execute_hierarchical(
        cls,
        team: dict,
        config: dict,
        message: str,
        event: dict,
        trigger_type: str,
        working_directory: str = None,
    ) -> List[str]:
        """Execute agents following a delegation tree depth-first.

        Config expects: {"lead": "agent-id-or-super-agent-id"}
        The lead is the root of a delegation tree defined by team_edges
        with edge_type='delegation'. Executes lead first, then delegates
        recursively, passing each parent's output to its children.
        """
        from ..database import get_team_edges

        lead_id = config.get("lead")
        if not lead_id:
            logger.warning(f"Hierarchical topology has no 'lead' config for team {team['id']}")
            return []

        team_id = team.get("id", "")
        members = team.get("members", [])

        # Build member lookup: map agent_id/super_agent_id -> member_id
        # and member_id -> agent_id/super_agent_id
        id_to_member_id = {}
        member_id_to_entity_id = {}
        for m in members:
            mid = m.get("id")
            aid = m.get("agent_id")
            said = m.get("super_agent_id")
            if aid:
                id_to_member_id[aid] = mid
                member_id_to_entity_id[mid] = aid
            if said:
                id_to_member_id[said] = mid
                member_id_to_entity_id[mid] = said

        lead_member_id = id_to_member_id.get(lead_id)
        if lead_member_id is None:
            logger.warning(f"Hierarchical lead '{lead_id}' not found in team members for {team_id}")
            return []

        # Load delegation edges and build adjacency map (source_member_id -> [target_member_ids])
        edges = get_team_edges(team_id)
        adjacency: Dict[int, List[int]] = {}
        for edge in edges:
            if edge.get("edge_type") == "delegation":
                src = edge["source_member_id"]
                tgt = edge["target_member_id"]
                adjacency.setdefault(src, []).append(tgt)

        # Depth-first recursive execution
        return cls._execute_hierarchical_recursive(
            team,
            adjacency,
            member_id_to_entity_id,
            lead_member_id,
            message,
            event,
            trigger_type,
            working_directory,
        )

    @classmethod
    def _execute_hierarchical_recursive(
        cls,
        team: dict,
        adjacency: Dict[int, List[int]],
        member_id_to_entity_id: Dict[int, str],
        current_member_id: int,
        message: str,
        event: dict,
        trigger_type: str,
        working_directory: str = None,
    ) -> List[str]:
        """Recursively execute agent for current_member_id, then delegates."""
        entity_id = member_id_to_entity_id.get(current_member_id)
        if not entity_id:
            logger.warning(f"No entity ID for member {current_member_id}")
            return []

        logger.info(f"Hierarchical: executing agent {entity_id} (member {current_member_id})")

        # Check if this is a super_agent and handle accordingly
        agent_id = entity_id
        execution_id, output = cls._run_agent_and_get_output(
            team, agent_id, message, event, trigger_type, working_directory
        )

        execution_ids = []
        if execution_id:
            execution_ids.append(execution_id)

        # Recurse into delegates with the current agent's output
        child_message = output if output else message
        children = adjacency.get(current_member_id, [])
        for child_member_id in children:
            child_ids = cls._execute_hierarchical_recursive(
                team,
                adjacency,
                member_id_to_entity_id,
                child_member_id,
                child_message,
                event,
                trigger_type,
                working_directory,
            )
            execution_ids.extend(child_ids)

        return execution_ids

    # ------------------------------------------------------------------
    # Human-in-loop execution strategy
    # ------------------------------------------------------------------

    @classmethod
    def _execute_human_in_loop(
        cls,
        team: dict,
        config: dict,
        message: str,
        event: dict,
        trigger_type: str,
        working_directory: str = None,
    ) -> List[str]:
        """Execute agents sequentially with approval gates at designated nodes.

        Config expects: {"order": ["agent-id-1", ...], "approval_nodes": ["agent-id-2"]}
        When an approval node is reached, execution pauses until approve_execution()
        is called or the timeout expires (default 30 minutes).
        """
        order = config.get("order", [])
        approval_nodes = set(config.get("approval_nodes", []))
        approval_timeout = config.get("approval_timeout", 1800)

        if not order:
            logger.warning(f"Human-in-loop topology has no 'order' config for team {team['id']}")
            return []

        # Find the team_exec_id for this execution so we can update status
        team_exec_id = cls._find_exec_id_for_team(team.get("id", ""))

        execution_ids = []
        current_message = message

        for agent_id in order:
            # Check if this is an approval node
            if agent_id in approval_nodes:
                logger.info(f"Human-in-loop: approval gate reached for agent {agent_id}")
                approval_event = threading.Event()

                if team_exec_id:
                    with cls._lock:
                        exec_entry = cls._executions.get(team_exec_id)
                        if exec_entry:
                            exec_entry["status"] = "pending_approval"
                            exec_entry["awaiting_approval"] = agent_id
                            exec_entry["approval_timeout"] = approval_timeout
                            exec_entry["_approval_event"] = approval_event

                # Wait for approval or timeout
                approved = approval_event.wait(timeout=approval_timeout)

                if not approved:
                    logger.warning(
                        f"Human-in-loop: approval timeout for agent {agent_id} "
                        f"after {approval_timeout}s"
                    )
                    if team_exec_id:
                        with cls._lock:
                            exec_entry = cls._executions.get(team_exec_id)
                            if exec_entry:
                                exec_entry["status"] = "approval_timeout"
                                exec_entry.pop("_approval_event", None)
                    return execution_ids

                # Approved -- clean up approval state and continue
                if team_exec_id:
                    with cls._lock:
                        exec_entry = cls._executions.get(team_exec_id)
                        if exec_entry:
                            exec_entry["status"] = "running"
                            exec_entry.pop("awaiting_approval", None)
                            exec_entry.pop("_approval_event", None)

            logger.info(
                f"Human-in-loop: executing agent {agent_id} "
                f"with message length={len(current_message)}"
            )
            execution_id, output = cls._run_agent_and_get_output(
                team, agent_id, current_message, event, trigger_type, working_directory
            )
            if execution_id:
                execution_ids.append(execution_id)
            if output:
                current_message = output

        return execution_ids

    @classmethod
    def _find_exec_id_for_team(cls, team_id: str) -> Optional[str]:
        """Find the current running team_exec_id for a team_id."""
        with cls._lock:
            for exec_id, entry in cls._executions.items():
                if entry.get("team_id") == team_id and entry.get("status") == "running":
                    return exec_id
        return None

    @classmethod
    def approve_execution(cls, team_exec_id: str) -> bool:
        """Approve a pending human-in-loop execution.

        Returns True if the execution was in pending_approval state and was
        successfully approved, False otherwise.
        """
        with cls._lock:
            exec_entry = cls._executions.get(team_exec_id)
            if not exec_entry:
                return False
            if exec_entry.get("status") != "pending_approval":
                return False
            approval_event = exec_entry.get("_approval_event")
            if not approval_event:
                return False

        # Set the event outside the lock to avoid potential deadlock
        approval_event.set()
        return True

    # ------------------------------------------------------------------
    # Composite execution strategy
    # ------------------------------------------------------------------

    @classmethod
    def _execute_composite(
        cls,
        team: dict,
        config: dict,
        message: str,
        event: dict,
        trigger_type: str,
        working_directory: str = None,
    ) -> List[str]:
        """Execute sub-groups sequentially, each using its own topology strategy.

        Config expects: {"sub_groups": [{"topology": "parallel", "config": {...}, "members": [...]}, ...]}
        Each sub-group is dispatched to the appropriate strategy.
        No composite-within-composite allowed (max nesting depth 2).
        """
        sub_groups = config.get("sub_groups", [])
        if not sub_groups:
            logger.warning(f"Composite topology has no 'sub_groups' config for team {team['id']}")
            return []

        # Strategy dispatch for sub-groups (exclude composite to prevent recursion)
        sub_strategy_map = {
            "sequential": cls._execute_sequential,
            "parallel": cls._execute_parallel,
            "coordinator": cls._execute_coordinator,
            "generator_critic": cls._execute_generator_critic,
            "hierarchical": cls._execute_hierarchical,
            "human_in_loop": cls._execute_human_in_loop,
        }

        execution_ids = []
        current_message = message

        for i, sub_group in enumerate(sub_groups):
            sub_topology = sub_group.get("topology")
            sub_config = sub_group.get("config", {})

            if sub_topology == "composite":
                logger.error(
                    f"Composite nesting not allowed in sub_group {i} for team {team['id']}"
                )
                continue

            strategy = sub_strategy_map.get(sub_topology)
            if not strategy:
                logger.error(
                    f"Unknown sub_group topology '{sub_topology}' in sub_group {i} "
                    f"for team {team['id']}"
                )
                continue

            logger.info(f"Composite: executing sub_group {i} with topology={sub_topology}")
            sub_exec_ids = strategy(
                team, sub_config, current_message, event, trigger_type, working_directory
            )
            execution_ids.extend(sub_exec_ids or [])

            # Pass last sub-group's output to next sub-group
            # Get output from the last execution in this sub-group
            if sub_exec_ids:
                from .execution_log_service import ExecutionLogService

                last_output = ExecutionLogService.get_stdout_log(sub_exec_ids[-1])
                if last_output:
                    current_message = last_output

        return execution_ids
