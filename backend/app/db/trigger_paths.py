"""Path / symlink / GitHub-repo / project-link helpers for triggers.

Split out of triggers.py in v0.7.3 — the file had grown past 1400
lines and mixed five distinct domains. Public API unchanged: this
module's symbols are re-exported from `app.db.triggers` for
backward compatibility.
"""

import logging
import os
import re
import sqlite3
from typing import Dict, List

import app.config as config

from .connection import get_connection

logger = logging.getLogger(__name__)


def _ensure_symlink_dir():
    """Ensure the symlink directory exists."""
    os.makedirs(config.SYMLINK_DIR, exist_ok=True)


def _sanitize_name(name: str) -> str:
    """Sanitize a name for use in filesystem."""
    # Replace non-alphanumeric chars with underscore
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    # Remove leading/trailing underscores and collapse multiple underscores
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "project"


def _generate_symlink_name(trigger_id: str, local_path: str) -> str:
    """Generate a unique symlink name for a project path."""
    basename = os.path.basename(local_path.rstrip("/"))
    sanitized = _sanitize_name(basename)
    base_name = f"{trigger_id}_{sanitized}"

    # Check if name already exists, add suffix if needed
    _ensure_symlink_dir()
    final_name = base_name
    counter = 1
    while os.path.exists(os.path.join(config.SYMLINK_DIR, final_name)):
        final_name = f"{base_name}_{counter}"
        counter += 1

    return final_name


def _create_symlink(symlink_name: str, target_path: str) -> bool:
    """Create a symlink in the project_links directory."""
    _ensure_symlink_dir()
    symlink_path = os.path.join(config.SYMLINK_DIR, symlink_name)
    try:
        os.symlink(target_path, symlink_path)
        if not os.path.exists(symlink_path):
            logger.debug(
                "Created broken symlink: %s -> %s (target not readable)", symlink_path, target_path
            )
            try:
                os.unlink(symlink_path)
            except OSError as unlink_err:
                logger.warning("Failed to clean up broken symlink %s: %s", symlink_path, unlink_err)
            return False
        logger.debug("Created symlink: %s -> %s", symlink_path, target_path)
        return True
    except OSError as e:
        logger.debug("Failed to create symlink: %s", e)
        return False


def _remove_symlink(symlink_name: str) -> bool:
    """Remove a symlink from the project_links directory."""
    if not symlink_name:
        return False
    symlink_path = os.path.join(config.SYMLINK_DIR, symlink_name)
    try:
        if os.path.islink(symlink_path):
            os.unlink(symlink_path)
            logger.debug("Removed symlink: %s", symlink_path)
            return True
        return False
    except OSError as e:
        logger.debug("Failed to remove symlink: %s", e)
        return False


# =============================================================================
# Project path operations
# =============================================================================


def add_project_path(trigger_id: str, local_project_path: str) -> bool:
    """Add a project path to a trigger. Creates symlink and returns True on success."""
    # Generate symlink name and create symlink
    symlink_name = _generate_symlink_name(trigger_id, local_project_path)
    if not _create_symlink(symlink_name, local_project_path):
        return False

    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO project_paths (trigger_id, local_project_path, symlink_name) VALUES (?, ?, ?)",
                (trigger_id, local_project_path, symlink_name),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Rollback symlink if DB insert fails
            _remove_symlink(symlink_name)
            return False


def remove_project_path(trigger_id: str, local_project_path: str) -> bool:
    """Remove a project path from a trigger. Removes symlink and returns True on success."""
    with get_connection() as conn:
        # Get symlink name before deleting
        cursor = conn.execute(
            "SELECT symlink_name FROM project_paths WHERE trigger_id = ? AND local_project_path = ?",
            (trigger_id, local_project_path),
        )
        row = cursor.fetchone()
        symlink_name = row["symlink_name"] if row else None

        # Delete from database
        cursor = conn.execute(
            "DELETE FROM project_paths WHERE trigger_id = ? AND local_project_path = ?",
            (trigger_id, local_project_path),
        )
        conn.commit()

        if cursor.rowcount > 0:
            # Remove symlink after successful DB delete
            _remove_symlink(symlink_name)
            return True
        return False


