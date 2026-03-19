"""Project Team Instance CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_pti_id

logger = logging.getLogger(__name__)


# =============================================================================
# Project Team Instance CRUD
# =============================================================================


def create_project_team_instance(
    project_id: str,
    template_team_id: str,
    config_overrides: str = None,
) -> Optional[str]:
    """Add a new project team instance. Returns instance ID on success, None on failure."""
    with get_connection() as conn:
        try:
            pti_id = _get_unique_pti_id(conn)
            conn.execute(
                """
                INSERT INTO project_team_instances
                (id, project_id, template_team_id, config_overrides)
                VALUES (?, ?, ?, ?)
            """,
                (pti_id, project_id, template_team_id, config_overrides),
            )
            conn.commit()
            return pti_id
        except sqlite3.IntegrityError:
            return None


def get_project_team_instance(instance_id: str) -> Optional[dict]:
    """Get a single project team instance by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM project_team_instances WHERE id = ?", (instance_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_project_team_instances_for_project(project_id: str) -> List[dict]:
    """Get all team instances for a project ordered by created_at DESC."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM project_team_instances WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_project_team_instance(instance_id: str) -> bool:
    """Delete a project team instance. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM project_team_instances WHERE id = ?", (instance_id,))
        conn.commit()
        return cursor.rowcount > 0
