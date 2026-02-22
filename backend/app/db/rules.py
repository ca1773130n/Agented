"""Rules CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection

logger = logging.getLogger(__name__)


def add_rule(
    name: str,
    rule_type: str = "validation",
    description: Optional[str] = None,
    condition: Optional[str] = None,
    action: Optional[str] = None,
    enabled: bool = True,
    project_id: Optional[str] = None,
    source_path: Optional[str] = None,
) -> Optional[int]:
    """Add a new rule."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO rules (name, rule_type, description, condition, action, enabled, project_id, source_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    name,
                    rule_type,
                    description,
                    condition,
                    action,
                    1 if enabled else 0,
                    project_id,
                    source_path,
                ),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Database error in add_rule: {e}")
            return None


def update_rule(
    rule_id: int,
    name: Optional[str] = None,
    rule_type: Optional[str] = None,
    description: Optional[str] = None,
    condition: Optional[str] = None,
    action: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> bool:
    """Update an existing rule."""
    with get_connection() as conn:
        updates = []
        values = []
        if name is not None:
            updates.append("name = ?")
            values.append(name)
        if rule_type is not None:
            updates.append("rule_type = ?")
            values.append(rule_type)
        if description is not None:
            updates.append("description = ?")
            values.append(description)
        if condition is not None:
            updates.append("condition = ?")
            values.append(condition)
        if action is not None:
            updates.append("action = ?")
            values.append(action)
        if enabled is not None:
            updates.append("enabled = ?")
            values.append(1 if enabled else 0)
        if not updates:
            return False
        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(rule_id)
        cursor = conn.execute(f"UPDATE rules SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_rule(rule_id: int) -> bool:
    """Delete a rule."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_rule(rule_id: int) -> Optional[dict]:
    """Get a rule by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM rules WHERE id = ?", (rule_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_rules(
    project_id: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[dict]:
    """Get all rules, optionally filtered by project, with optional pagination."""
    with get_connection() as conn:
        params: list = []
        if project_id:
            sql = "SELECT * FROM rules WHERE project_id = ? OR project_id IS NULL ORDER BY name ASC"
            params.append(project_id)
        else:
            sql = "SELECT * FROM rules ORDER BY name ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def count_rules(project_id: Optional[str] = None) -> int:
    """Count total number of rules, optionally filtered by project."""
    with get_connection() as conn:
        if project_id:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM rules WHERE project_id = ? OR project_id IS NULL",
                (project_id,),
            )
        else:
            cursor = conn.execute("SELECT COUNT(*) FROM rules")
        return cursor.fetchone()[0]


def get_rules_by_project(project_id: str) -> List[dict]:
    """Get rules for a specific project only."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM rules WHERE project_id = ? ORDER BY name ASC",
            (project_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_rules_by_type(rule_type: str) -> List[dict]:
    """Get rules by type."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM rules WHERE rule_type = ? AND enabled = 1 ORDER BY name ASC",
            (rule_type,),
        )
        return [dict(row) for row in cursor.fetchall()]
