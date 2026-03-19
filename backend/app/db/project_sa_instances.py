"""Project SA Instance CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_psa_id

logger = logging.getLogger(__name__)


# =============================================================================
# Project SA Instance CRUD
# =============================================================================


def create_project_sa_instance(
    project_id: str,
    template_sa_id: str,
    worktree_path: str = None,
    default_chat_mode: str = "management",
    config_overrides: str = None,
) -> Optional[str]:
    """Add a new project SA instance. Returns instance ID on success, None on failure."""
    with get_connection() as conn:
        try:
            psa_id = _get_unique_psa_id(conn)
            conn.execute(
                """
                INSERT INTO project_sa_instances
                (id, project_id, template_sa_id, worktree_path,
                 default_chat_mode, config_overrides)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    psa_id,
                    project_id,
                    template_sa_id,
                    worktree_path,
                    default_chat_mode,
                    config_overrides,
                ),
            )
            conn.commit()
            return psa_id
        except sqlite3.IntegrityError:
            return None


def get_project_sa_instance(instance_id: str) -> Optional[dict]:
    """Get a single project SA instance by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM project_sa_instances WHERE id = ?", (instance_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_project_sa_instance_by_project_and_sa(
    project_id: str, template_sa_id: str
) -> Optional[dict]:
    """Get a project SA instance by project_id and template_sa_id combo."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM project_sa_instances WHERE project_id = ? AND template_sa_id = ?",
            (project_id, template_sa_id),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_project_sa_instances_for_project(project_id: str) -> List[dict]:
    """Get all SA instances for a project ordered by created_at DESC."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM project_sa_instances WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_project_sa_instance(
    instance_id: str,
    worktree_path: str = None,
    default_chat_mode: str = None,
    config_overrides: str = None,
) -> bool:
    """Update project SA instance fields. Returns True on success."""
    updates = []
    values = []

    if worktree_path is not None:
        updates.append("worktree_path = ?")
        values.append(worktree_path)
    if default_chat_mode is not None:
        updates.append("default_chat_mode = ?")
        values.append(default_chat_mode)
    if config_overrides is not None:
        updates.append("config_overrides = ?")
        values.append(config_overrides)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(instance_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE project_sa_instances SET {', '.join(updates)} WHERE id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def get_project_sa_instances_without_worktree() -> List[dict]:
    """Get all SA instances where worktree_path IS NULL."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM project_sa_instances WHERE worktree_path IS NULL")
        return [dict(row) for row in cursor.fetchall()]


def delete_project_sa_instance(instance_id: str) -> bool:
    """Delete a project SA instance. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM project_sa_instances WHERE id = ?", (instance_id,))
        conn.commit()
        return cursor.rowcount > 0
