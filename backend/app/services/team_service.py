"""Team service for topology validation and membership checking."""

import json

from ..database import get_team_members
from ..models.team import VALID_TOPOLOGIES


class TeamService:
    """Service for team business logic that doesn't belong in route handlers."""

    @staticmethod
    def validate_topology_config(team_id: str, topology: str, config) -> str | None:
        """Validate topology configuration. Returns error message or None."""
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                return "topology_config must be valid JSON"

        if not isinstance(config, dict):
            return "topology_config must be a JSON object"

        members = get_team_members(team_id)
        # Include both agent_id and super_agent_id in member lookup set
        member_agent_ids = set()
        for m in members:
            if m.get("agent_id"):
                member_agent_ids.add(m["agent_id"])
            if m.get("super_agent_id"):
                member_agent_ids.add(m["super_agent_id"])

        if topology == "sequential":
            order = config.get("order")
            if not isinstance(order, list) or len(order) == 0:
                return "sequential topology requires 'order' array of agent_ids"
            for aid in order:
                if aid not in member_agent_ids:
                    return f"Agent {aid} in 'order' is not a team member"

        elif topology == "parallel":
            agents = config.get("agents")
            if not isinstance(agents, list) or len(agents) == 0:
                return "parallel topology requires 'agents' array of agent_ids"
            for aid in agents:
                if aid not in member_agent_ids:
                    return f"Agent {aid} in 'agents' is not a team member"

        elif topology == "coordinator":
            coordinator = config.get("coordinator")
            workers = config.get("workers")
            if not coordinator or not isinstance(workers, list) or len(workers) == 0:
                return "coordinator topology requires 'coordinator' string and 'workers' array"
            if coordinator in workers:
                return "coordinator must differ from all workers"
            all_agents = [coordinator] + workers
            for aid in all_agents:
                if aid not in member_agent_ids:
                    return f"Agent {aid} is not a team member"

        elif topology == "generator_critic":
            generator = config.get("generator")
            critic = config.get("critic")
            if not generator or not critic:
                return "generator_critic topology requires 'generator' and 'critic' strings"
            if generator == critic:
                return "generator must differ from critic"
            for aid in [generator, critic]:
                if aid not in member_agent_ids:
                    return f"Agent {aid} is not a team member"

        elif topology == "hierarchical":
            lead = config.get("lead")
            if not lead or not isinstance(lead, str):
                return "hierarchical topology requires 'lead' string (agent_id or super_agent_id)"
            if lead not in member_agent_ids:
                return f"Lead '{lead}' is not a team member"
            # Verify delegation edges form a tree (no cycles) and lead has outgoing edges
            from ..database import get_team_edges

            edges = get_team_edges(team_id)
            delegation_edges = [e for e in edges if e.get("edge_type") == "delegation"]
            # Build adjacency for cycle detection
            adjacency: dict[int, list[int]] = {}
            for e in delegation_edges:
                src = e["source_member_id"]
                tgt = e["target_member_id"]
                adjacency.setdefault(src, []).append(tgt)
            # Find lead's member_id
            lead_member_id = None
            for m in members:
                if m.get("agent_id") == lead or m.get("super_agent_id") == lead:
                    lead_member_id = m.get("id")
                    break
            if lead_member_id is not None and lead_member_id not in adjacency:
                return "Lead must have at least one outgoing delegation edge"
            # DFS cycle detection
            if _has_cycle(adjacency):
                return "Delegation edges contain a cycle"

        elif topology == "human_in_loop":
            order = config.get("order")
            if not isinstance(order, list) or len(order) == 0:
                return "human_in_loop topology requires 'order' array of agent_ids"
            approval_nodes = config.get("approval_nodes")
            if not isinstance(approval_nodes, list) or len(approval_nodes) == 0:
                return "human_in_loop topology requires non-empty 'approval_nodes' array"
            for aid in order:
                if aid not in member_agent_ids:
                    return f"Agent {aid} in 'order' is not a team member"
            for aid in approval_nodes:
                if aid not in order:
                    return f"Approval node '{aid}' is not in the 'order' list"

        elif topology == "composite":
            sub_groups = config.get("sub_groups")
            if not isinstance(sub_groups, list) or len(sub_groups) == 0:
                return "composite topology requires 'sub_groups' array"
            for i, sg in enumerate(sub_groups):
                if not isinstance(sg, dict):
                    return f"sub_group {i} must be a JSON object"
                sg_topology = sg.get("topology")
                if not sg_topology or not isinstance(sg_topology, str):
                    return f"sub_group {i} requires 'topology' string"
                if sg_topology == "composite":
                    return f"sub_group {i} cannot have topology 'composite' (max nesting depth 2)"
                if sg_topology not in VALID_TOPOLOGIES:
                    return f"sub_group {i} has invalid topology '{sg_topology}'"
                sg_config = sg.get("config")
                if not isinstance(sg_config, dict):
                    return f"sub_group {i} requires 'config' dict"

        return None

    @staticmethod
    def is_agent_team_member(team_id: str, agent_id: str) -> bool:
        """Check if an agent (or super_agent) is a member of the given team."""
        members = get_team_members(team_id)
        return any(
            m.get("agent_id") == agent_id or m.get("super_agent_id") == agent_id for m in members
        )


def _has_cycle(adjacency: dict[int, list[int]]) -> bool:
    """DFS-based cycle detection on a directed graph adjacency map.

    Returns True if any cycle exists in the graph.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[int, int] = {}

    # Collect all nodes
    all_nodes = set(adjacency.keys())
    for targets in adjacency.values():
        all_nodes.update(targets)

    for node in all_nodes:
        color.setdefault(node, WHITE)

    def dfs(u: int) -> bool:
        color[u] = GRAY
        for v in adjacency.get(u, []):
            if color.get(v, WHITE) == GRAY:
                return True  # Back edge = cycle
            if color.get(v, WHITE) == WHITE and dfs(v):
                return True
        color[u] = BLACK
        return False

    for node in all_nodes:
        if color.get(node, WHITE) == WHITE:
            if dfs(node):
                return True
    return False
