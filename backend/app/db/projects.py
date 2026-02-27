"""Project CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_project_id

logger = logging.getLogger(__name__)


# =============================================================================
# Project CRUD
# =============================================================================


def add_project(
    name: str,
    description: str = None,
    status: str = "active",
    product_id: str = None,
    github_repo: str = None,
    owner_team_id: str = None,
    local_path: str = None,
    github_host: str = None,
) -> Optional[str]:
    """Add a new project. Returns project_id on success, None on failure."""
    with get_connection() as conn:
        try:
            project_id = _get_unique_project_id(conn)
            conn.execute(
                """
                INSERT INTO projects (id, name, description, status, product_id, github_repo, owner_team_id, local_path, github_host)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    project_id,
                    name,
                    description,
                    status,
                    product_id,
                    github_repo,
                    owner_team_id,
                    local_path,
                    github_host or "github.com",
                ),
            )
            conn.commit()
            return project_id
        except sqlite3.IntegrityError:
            return None


def update_project(
    project_id: str,
    name: str = None,
    description: str = None,
    status: str = None,
    product_id: str = None,
    github_repo: str = None,
    owner_team_id: str = None,
    local_path: str = None,
    grd_sync_at: str = None,
    github_host: str = None,
    manager_super_agent_id: str = None,
    grd_init_status: str = None,
) -> bool:
    """Update project fields. Returns True on success."""
    updates = []
    values = []

    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if description is not None:
        updates.append("description = ?")
        values.append(description)
    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if product_id is not None:
        updates.append("product_id = ?")
        values.append(product_id if product_id else None)
    if github_repo is not None:
        updates.append("github_repo = ?")
        values.append(github_repo if github_repo else None)
    if owner_team_id is not None:
        updates.append("owner_team_id = ?")
        values.append(owner_team_id if owner_team_id else None)
    if local_path is not None:
        updates.append("local_path = ?")
        values.append(local_path if local_path else None)
    if grd_sync_at is not None:
        updates.append("grd_sync_at = ?")
        values.append(grd_sync_at)
    if github_host is not None:
        updates.append("github_host = ?")
        values.append(github_host if github_host else "github.com")
    if manager_super_agent_id is not None:
        updates.append("manager_super_agent_id = ?")
        values.append(manager_super_agent_id if manager_super_agent_id else None)
    if grd_init_status is not None:
        updates.append("grd_init_status = ?")
        values.append(grd_init_status)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(project_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_project(project_id: str) -> bool:
    """Delete a project. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_project(project_id: str) -> Optional[dict]:
    """Get a single project by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_projects(limit: Optional[int] = None, offset: int = 0) -> List[dict]:
    """Get all projects with team counts and owner team name, with optional pagination."""
    with get_connection() as conn:
        sql = """
            SELECT p.*, pd.name as product_name, t.name as owner_team_name, COUNT(pt.id) as team_count
            FROM projects p
            LEFT JOIN products pd ON p.product_id = pd.id
            LEFT JOIN teams t ON p.owner_team_id = t.id
            LEFT JOIN project_teams pt ON p.id = pt.project_id
            GROUP BY p.id
            ORDER BY p.name ASC
        """
        params: list = []
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def count_projects() -> int:
    """Count total number of projects."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM projects")
        return cursor.fetchone()[0]


def get_project_detail(project_id: str) -> Optional[dict]:
    """Get project with teams and owner team name."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT p.*, pd.name as product_name, t.name as owner_team_name
            FROM projects p
            LEFT JOIN products pd ON p.product_id = pd.id
            LEFT JOIN teams t ON p.owner_team_id = t.id
            WHERE p.id = ?
        """,
            (project_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        project = dict(row)
        cursor = conn.execute(
            """
            SELECT t.* FROM teams t
            JOIN project_teams pt ON t.id = pt.team_id
            WHERE pt.project_id = ?
            ORDER BY t.name ASC
        """,
            (project_id,),
        )
        project["teams"] = [dict(r) for r in cursor.fetchall()]
        return project


# =============================================================================
# Project team assignment operations
# =============================================================================


def assign_team_to_project(project_id: str, team_id: str) -> bool:
    """Assign a team to a project. Returns True on success."""
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO project_teams (project_id, team_id)
                VALUES (?, ?)
            """,
                (project_id, team_id),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def unassign_team_from_project(project_id: str, team_id: str) -> bool:
    """Remove a team from a project. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM project_teams WHERE project_id = ? AND team_id = ?", (project_id, team_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def get_project_teams(project_id: str) -> List[dict]:
    """Get all teams assigned to a project."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT t.* FROM teams t
            JOIN project_teams pt ON t.id = pt.team_id
            WHERE pt.project_id = ?
            ORDER BY t.name ASC
        """,
            (project_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# Project skill operations
# =============================================================================


def add_project_skill(
    project_id: str,
    skill_name: str,
    skill_path: Optional[str] = None,
    source: str = "manual",
) -> Optional[int]:
    """Add a skill to a project."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO project_skills (project_id, skill_name, skill_path, source)
                VALUES (?, ?, ?, ?)
            """,
                (project_id, skill_name, skill_path, source),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Database error in add_project_skill: {e}")
            return None


def delete_project_skill(project_id: str, skill_name: str) -> bool:
    """Remove a skill from a project."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM project_skills WHERE project_id = ? AND skill_name = ?",
            (project_id, skill_name),
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_project_skill_by_id(skill_id: int) -> bool:
    """Remove a project skill by ID."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM project_skills WHERE id = ?", (skill_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_project_skills(project_id: str) -> List[dict]:
    """Get all skills for a project."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM project_skills WHERE project_id = ? ORDER BY skill_name ASC",
            (project_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def clear_project_skills(project_id: str, source: Optional[str] = None) -> int:
    """Clear skills from a project, optionally by source."""
    with get_connection() as conn:
        if source:
            cursor = conn.execute(
                "DELETE FROM project_skills WHERE project_id = ? AND source = ?",
                (project_id, source),
            )
        else:
            cursor = conn.execute(
                "DELETE FROM project_skills WHERE project_id = ?",
                (project_id,),
            )
        conn.commit()
        return cursor.rowcount


# =============================================================================
# Project installation operations
# =============================================================================


def add_project_installation(
    project_id: str, component_type: str, component_id: str
) -> Optional[int]:
    """Add a project installation record. Returns id or None if already exists."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO project_installations
                (project_id, component_type, component_id)
                VALUES (?, ?, ?)
            """,
                (project_id, component_type, str(component_id)),
            )
            conn.commit()
            return cursor.lastrowid if cursor.rowcount > 0 else None
        except sqlite3.Error as e:
            logger.error(f"Database error in add_project_installation: {e}")
            return None


def delete_project_installation(project_id: str, component_type: str, component_id: str) -> bool:
    """Delete a project installation record. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM project_installations WHERE project_id = ? AND component_type = ? AND component_id = ?",
            (project_id, component_type, str(component_id)),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_project_installations(project_id: str, component_type: Optional[str] = None) -> List[dict]:
    """Get all installations for a project, optionally filtered by component type."""
    with get_connection() as conn:
        if component_type:
            cursor = conn.execute(
                "SELECT * FROM project_installations WHERE project_id = ? AND component_type = ? ORDER BY installed_at DESC",
                (project_id, component_type),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM project_installations WHERE project_id = ? ORDER BY installed_at DESC",
                (project_id,),
            )
        return [dict(row) for row in cursor.fetchall()]


def get_project_installation(
    project_id: str, component_type: str, component_id: str
) -> Optional[dict]:
    """Get a single project installation record."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM project_installations WHERE project_id = ? AND component_type = ? AND component_id = ?",
            (project_id, component_type, str(component_id)),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


# =============================================================================
# Project team edge operations (org chart)
# =============================================================================


def add_project_team_edge(
    project_id: str,
    source_team_id: str,
    target_team_id: str,
    edge_type: str = "dependency",
    label: Optional[str] = None,
    weight: int = 1,
) -> Optional[int]:
    """Add a directed edge between two teams in a project org chart."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO project_team_edges
                (project_id, source_team_id, target_team_id, edge_type, label, weight)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (project_id, source_team_id, target_team_id, edge_type, label, weight),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_project_team_edges(project_id: str) -> List[dict]:
    """Get all team edges for a project."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM project_team_edges WHERE project_id = ? ORDER BY id ASC",
            (project_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_project_team_edge(edge_id: int) -> bool:
    """Delete a project team edge by ID."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM project_team_edges WHERE id = ?", (edge_id,))
        conn.commit()
        return cursor.rowcount > 0


def delete_project_team_edges_by_project(project_id: str) -> int:
    """Delete all team edges for a project."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM project_team_edges WHERE project_id = ?", (project_id,))
        conn.commit()
        return cursor.rowcount


def update_project_clone_status(
    project_id: str,
    clone_status: str,
    clone_error: Optional[str] = None,
    last_synced_at: Optional[str] = None,
) -> bool:
    """Update clone-related fields for a project."""
    updates = ["clone_status = ?", "updated_at = CURRENT_TIMESTAMP"]
    values: list = [clone_status]
    updates.append("clone_error = ?")
    values.append(clone_error)
    if last_synced_at is not None:
        updates.append("last_synced_at = ?")
        values.append(last_synced_at)
    values.append(project_id)
    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def get_projects_with_github_repo(clone_status: str = "cloned") -> List[dict]:
    """Return all projects that have github_repo set and matching clone_status."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM projects WHERE github_repo IS NOT NULL AND github_repo != '' AND clone_status = ?",
            (clone_status,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_project_team_topology_config(project_id: str, config: str) -> bool:
    """Update the team_topology_config JSON for a project."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE projects SET team_topology_config = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (config, project_id),
        )
        conn.commit()
        return cursor.rowcount > 0
