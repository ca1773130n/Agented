"""Campaigns CRUD operations for multi-repo campaign orchestration."""

import datetime
import json
import logging
import sqlite3
from typing import List, Optional

from .connection import get_connection
from .ids import _get_unique_campaign_id

logger = logging.getLogger(__name__)


def create_campaign(name: str, trigger_id: str, repo_urls: list[str]) -> Optional[str]:
    """Create a new campaign. Returns campaign_id or None on error."""
    with get_connection() as conn:
        try:
            campaign_id = _get_unique_campaign_id(conn)
            now = datetime.datetime.now().isoformat()
            conn.execute(
                """
                INSERT INTO campaigns (id, name, trigger_id, status, repo_urls,
                                       total_repos, completed_repos, failed_repos, started_at)
                VALUES (?, ?, ?, 'running', ?, ?, 0, 0, ?)
                """,
                (
                    campaign_id,
                    name,
                    trigger_id,
                    json.dumps(repo_urls),
                    len(repo_urls),
                    now,
                ),
            )
            conn.commit()
            return campaign_id
        except sqlite3.Error as e:
            logger.error("Database error in create_campaign: %s", e)
            return None


def get_campaign(campaign_id: str) -> Optional[dict]:
    """Get a campaign by ID."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        # Parse repo_urls JSON
        if result.get("repo_urls"):
            try:
                result["repo_urls"] = json.loads(result["repo_urls"])
            except (json.JSONDecodeError, TypeError):
                result["repo_urls"] = []
        return result


def list_campaigns(
    trigger_id: Optional[str] = None,
    status: Optional[str] = None,
) -> List[dict]:
    """List campaigns with optional filtering."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM campaigns"
        params = []
        conditions = []

        if trigger_id:
            conditions.append("trigger_id = ?")
            params.append(trigger_id)
        if status:
            conditions.append("status = ?")
            params.append(status)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC"

        rows = conn.execute(query, params).fetchall()
        results = []
        for row in rows:
            r = dict(row)
            if r.get("repo_urls"):
                try:
                    r["repo_urls"] = json.loads(r["repo_urls"])
                except (json.JSONDecodeError, TypeError):
                    r["repo_urls"] = []
            results.append(r)
        return results


def update_campaign_status(
    campaign_id: str,
    status: str,
    completed: Optional[int] = None,
    failed: Optional[int] = None,
) -> bool:
    """Update campaign status and optional counters."""
    with get_connection() as conn:
        try:
            updates = ["status = ?"]
            params = [status]

            if completed is not None:
                updates.append("completed_repos = ?")
                params.append(completed)
            if failed is not None:
                updates.append("failed_repos = ?")
                params.append(failed)

            if status in ("completed", "partial_failure"):
                updates.append("finished_at = ?")
                params.append(datetime.datetime.now().isoformat())

            params.append(campaign_id)
            cursor = conn.execute(
                f"UPDATE campaigns SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error("Database error in update_campaign_status: %s", e)
            return False


def create_campaign_execution(campaign_id: str, repo_url: str) -> Optional[int]:
    """Add a campaign execution entry for a repo. Returns row id."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO campaign_executions (campaign_id, repo_url, status)
                VALUES (?, ?, 'pending')
                """,
                (campaign_id, repo_url),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error("Database error in create_campaign_execution: %s", e)
            return None


def update_campaign_execution(
    campaign_id: str,
    repo_url: str,
    execution_id: Optional[str] = None,
    status: Optional[str] = None,
    error: Optional[str] = None,
) -> bool:
    """Update a campaign execution entry."""
    with get_connection() as conn:
        try:
            updates = []
            params = []

            if execution_id is not None:
                updates.append("execution_id = ?")
                params.append(execution_id)
            if status is not None:
                updates.append("status = ?")
                params.append(status)
                if status == "running":
                    updates.append("started_at = ?")
                    params.append(datetime.datetime.now().isoformat())
                elif status in ("completed", "failed"):
                    updates.append("finished_at = ?")
                    params.append(datetime.datetime.now().isoformat())
            if error is not None:
                updates.append("error_message = ?")
                params.append(error)

            if not updates:
                return True

            params.extend([campaign_id, repo_url])
            cursor = conn.execute(
                f"UPDATE campaign_executions SET {', '.join(updates)} "
                "WHERE campaign_id = ? AND repo_url = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error("Database error in update_campaign_execution: %s", e)
            return False


def list_campaign_executions(campaign_id: str) -> List[dict]:
    """List all executions for a campaign."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM campaign_executions WHERE campaign_id = ? ORDER BY id",
            (campaign_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def delete_campaign(campaign_id: str) -> bool:
    """Delete a campaign and its executions (CASCADE)."""
    with get_connection() as conn:
        try:
            # Enable foreign keys for CASCADE
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error("Database error in delete_campaign: %s", e)
            return False
