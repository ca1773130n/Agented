"""Team CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_team_id

logger = logging.getLogger(__name__)

# --- Constants ---

VALID_ENTITY_TYPES = ("skill", "command", "hook", "rule")


# =============================================================================
# Team CRUD
# =============================================================================


def add_team(
    name: str,
    description: str = None,
    color: str = "#00d4ff",
    leader_id: str = None,
    source: str = "ui_created",
    topology: str = None,
    topology_config: str = None,
    trigger_source: str = None,
    trigger_config: str = None,
) -> Optional[str]:
    """Add a new team. Returns team_id on success, None on failure.

    Args:
        name: Team name
        description: Team description
        color: Team color (hex)
        leader_id: Leader ID (optional)
        source: Source of team creation ('ui_created' or 'github_sync')
        topology: Execution topology pattern
        topology_config: JSON config for the topology
        trigger_source: Trigger type (webhook, github, manual, scheduled)
        trigger_config: JSON config for trigger matching
    """
    with get_connection() as conn:
        try:
            team_id = _get_unique_team_id(conn)
            conn.execute(
                """
                INSERT INTO teams (id, name, description, color, leader_id, source,
                                   topology, topology_config, trigger_source, trigger_config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    team_id,
                    name,
                    description,
                    color,
                    leader_id,
                    source,
                    topology,
                    topology_config,
                    trigger_source,
                    trigger_config,
                ),
            )
            conn.commit()
            return team_id
        except sqlite3.IntegrityError:
            return None


def update_team(
    team_id: str,
    name: str = None,
    description: str = None,
    color: str = None,
    leader_id: str = None,
    topology: str = None,
    topology_config: str = None,
    trigger_source: str = None,
    trigger_config: str = None,
    enabled: int = None,
) -> bool:
    """Update team fields. Returns True on success."""
    updates = []
    values = []

    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if description is not None:
        updates.append("description = ?")
        values.append(description)
    if color is not None:
        updates.append("color = ?")
        values.append(color)
    if leader_id is not None:
        updates.append("leader_id = ?")
        values.append(leader_id)
    if topology is not None:
        updates.append("topology = ?")
        values.append(topology)
    if topology_config is not None:
        updates.append("topology_config = ?")
        values.append(topology_config)
    if trigger_source is not None:
        updates.append("trigger_source = ?")
        values.append(trigger_source)
    if trigger_config is not None:
        updates.append("trigger_config = ?")
        values.append(trigger_config)
    if enabled is not None:
        updates.append("enabled = ?")
        values.append(enabled)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(team_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE teams SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_team(team_id: str) -> bool:
    """Delete a team. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_team(team_id: str) -> Optional[dict]:
    """Get a single team by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_team_by_name(name: str) -> Optional[dict]:
    """Get a team by name."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM teams WHERE name = ?", (name,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_teams(limit: Optional[int] = None, offset: int = 0) -> List[dict]:
    """Get all teams with member counts and leader info, with optional pagination."""
    with get_connection() as conn:
        sql = """
            SELECT t.*, COUNT(tm.id) as member_count, a.name as leader_name
            FROM teams t
            LEFT JOIN team_members tm ON t.id = tm.team_id
            LEFT JOIN agents a ON t.leader_id = a.id
            GROUP BY t.id
            ORDER BY t.name ASC
        """
        params: list = []
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def count_teams() -> int:
    """Count total number of teams."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM teams")
        return cursor.fetchone()[0]


