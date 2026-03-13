"""Findings database CRUD operations.

Findings represent actionable security, code review, and analysis issues
surfaced by bots and triaged on the FindingsTriageBoardPage.
"""

import logging
from typing import Optional

from .connection import get_connection
from .ids import generate_id

logger = logging.getLogger(__name__)


def create_finding(data: dict) -> str:
    """Create a new finding. Returns the new finding ID.

    Args:
        data: Dict with keys: title, severity, and optional description,
              bot_id, file_ref, owner, execution_id.

    Returns:
        The new finding ID (find-XXXXXX).
    """
    finding_id = generate_id("find-", 6)
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO findings
               (id, title, description, severity, status, bot_id, file_ref, owner, execution_id)
               VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?)""",
            (
                finding_id,
                data["title"],
                data.get("description"),
                data["severity"],
                data.get("bot_id"),
                data.get("file_ref"),
                data.get("owner"),
                data.get("execution_id"),
            ),
        )
        conn.commit()
    return finding_id


def list_findings(
    status: Optional[str] = None,
    bot_id: Optional[str] = None,
    owner: Optional[str] = None,
) -> list[dict]:
    """List findings with optional filtering.

    Args:
        status: Filter by status (open, in_progress, resolved, wont_fix).
        bot_id: Filter by originating bot ID.
        owner: Filter by assigned owner.

    Returns:
        List of finding dicts ordered by created_at descending.
    """
    conditions = []
    params: list = []

    if status is not None:
        conditions.append("status = ?")
        params.append(status)
    if bot_id is not None:
        conditions.append("bot_id = ?")
        params.append(bot_id)
    if owner is not None:
        conditions.append("owner = ?")
        params.append(owner)

    sql = "SELECT * FROM findings"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC"

    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def get_finding(finding_id: str) -> Optional[dict]:
    """Get a single finding by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_finding(finding_id: str, updates: dict) -> bool:
    """Partially update a finding (status, owner).

    Args:
        finding_id: ID of the finding to update.
        updates: Dict of fields to update (status and/or owner).

    Returns:
        True if a row was updated, False otherwise.
    """
    fields = []
    params: list = []

    if "status" in updates and updates["status"] is not None:
        fields.append("status = ?")
        params.append(updates["status"])
    if "owner" in updates:
        fields.append("owner = ?")
        params.append(updates["owner"])

    if not fields:
        return False

    fields.append("updated_at = CURRENT_TIMESTAMP")
    params.append(finding_id)
    sql = f"UPDATE findings SET {', '.join(fields)} WHERE id = ?"

    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.rowcount > 0


def delete_finding(finding_id: str) -> bool:
    """Delete a finding by ID. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM findings WHERE id = ?", (finding_id,))
        conn.commit()
        return cursor.rowcount > 0
