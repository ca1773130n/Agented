"""GitOps repository configuration and sync state CRUD operations."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from .connection import get_connection
from .ids import _generate_short_id

logger = logging.getLogger(__name__)

GITOPS_REPO_ID_PREFIX = "gop-"
GITOPS_REPO_ID_LENGTH = 6


def _generate_gitops_repo_id() -> str:
    """Generate a unique gitops repo ID."""
    return GITOPS_REPO_ID_PREFIX + _generate_short_id(GITOPS_REPO_ID_LENGTH)


def create_gitops_repo(
    name: str,
    repo_url: str,
    branch: str = "main",
    config_path: str = "agented/",
    poll_interval: int = 60,
) -> str:
    """Create a new GitOps repo configuration.

    Args:
        name: Human-readable name for this repo.
        repo_url: Git repository URL.
        branch: Branch to watch (default: main).
        config_path: Path within repo containing configs (default: agented/).
        poll_interval: Polling interval in seconds (default: 60).

    Returns:
        The generated repo ID.
    """
    repo_id = _generate_gitops_repo_id()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO gitops_repos (id, name, repo_url, branch, config_path,
               poll_interval_seconds) VALUES (?, ?, ?, ?, ?, ?)""",
            (repo_id, name, repo_url, branch, config_path, poll_interval),
        )
        conn.commit()
    return repo_id


def get_gitops_repo(repo_id: str) -> Optional[dict]:
    """Get a single GitOps repo configuration.

    Args:
        repo_id: The repo ID.

    Returns:
        Dict with repo config, or None if not found.
    """
    with get_connection() as conn:
        conn.row_factory = _dict_factory
        row = conn.execute(
            "SELECT * FROM gitops_repos WHERE id = ?", (repo_id,)
        ).fetchone()
    return row


def list_gitops_repos() -> list[dict]:
    """List all GitOps repo configurations.

    Returns:
        List of repo config dicts.
    """
    with get_connection() as conn:
        conn.row_factory = _dict_factory
        rows = conn.execute(
            "SELECT * FROM gitops_repos ORDER BY created_at DESC"
        ).fetchall()
    return rows


def update_gitops_repo(repo_id: str, **kwargs) -> bool:
    """Update a GitOps repo configuration.

    Args:
        repo_id: The repo ID to update.
        **kwargs: Fields to update (name, repo_url, branch, config_path,
                  poll_interval_seconds, enabled).

    Returns:
        True if the repo was found and updated.
    """
    allowed = {
        "name", "repo_url", "branch", "config_path",
        "poll_interval_seconds", "enabled",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [repo_id]

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE gitops_repos SET {set_clause} WHERE id = ?",
            values,
        )
        conn.commit()
    return cursor.rowcount > 0


def delete_gitops_repo(repo_id: str) -> bool:
    """Delete a GitOps repo configuration.

    Args:
        repo_id: The repo ID to delete.

    Returns:
        True if the repo was found and deleted.
    """
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM gitops_repos WHERE id = ?", (repo_id,))
        conn.commit()
    return cursor.rowcount > 0


def update_sync_state(repo_id: str, commit_sha: str, synced_at: str) -> bool:
    """Update the last sync state for a repo.

    Args:
        repo_id: The repo ID.
        commit_sha: The commit SHA that was synced.
        synced_at: ISO timestamp of sync.

    Returns:
        True if the repo was found and updated.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE gitops_repos SET last_commit_sha = ?, last_sync_at = ? WHERE id = ?",
            (commit_sha, synced_at, repo_id),
        )
        conn.commit()
    return cursor.rowcount > 0


def add_sync_log(
    repo_id: str,
    commit_sha: Optional[str],
    files_changed: int = 0,
    files_applied: int = 0,
    files_conflicted: int = 0,
    status: str = "success",
    details: Optional[str] = None,
) -> int:
    """Add a sync log entry.

    Args:
        repo_id: The repo ID.
        commit_sha: The commit SHA for this sync.
        files_changed: Number of changed files detected.
        files_applied: Number of files applied.
        files_conflicted: Number of files with conflicts.
        status: Sync status (success, failed, skipped, dry_run).
        details: JSON string with sync details.

    Returns:
        The log entry ID.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO gitops_sync_log
               (repo_id, commit_sha, files_changed, files_applied,
                files_conflicted, status, details)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (repo_id, commit_sha, files_changed, files_applied,
             files_conflicted, status, details),
        )
        conn.commit()
    return cursor.lastrowid


def list_sync_logs(repo_id: str, limit: int = 20) -> list[dict]:
    """List sync log entries for a repo.

    Args:
        repo_id: The repo ID.
        limit: Max entries to return (default 20).

    Returns:
        List of sync log dicts, newest first.
    """
    with get_connection() as conn:
        conn.row_factory = _dict_factory
        rows = conn.execute(
            "SELECT * FROM gitops_sync_log WHERE repo_id = ? ORDER BY created_at DESC LIMIT ?",
            (repo_id, limit),
        ).fetchall()
    return rows


def _dict_factory(cursor, row):
    """Convert a sqlite3 Row to a dict."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
