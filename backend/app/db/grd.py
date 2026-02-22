"""GRD project management CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import (
    _get_unique_milestone_id,
    _get_unique_phase_id,
    _get_unique_plan_id,
    _get_unique_project_session_id,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Milestone CRUD
# =============================================================================


def add_milestone(
    project_id: str,
    version: str,
    title: str,
    description: str = None,
    status: str = "planning",
    requirements_json: str = None,
    roadmap_json: str = None,
) -> Optional[str]:
    """Add a new milestone. Returns milestone_id on success, None on failure."""
    with get_connection() as conn:
        try:
            milestone_id = _get_unique_milestone_id(conn)
            conn.execute(
                """
                INSERT INTO milestones
                (id, project_id, version, title, description, status, requirements_json, roadmap_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    milestone_id,
                    project_id,
                    version,
                    title,
                    description,
                    status,
                    requirements_json,
                    roadmap_json,
                ),
            )
            conn.commit()
            return milestone_id
        except sqlite3.IntegrityError:
            return None


def get_milestone(milestone_id: str) -> Optional[dict]:
    """Get a single milestone by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM milestones WHERE id = ?", (milestone_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_milestones_by_project(project_id: str) -> List[dict]:
    """Get all milestones for a project."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM milestones WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_milestone(milestone_id: str, **kwargs) -> bool:
    """Update milestone fields. Returns True on success.

    Supported kwargs: version, title, description, status, requirements_json, roadmap_json.
    """
    allowed = {"version", "title", "description", "status", "requirements_json", "roadmap_json"}
    updates = []
    values = []

    for key, value in kwargs.items():
        if key in allowed and value is not None:
            updates.append(f"{key} = ?")
            values.append(value)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(milestone_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE milestones SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_milestone(milestone_id: str) -> bool:
    """Delete a milestone. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM milestones WHERE id = ?", (milestone_id,))
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Project Phase CRUD
# =============================================================================


def add_project_phase(
    milestone_id: str,
    phase_number: int,
    name: str,
    description: str = None,
    goal: str = None,
    verification_level: str = "sanity",
    success_criteria: str = None,
    dependencies: str = None,
) -> Optional[str]:
    """Add a new project phase. Returns phase_id on success, None on failure."""
    with get_connection() as conn:
        try:
            phase_id = _get_unique_phase_id(conn)
            conn.execute(
                """
                INSERT INTO project_phases
                (id, milestone_id, phase_number, name, description, goal,
                 verification_level, success_criteria, dependencies)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    phase_id,
                    milestone_id,
                    phase_number,
                    name,
                    description,
                    goal,
                    verification_level,
                    success_criteria,
                    dependencies,
                ),
            )
            conn.commit()
            return phase_id
        except sqlite3.IntegrityError:
            return None