def get_paths_for_trigger(trigger_id: str) -> List[str]:
    """Get all original project paths for a specific trigger."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT local_project_path FROM project_paths WHERE trigger_id = ?", (trigger_id,)
        )
        return [row["local_project_path"] for row in cursor.fetchall()]


def get_symlink_paths_for_trigger(trigger_id: str) -> List[str]:
    """Get all symlink paths (relative to project_links/) for a specific trigger."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT symlink_name FROM project_paths WHERE trigger_id = ? AND symlink_name IS NOT NULL",
            (trigger_id,),
        )
        return [f"project_links/{row['symlink_name']}" for row in cursor.fetchall()]


def list_paths_for_trigger(trigger_id: str, limit=None, offset=0) -> List[dict]:
    """Get all project paths with metadata for a specific trigger."""
    with get_connection() as conn:
        query = """SELECT pp.id, pp.local_project_path, pp.symlink_name, pp.path_type,
                      pp.github_repo_url, pp.project_id, pp.created_at,
                      p.name as project_name, p.github_repo as project_github_repo
               FROM project_paths pp
               LEFT JOIN projects p ON pp.project_id = p.id
               WHERE pp.trigger_id = ?
               ORDER BY pp.created_at ASC"""
        params: list = [trigger_id]
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def count_paths_for_trigger(trigger_id: str) -> int:
    """Count project paths for a specific trigger."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM project_paths WHERE trigger_id = ?", (trigger_id,)
        )
        return cursor.fetchone()[0]


def add_github_repo(trigger_id: str, github_repo_url: str) -> bool:
    """Add a GitHub repo to a trigger. Returns True on success."""
    # Use github:// placeholder as local_project_path for uniqueness constraint
    # Extract owner/repo from any GitHub host URL
    url_stripped = github_repo_url.rstrip("/")
    match = re.match(r"https?://[^/]+/(.+)", url_stripped)
    repo_slug = match.group(1) if match else url_stripped
    placeholder = f"github://{repo_slug}"

    with get_connection() as conn:
        try:
            conn.execute(
                """INSERT INTO project_paths
                   (trigger_id, local_project_path, path_type, github_repo_url)
                   VALUES (?, ?, 'github', ?)""",
                (trigger_id, placeholder, github_repo_url),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def remove_github_repo(trigger_id: str, github_repo_url: str) -> bool:
    """Remove a GitHub repo from a trigger. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM project_paths WHERE trigger_id = ? AND github_repo_url = ?",
            (trigger_id, github_repo_url),
        )
        conn.commit()
        return cursor.rowcount > 0


def add_project_to_trigger(trigger_id: str, project_id: str) -> bool:
    """Add a project reference to a trigger. Returns True on success."""
    # Use project:// placeholder as local_project_path for uniqueness constraint
    placeholder = f"project://{project_id}"

    with get_connection() as conn:
        try:
            # Get the project's github_repo for reference
            cursor = conn.execute(
                "SELECT github_repo FROM projects WHERE id = ?",
                (project_id,),
            )
            row = cursor.fetchone()
            github_repo = row["github_repo"] if row else None

            conn.execute(
                """INSERT INTO project_paths
                   (trigger_id, local_project_path, path_type, github_repo_url, project_id)
                   VALUES (?, ?, 'project', ?, ?)""",
                (trigger_id, placeholder, github_repo, project_id),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def remove_project_from_trigger(trigger_id: str, project_id: str) -> bool:
    """Remove a project reference from a trigger. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM project_paths WHERE trigger_id = ? AND project_id = ?",
            (trigger_id, project_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_paths_for_trigger_detailed(trigger_id: str) -> List[Dict]:
    """Get all paths for a trigger with type information."""
    with get_connection() as conn:
        cursor = conn.execute(
            """SELECT local_project_path, path_type, github_repo_url
               FROM project_paths WHERE trigger_id = ?""",
            (trigger_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