def get_team_detail(team_id: str) -> Optional[dict]:
    """Get team with members and leader info."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT t.*, a.name as leader_name
            FROM teams t
            LEFT JOIN agents a ON t.leader_id = a.id
            WHERE t.id = ?
            """,
            (team_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        team = dict(row)
        # Get members with agent and super_agent info
        # Use a fallback query if super_agent_id column hasn't been migrated yet
        col_names = {c[1] for c in conn.execute("PRAGMA table_info(team_members)").fetchall()}
        has_sa = "super_agent_id" in col_names
        if has_sa:
            cursor = conn.execute(
                """
                SELECT tm.*,
                       ag.name as agent_name,
                       sa.name as super_agent_name,
                       CASE
                           WHEN tm.agent_id IS NOT NULL THEN 'agent'
                           WHEN tm.super_agent_id IS NOT NULL THEN 'super_agent'
                           ELSE 'manual'
                       END as member_type
                FROM team_members tm
                LEFT JOIN agents ag ON tm.agent_id = ag.id
                LEFT JOIN super_agents sa ON tm.super_agent_id = sa.id
                WHERE tm.team_id = ?
                ORDER BY tm.name ASC
                """,
                (team_id,),
            )
        else:
            cursor = conn.execute(
                """
                SELECT tm.*,
                       ag.name as agent_name,
                       NULL as super_agent_name,
                       CASE
                           WHEN tm.agent_id IS NOT NULL THEN 'agent'
                           ELSE 'manual'
                       END as member_type
                FROM team_members tm
                LEFT JOIN agents ag ON tm.agent_id = ag.id
                WHERE tm.team_id = ?
                ORDER BY tm.name ASC
                """,
                (team_id,),
            )
        team["members"] = [dict(r) for r in cursor.fetchall()]
        return team


# =============================================================================
# Team member operations
# =============================================================================


def add_team_member(
    team_id: str,
    name: str = None,
    email: str = None,
    role: str = "member",
    layer: str = "backend",
    description: str = None,
    agent_id: str = None,
    super_agent_id: str = None,
    tier: str = None,
) -> Optional[int]:
    """Add a member to a team. Returns member id on success.

    If agent_id is provided, the name will be fetched from the agent record.
    If super_agent_id is provided, the name will be fetched from the super_agent record.
    XOR validation: cannot have both agent_id and super_agent_id set.
    """
    # XOR validation: at most one of agent_id / super_agent_id
    if agent_id and super_agent_id:
        return None

    # Must have at least one identifier
    if not agent_id and not super_agent_id and not name:
        return None

    with get_connection() as conn:
        try:
            # If agent_id is provided, get the agent name
            if agent_id and not name:
                cursor = conn.execute("SELECT name FROM agents WHERE id = ?", (agent_id,))
                agent_row = cursor.fetchone()
                if agent_row:
                    name = agent_row["name"]
                else:
                    name = "Unknown Agent"

            # If super_agent_id is provided, get the super_agent name
            if super_agent_id and not name:
                cursor = conn.execute(
                    "SELECT name FROM super_agents WHERE id = ?", (super_agent_id,)
                )
                sa_row = cursor.fetchone()
                if sa_row:
                    name = sa_row["name"]
                else:
                    name = "Unknown SuperAgent"

            col_names = {c[1] for c in conn.execute("PRAGMA table_info(team_members)").fetchall()}
            columns = ["team_id", "name", "email", "role", "layer", "description", "agent_id"]
            values_list = [team_id, name, email, role, layer, description, agent_id]
            if "super_agent_id" in col_names:
                columns.append("super_agent_id")
                values_list.append(super_agent_id)
            if "tier" in col_names and tier is not None:
                columns.append("tier")
                values_list.append(tier)
            placeholders = ", ".join("?" for _ in columns)
            col_str = ", ".join(columns)
            cursor = conn.execute(
                f"INSERT INTO team_members ({col_str}) VALUES ({placeholders})",
                tuple(values_list),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def update_team_member(
    member_id: int,
    name: str = None,
    email: str = None,
    role: str = None,
    layer: str = None,
    description: str = None,
    tier: str = None,
) -> bool:
    """Update a team member. Returns True on success."""
    updates = []
    values = []

    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if email is not None:
        updates.append("email = ?")
        values.append(email)
    if role is not None:
        updates.append("role = ?")
        values.append(role)
    if layer is not None:
        updates.append("layer = ?")
        values.append(layer)
    if description is not None:
        updates.append("description = ?")
        values.append(description)
    if tier is not None:
        updates.append("tier = ?")
        values.append(tier)

    if not updates:
        return False

    values.append(member_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE team_members SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def remove_team_member(member_id: int) -> bool:
    """Remove a team member. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM team_members WHERE id = ?", (member_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_team_members(team_id: str) -> List[dict]:
    """Get all members of a team with agent and super_agent info."""
    with get_connection() as conn:
        col_names = {c[1] for c in conn.execute("PRAGMA table_info(team_members)").fetchall()}
        has_sa = "super_agent_id" in col_names
        if has_sa:
            cursor = conn.execute(
                """
                SELECT tm.*,
                       ag.name as agent_name,
                       sa.name as super_agent_name,
                       CASE
                           WHEN tm.agent_id IS NOT NULL THEN 'agent'
                           WHEN tm.super_agent_id IS NOT NULL THEN 'super_agent'
                           ELSE 'manual'
                       END as member_type
                FROM team_members tm
                LEFT JOIN agents ag ON tm.agent_id = ag.id
                LEFT JOIN super_agents sa ON tm.super_agent_id = sa.id
                WHERE tm.team_id = ?
                ORDER BY tm.name ASC
                """,
                (team_id,),
            )
        else:
            cursor = conn.execute(
                """
                SELECT tm.*,
                       ag.name as agent_name,
                       NULL as super_agent_name,
                       CASE
                           WHEN tm.agent_id IS NOT NULL THEN 'agent'
                           ELSE 'manual'
                       END as member_type
                FROM team_members tm
                LEFT JOIN agents ag ON tm.agent_id = ag.id
                WHERE tm.team_id = ?
                ORDER BY tm.name ASC
                """,
                (team_id,),
            )
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# Team agent assignment operations
# =============================================================================


def add_team_agent_assignment(
    team_id: str,
    agent_id: str,
    entity_type: str,
    entity_id: str,
    entity_name: str = None,
) -> Optional[int]:
    """Add an entity assignment for an agent within a team.

    Uses INSERT OR IGNORE for the UNIQUE constraint.
    Returns row id on success, None if invalid entity_type or duplicate.
    """
    if entity_type not in VALID_ENTITY_TYPES:
        return None

    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO team_agent_assignments
                    (team_id, agent_id, entity_type, entity_id, entity_name)
                VALUES (?, ?, ?, ?, ?)
                """,
                (team_id, agent_id, entity_type, entity_id, entity_name),
            )
            conn.commit()
            return cursor.lastrowid if cursor.rowcount > 0 else None
        except sqlite3.IntegrityError:
            return None


def get_team_agent_assignments(team_id: str, agent_id: str = None) -> List[dict]:
    """Get assignments for a team, optionally filtered by agent_id."""
    with get_connection() as conn:
        if agent_id:
            cursor = conn.execute(
                "SELECT * FROM team_agent_assignments WHERE team_id = ? AND agent_id = ? ORDER BY entity_type, entity_name",
                (team_id, agent_id),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM team_agent_assignments WHERE team_id = ? ORDER BY agent_id, entity_type, entity_name",
                (team_id,),
            )
        return [dict(row) for row in cursor.fetchall()]


def delete_team_agent_assignment(assignment_id: int) -> bool:
    """Delete a single assignment by id. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM team_agent_assignments WHERE id = ?", (assignment_id,))
        conn.commit()
        return cursor.rowcount > 0


def delete_team_agent_assignments_bulk(
    team_id: str, agent_id: str = None, entity_type: str = None
) -> int:
    """Bulk delete assignments with optional filters. Returns count deleted."""
    conditions = ["team_id = ?"]
    values = [team_id]

    if agent_id is not None:
        conditions.append("agent_id = ?")
        values.append(agent_id)
    if entity_type is not None:
        conditions.append("entity_type = ?")
        values.append(entity_type)

    with get_connection() as conn:
        cursor = conn.execute(
            f"DELETE FROM team_agent_assignments WHERE {' AND '.join(conditions)}",
            values,
        )
        conn.commit()
        return cursor.rowcount


def get_teams_by_trigger_source(trigger_source: str) -> List[dict]:
    """Get all enabled teams with a specific trigger source."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM teams WHERE trigger_source = ? AND enabled = 1",
            (trigger_source,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_webhook_teams() -> List[dict]:
    """Get all enabled teams with webhook trigger source."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM teams WHERE trigger_source = 'webhook' AND enabled = 1"
        )
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# Team edge operations (directed graph relationships)
# =============================================================================

VALID_EDGE_TYPES = ("delegation", "reporting", "messaging", "approval_gate")


def add_team_edge(
    team_id: str,
    source_member_id: int,
    target_member_id: int,
    edge_type: str = "delegation",
    label: str = None,
    weight: int = 1,
) -> Optional[int]:
    """Add a directed edge between two team members. Returns edge id on success.

    Valid edge_types: delegation, reporting, messaging, approval_gate.
    Self-loops are rejected by the database CHECK constraint.
    Duplicate edges (same team, source, target, type) are rejected by unique index.
    """
    if edge_type not in VALID_EDGE_TYPES:
        return None

    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO team_edges
                    (team_id, source_member_id, target_member_id, edge_type, label, weight)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (team_id, source_member_id, target_member_id, edge_type, label, weight),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_team_edges(team_id: str) -> List[dict]:
    """Get all edges for a team ordered by source_member_id."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT * FROM team_edges
            WHERE team_id = ?
            ORDER BY source_member_id ASC
            """,
            (team_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_team_edge(edge_id: int) -> bool:
    """Delete a single edge by id. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM team_edges WHERE id = ?", (edge_id,))
        conn.commit()
        return cursor.rowcount > 0


def delete_team_edges_by_team(team_id: str) -> int:
    """Bulk delete all edges for a team. Returns count deleted."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM team_edges WHERE team_id = ?", (team_id,))
        conn.commit()
        return cursor.rowcount


def get_team_hierarchy(team_id: str, root_member_id: int) -> List[dict]:
    """Get all descendants of a member via delegation edges using recursive CTE.

    Returns list of dicts with member info and depth, max depth 10.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            WITH RECURSIVE hierarchy AS (
                SELECT te.target_member_id as member_id, 1 as depth
                FROM team_edges te
                WHERE te.team_id = ?
                  AND te.source_member_id = ?
                  AND te.edge_type = 'delegation'

                UNION ALL

                SELECT te.target_member_id, h.depth + 1
                FROM team_edges te
                JOIN hierarchy h ON te.source_member_id = h.member_id
                WHERE te.team_id = ?
                  AND te.edge_type = 'delegation'
                  AND h.depth < 10
            )
            SELECT tm.id, tm.name, tm.agent_id, h.depth
            FROM hierarchy h
            JOIN team_members tm ON h.member_id = tm.id
            ORDER BY h.depth ASC, tm.name ASC
            """,
            (team_id, root_member_id, team_id),
        )
        return [dict(row) for row in cursor.fetchall()]