def get_project_phase(phase_id: str) -> Optional[dict]:
    """Get a single project phase by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM project_phases WHERE id = ?", (phase_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_phases_by_milestone(milestone_id: str) -> List[dict]:
    """Get all phases for a milestone, ordered by phase_number ASC."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM project_phases WHERE milestone_id = ? ORDER BY phase_number ASC",
            (milestone_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_project_phase(phase_id: str, **kwargs) -> bool:
    """Update project phase fields. Returns True on success.

    Supported kwargs: name, description, goal, status, verification_level,
    success_criteria, dependencies, started_at, completed_at.
    """
    allowed = {
        "name",
        "description",
        "goal",
        "status",
        "verification_level",
        "success_criteria",
        "dependencies",
        "started_at",
        "completed_at",
    }
    updates = []
    values = []

    for key, value in kwargs.items():
        if key in allowed and value is not None:
            updates.append(f"{key} = ?")
            values.append(value)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(phase_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE project_phases SET {', '.join(updates)} WHERE id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_project_phase(phase_id: str) -> bool:
    """Delete a project phase. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM project_phases WHERE id = ?", (phase_id,))
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Project Plan CRUD
# =============================================================================


def add_project_plan(
    phase_id: str,
    plan_number: int,
    title: str,
    description: str = None,
    tasks_json: str = None,
) -> Optional[str]:
    """Add a new project plan. Returns plan_id on success, None on failure."""
    with get_connection() as conn:
        try:
            plan_id = _get_unique_plan_id(conn)
            conn.execute(
                """
                INSERT INTO project_plans
                (id, phase_id, plan_number, title, description, tasks_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (plan_id, phase_id, plan_number, title, description, tasks_json),
            )
            conn.commit()
            return plan_id
        except sqlite3.IntegrityError:
            return None


def get_project_plan(plan_id: str) -> Optional[dict]:
    """Get a single project plan by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM project_plans WHERE id = ?", (plan_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_plans_by_phase(phase_id: str) -> List[dict]:
    """Get all plans for a phase, ordered by plan_number ASC."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM project_plans WHERE phase_id = ? ORDER BY plan_number ASC",
            (phase_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_project_plan(plan_id: str, **kwargs) -> bool:
    """Update project plan fields. Returns True on success.

    Supported kwargs: title, description, status, tasks_json, started_at, completed_at.
    """
    allowed = {"title", "description", "status", "tasks_json", "started_at", "completed_at"}
    updates = []
    values = []

    for key, value in kwargs.items():
        if key in allowed and value is not None:
            updates.append(f"{key} = ?")
            values.append(value)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(plan_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE project_plans SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_project_plan(plan_id: str) -> bool:
    """Delete a project plan. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM project_plans WHERE id = ?", (plan_id,))
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Project Session CRUD
# =============================================================================


def add_project_session(
    project_id: str,
    phase_id: str = None,
    plan_id: str = None,
    agent_id: str = None,
    pid: int = None,
    pgid: int = None,
    worktree_path: str = None,
    execution_type: str = None,
    execution_mode: str = None,
    idle_timeout_seconds: int = None,
    max_lifetime_seconds: int = None,
    last_activity_at: str = None,
) -> Optional[str]:
    """Add a new project session. Returns session_id on success, None on failure."""
    with get_connection() as conn:
        try:
            session_id = _get_unique_project_session_id(conn)
            # Build dynamic column/value lists for optional new fields
            columns = ["id", "project_id", "phase_id", "plan_id", "agent_id"]
            values = [session_id, project_id, phase_id, plan_id, agent_id]
            optional_fields = {
                "pid": pid,
                "pgid": pgid,
                "worktree_path": worktree_path,
                "execution_type": execution_type,
                "execution_mode": execution_mode,
                "idle_timeout_seconds": idle_timeout_seconds,
                "max_lifetime_seconds": max_lifetime_seconds,
                "last_activity_at": last_activity_at,
            }
            for col, val in optional_fields.items():
                if val is not None:
                    columns.append(col)
                    values.append(val)
            placeholders = ", ".join(["?"] * len(columns))
            col_str = ", ".join(columns)
            conn.execute(
                f"INSERT INTO project_sessions ({col_str}) VALUES ({placeholders})",
                values,
            )
            conn.commit()
            return session_id
        except sqlite3.IntegrityError:
            return None


def get_project_session(session_id: str) -> Optional[dict]:
    """Get a single project session by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM project_sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_sessions_by_project(project_id: str) -> List[dict]:
    """Get all sessions for a project, ordered by started_at DESC."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM project_sessions WHERE project_id = ? ORDER BY started_at DESC",
            (project_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_project_session(session_id: str, **kwargs) -> bool:
    """Update project session fields. Returns True on success.

    Supported kwargs: status, summary, log_json, ended_at, pid, pgid,
    worktree_path, execution_type, execution_mode, idle_timeout_seconds,
    max_lifetime_seconds, last_activity_at.
    """
    allowed = {
        "status",
        "summary",
        "log_json",
        "ended_at",
        "pid",
        "pgid",
        "worktree_path",
        "execution_type",
        "execution_mode",
        "idle_timeout_seconds",
        "max_lifetime_seconds",
        "last_activity_at",
    }
    updates = []
    values = []

    for key, value in kwargs.items():
        if key in allowed and value is not None:
            updates.append(f"{key} = ?")
            values.append(value)

    if not updates:
        return False

    values.append(session_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE project_sessions SET {', '.join(updates)} WHERE id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_project_session(session_id: str) -> bool:
    """Delete a project session. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM project_sessions WHERE id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_active_sessions() -> List[dict]:
    """Get all project sessions with status='active'. Used for startup cleanup."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM project_sessions WHERE status = 'active' ORDER BY started_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]


def get_sessions_by_status(status: str) -> List[dict]:
    """Get all project sessions matching a given status. Used for monitoring."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM project_sessions WHERE status = ? ORDER BY started_at DESC",
            (status,),
        )
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# Project Sync State CRUD
# =============================================================================


def upsert_project_sync_state(
    project_id: str,
    file_path: str,
    content_hash: str,
    entity_type: str,
    entity_id: str = None,
) -> bool:
    """Insert or replace sync state for a project file.

    Uses INSERT OR REPLACE on the (project_id, file_path) UNIQUE constraint.
    Returns True on success, False on failure.
    """
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO project_sync_state
                (project_id, file_path, content_hash, entity_type, entity_id, last_synced_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (project_id, file_path, content_hash, entity_type, entity_id),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def get_project_sync_state(project_id: str, file_path: str) -> Optional[dict]:
    """Get sync state for a specific project file."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM project_sync_state WHERE project_id = ? AND file_path = ?",
            (project_id, file_path),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_project_sync_states(project_id: str) -> List[dict]:
    """Get all sync states for a project."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM project_sync_state WHERE project_id = ? ORDER BY file_path ASC",
            (project_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_project_sync_state(project_id: str, file_path: str) -> bool:
    """Delete sync state for a specific project file. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM project_sync_state WHERE project_id = ? AND file_path = ?",
            (project_id, file_path),
        )
        conn.commit()
        return cursor.rowcount > 0
