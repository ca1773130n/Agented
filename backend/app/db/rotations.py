"""Rotation events and organizational CRUD operations."""

import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import (
    _get_unique_product_decision_id,
    _get_unique_product_milestone_id,
    _get_unique_rotation_event_id,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Rotation Event CRUD
# =============================================================================


def add_rotation_event(
    execution_id: str,
    from_account_id: int = None,
    to_account_id: int = None,
    reason: str = None,
    urgency: str = "normal",
) -> Optional[str]:
    """Add a new rotation event. Returns event_id on success, None on failure."""
    with get_connection() as conn:
        try:
            event_id = _get_unique_rotation_event_id(conn)
            conn.execute(
                """
                INSERT INTO rotation_events
                (id, execution_id, from_account_id, to_account_id, reason, urgency)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (event_id, execution_id, from_account_id, to_account_id, reason, urgency),
            )
            conn.commit()
            return event_id
        except sqlite3.IntegrityError:
            return None


def get_rotation_event(event_id: str) -> Optional[dict]:
    """Get a single rotation event by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM rotation_events WHERE id = ?", (event_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_rotation_events_by_execution(execution_id: str) -> List[dict]:
    """Get all rotation events for an execution, ordered by created_at DESC."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM rotation_events WHERE execution_id = ? ORDER BY created_at DESC",
            (execution_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_all_rotation_events(limit: int = 100) -> List[dict]:
    """Get all rotation events, ordered by created_at DESC."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM rotation_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_rotation_events_enriched(limit: int = 50) -> List[dict]:
    """Get all rotation events with account names from JOIN, ordered by created_at DESC."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT re.*,
                   COALESCE(ba_from.account_name, 'Deleted Account') AS from_account_name,
                   COALESCE(ba_to.account_name, 'Deleted Account') AS to_account_name
            FROM rotation_events re
            LEFT JOIN backend_accounts ba_from ON re.from_account_id = ba_from.id
            LEFT JOIN backend_accounts ba_to ON re.to_account_id = ba_to.id
            ORDER BY re.created_at DESC
            LIMIT ?
        """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_rotation_events_enriched_by_execution(execution_id: str) -> List[dict]:
    """Get rotation events for a specific execution with account names from JOIN."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT re.*,
                   COALESCE(ba_from.account_name, 'Deleted Account') AS from_account_name,
                   COALESCE(ba_to.account_name, 'Deleted Account') AS to_account_name
            FROM rotation_events re
            LEFT JOIN backend_accounts ba_from ON re.from_account_id = ba_from.id
            LEFT JOIN backend_accounts ba_to ON re.to_account_id = ba_to.id
            WHERE re.execution_id = ?
            ORDER BY re.created_at DESC
        """,
            (execution_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_rotation_event(event_id: str, **kwargs) -> bool:
    """Update rotation event fields. Returns True on success.

    Supported kwargs: rotation_status, utilization_at_rotation,
    continuation_execution_id, completed_at.
    """
    allowed = {
        "rotation_status",
        "utilization_at_rotation",
        "continuation_execution_id",
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

    values.append(event_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE rotation_events SET {', '.join(updates)} WHERE id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Product Decision CRUD
# =============================================================================


def add_product_decision(
    product_id: str,
    title: str,
    description: str = None,
    decision_type: str = "technical",
    rationale: str = None,
    tags_json: str = None,
) -> Optional[str]:
    """Add a new product decision. Returns decision_id on success, None on failure."""
    with get_connection() as conn:
        try:
            decision_id = _get_unique_product_decision_id(conn)
            conn.execute(
                """
                INSERT INTO product_decisions
                (id, product_id, title, description, decision_type, rationale, tags_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    decision_id,
                    product_id,
                    title,
                    description,
                    decision_type,
                    rationale,
                    tags_json,
                ),
            )
            conn.commit()
            return decision_id
        except sqlite3.IntegrityError:
            return None


def get_product_decision(decision_id: str) -> Optional[dict]:
    """Get a single product decision by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM product_decisions WHERE id = ?", (decision_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_decisions_by_product(product_id: str, status: str = None, tag: str = None) -> List[dict]:
    """Get all decisions for a product with optional status and tag filtering."""
    with get_connection() as conn:
        query = "SELECT * FROM product_decisions WHERE product_id = ?"
        params: list = [product_id]

        if status:
            query += " AND status = ?"
            params.append(status)
        if tag:
            query += " AND tags_json LIKE ?"
            params.append(f"%{tag}%")

        query += " ORDER BY created_at DESC"
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def update_product_decision(decision_id: str, **kwargs) -> bool:
    """Update product decision fields. Returns True on success.

    Supported kwargs: title, description, decision_type, status, decided_by,
    decided_at, context_json, rationale, tags_json.
    """
    allowed = {
        "title",
        "description",
        "decision_type",
        "status",
        "decided_by",
        "decided_at",
        "context_json",
        "rationale",
        "tags_json",
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
    values.append(decision_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE product_decisions SET {', '.join(updates)} WHERE id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_product_decision(decision_id: str) -> bool:
    """Delete a product decision. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM product_decisions WHERE id = ?", (decision_id,))
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Product Milestone CRUD
# =============================================================================


def add_product_milestone(
    product_id: str,
    version: str,
    title: str,
    description: str = None,
    target_date: str = None,
    sort_order: int = 0,
    progress_pct: int = 0,
) -> Optional[str]:
    """Add a new product milestone. Returns milestone_id on success, None on failure."""
    with get_connection() as conn:
        try:
            milestone_id = _get_unique_product_milestone_id(conn)
            conn.execute(
                """
                INSERT INTO product_milestones
                (id, product_id, version, title, description, target_date, sort_order, progress_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    milestone_id,
                    product_id,
                    version,
                    title,
                    description,
                    target_date,
                    sort_order,
                    progress_pct,
                ),
            )
            conn.commit()
            return milestone_id
        except sqlite3.IntegrityError:
            return None


def get_product_milestone(milestone_id: str) -> Optional[dict]:
    """Get a single product milestone by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM product_milestones WHERE id = ?", (milestone_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_milestones_by_product(product_id: str, status: str = None) -> List[dict]:
    """Get all milestones for a product with optional status filtering."""
    with get_connection() as conn:
        query = "SELECT * FROM product_milestones WHERE product_id = ?"
        params: list = [product_id]

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY sort_order ASC, created_at DESC"
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def update_product_milestone(milestone_id: str, **kwargs) -> bool:
    """Update product milestone fields. Returns True on success.

    Supported kwargs: version, title, description, status, target_date,
    sort_order, progress_pct, completed_date.
    """
    allowed = {
        "version",
        "title",
        "description",
        "status",
        "target_date",
        "sort_order",
        "progress_pct",
        "completed_date",
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
    values.append(milestone_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE product_milestones SET {', '.join(updates)} WHERE id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_product_milestone(milestone_id: str) -> bool:
    """Delete a product milestone. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM product_milestones WHERE id = ?", (milestone_id,))
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Team Connection CRUD
# =============================================================================


def add_team_connection(
    source_team_id: str,
    target_team_id: str,
    connection_type: str = "dependency",
    description: str = None,
) -> Optional[int]:
    """Add a directed connection between teams. Returns integer autoincrement ID."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO team_connections
                (source_team_id, target_team_id, connection_type, description)
                VALUES (?, ?, ?, ?)
            """,
                (source_team_id, target_team_id, connection_type, description),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_team_connections(team_id: str) -> List[dict]:
    """Get all connections for a team (as source or target)."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM team_connections WHERE source_team_id = ? OR target_team_id = ?",
            (team_id, team_id),
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_team_connection(connection_id: int) -> bool:
    """Delete a team connection. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM team_connections WHERE id = ?", (connection_id,))
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Milestone-Projects Junction CRUD
# =============================================================================


def add_milestone_project(
    milestone_id: str,
    project_id: str,
    contribution: str = None,
) -> Optional[int]:
    """Link a project to a product milestone. Returns integer autoincrement ID."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO milestone_projects
                (milestone_id, project_id, contribution)
                VALUES (?, ?, ?)
            """,
                (milestone_id, project_id, contribution),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_projects_for_milestone(milestone_id: str) -> List[dict]:
    """Get all projects linked to a product milestone."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT mp.*, p.name as project_name, p.status as project_status
            FROM milestone_projects mp
            JOIN projects p ON mp.project_id = p.id
            WHERE mp.milestone_id = ?
            ORDER BY p.name ASC
        """,
            (milestone_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_milestone_project(milestone_id: str, project_id: str) -> bool:
    """Remove a project from a product milestone. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM milestone_projects WHERE milestone_id = ? AND project_id = ?",
            (milestone_id, project_id),
        )
        conn.commit()
        return cursor.rowcount > 0
