"""Trigger CRUD operations.

Includes trigger management, path/symlink operations, execution logs,
and PR review records. This module exceeds 500 lines because execution_logs
and PR reviews are kept here for domain cohesion — triggers own their
execution history and review records.
"""

import logging
import os
import re
import sqlite3
from typing import Dict, List, Optional

import app.config as config

from .connection import get_connection
from .ids import _get_unique_trigger_id

logger = logging.getLogger(__name__)

# --- Constants ---

VALID_BACKENDS = ("claude", "opencode", "gemini", "codex")
VALID_TRIGGER_SOURCES = ("webhook", "github", "manual", "scheduled")
VALID_SCHEDULE_TYPES = {"daily", "weekly", "monthly"}

# Predefined trigger configurations
# Predefined trigger IDs retain the bot- prefix to preserve historical execution logs,
# PR review records, and external webhook integrations.
PREDEFINED_TRIGGERS = [
    {
        "id": "bot-security",
        "name": "Weekly Security Audit",
        "group_id": 0,  # Deprecated, use match_field_path/match_field_value
        "detection_keyword": "주간 보안 취약점 알림",
        "prompt_template": "/weekly-security-audit {paths}",
        "backend_type": "claude",
        "trigger_source": "webhook",
        "match_field_path": "event.group_id",
        "match_field_value": "4",
        "text_field_path": "event.text",
        "is_predefined": 1,
    },
    {
        "id": "bot-pr-review",
        "name": "PR Review",
        "group_id": 0,  # Not used for GitHub trigger
        "detection_keyword": "",  # Not used for GitHub trigger
        "prompt_template": "/pr-review {pr_url} {pr_title}",
        "backend_type": "claude",
        "trigger_source": "github",
        "match_field_path": None,
        "match_field_value": None,
        "text_field_path": "text",
        "is_predefined": 1,
    },
]

PREDEFINED_TRIGGER_IDS = {t["id"] for t in PREDEFINED_TRIGGERS}

# Backward compatibility aliases
PREDEFINED_TRIGGER_ID = "bot-security"
PREDEFINED_TRIGGER = PREDEFINED_TRIGGERS[0]


# =============================================================================
# Trigger CRUD
# =============================================================================


def add_trigger(
    name: str,
    prompt_template: str,
    backend_type: str = "claude",
    trigger_source: str = "webhook",
    match_field_path: str = None,
    match_field_value: str = None,
    text_field_path: str = "text",
    detection_keyword: str = "",
    group_id: int = 0,  # Deprecated, kept for backward compatibility
    schedule_type: str = None,
    schedule_time: str = None,
    schedule_day: int = None,
    schedule_timezone: str = "Asia/Seoul",
    skill_command: str = None,
    model: str = None,
    execution_mode: str = "direct",
    team_id: str = None,
    timeout_seconds: int = None,
    webhook_secret: str = None,
    allowed_tools: str = None,
    sigterm_grace_seconds: int = None,
) -> Optional[str]:
    """Add a new trigger. Returns trigger_id (string) on success, None on failure."""
    if backend_type not in VALID_BACKENDS:
        logger.warning(
            "Invalid backend_type %r for trigger %r; falling back to 'claude'. " "Valid values: %s",
            backend_type,
            name,
            VALID_BACKENDS,
        )
        backend_type = "claude"
    if trigger_source not in VALID_TRIGGER_SOURCES:
        logger.warning(
            "Invalid trigger_source %r for trigger %r; falling back to 'webhook'. "
            "Valid values: %s",
            trigger_source,
            name,
            VALID_TRIGGER_SOURCES,
        )
        trigger_source = "webhook"
    if schedule_type and schedule_type not in VALID_SCHEDULE_TYPES:
        logger.warning(
            "Invalid schedule_type %r for trigger %r; setting to None. Valid values: %s",
            schedule_type,
            name,
            VALID_SCHEDULE_TYPES,
        )
        schedule_type = None
    if execution_mode not in ("direct", "team"):
        logger.warning(
            "Invalid execution_mode %r for trigger %r; falling back to 'direct'.",
            execution_mode,
            name,
        )
        execution_mode = "direct"

    with get_connection() as conn:
        try:
            trigger_id = _get_unique_trigger_id(conn)
            conn.execute(
                """
                INSERT INTO triggers (id, name, group_id, detection_keyword, prompt_template, backend_type, trigger_source,
                                      match_field_path, match_field_value, text_field_path,
                                      schedule_type, schedule_time, schedule_day, schedule_timezone, skill_command, model,
                                      execution_mode, team_id, timeout_seconds, webhook_secret, allowed_tools,
                                      sigterm_grace_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    trigger_id,
                    name,
                    group_id,
                    detection_keyword,
                    prompt_template,
                    backend_type,
                    trigger_source,
                    match_field_path,
                    match_field_value,
                    text_field_path,
                    schedule_type,
                    schedule_time,
                    schedule_day,
                    schedule_timezone,
                    skill_command,
                    model,
                    execution_mode,
                    team_id,
                    timeout_seconds,
                    webhook_secret,
                    allowed_tools,
                    sigterm_grace_seconds,
                ),
            )
            conn.commit()
            return trigger_id
        except sqlite3.IntegrityError:
            return None


def update_trigger(
    trigger_id: str,
    name: str = None,
    group_id: int = None,  # Deprecated
    detection_keyword: str = None,
    prompt_template: str = None,
    backend_type: str = None,
    trigger_source: str = None,
    match_field_path: str = None,
    match_field_value: str = None,
    text_field_path: str = None,
    enabled: int = None,
    schedule_type: str = None,
    schedule_time: str = None,
    schedule_day: int = None,
    schedule_timezone: str = None,
    skill_command: str = None,
    model: str = None,
    execution_mode: str = None,
    team_id: str = None,
    timeout_seconds: int = None,
    webhook_secret: str = None,
    allowed_tools: str = None,
    sigterm_grace_seconds: int = None,
) -> bool:
    """Update trigger fields. Returns True on success."""
    updates = []
    values = []

    if name is not None:
        updates.append("name = ?")
        values.append(name)
    if group_id is not None:
        updates.append("group_id = ?")
        values.append(group_id)
    if detection_keyword is not None:
        updates.append("detection_keyword = ?")
        values.append(detection_keyword)
    if prompt_template is not None:
        updates.append("prompt_template = ?")
        values.append(prompt_template)
    if backend_type is not None and backend_type in VALID_BACKENDS:
        updates.append("backend_type = ?")
        values.append(backend_type)
    if trigger_source is not None and trigger_source in VALID_TRIGGER_SOURCES:
        updates.append("trigger_source = ?")
        values.append(trigger_source)
    # Webhook matching fields - allow setting to NULL with empty string
    if match_field_path is not None:
        if match_field_path == "":
            updates.append("match_field_path = NULL")
        else:
            updates.append("match_field_path = ?")
            values.append(match_field_path)
    if match_field_value is not None:
        if match_field_value == "":
            updates.append("match_field_value = NULL")
        else:
            updates.append("match_field_value = ?")
            values.append(match_field_value)
    if text_field_path is not None:
        if text_field_path == "":
            updates.append("text_field_path = 'text'")  # Reset to default
        else:
            updates.append("text_field_path = ?")
            values.append(text_field_path)
    if enabled is not None:
        updates.append("enabled = ?")
        values.append(enabled)
    # Schedule fields - allow setting to NULL by passing empty string
    if schedule_type is not None:
        if schedule_type == "" or schedule_type not in VALID_SCHEDULE_TYPES:
            updates.append("schedule_type = NULL")
        else:
            updates.append("schedule_type = ?")
            values.append(schedule_type)
    if schedule_time is not None:
        if schedule_time == "":
            updates.append("schedule_time = NULL")
        else:
            updates.append("schedule_time = ?")
            values.append(schedule_time)
    if schedule_day is not None:
        updates.append("schedule_day = ?")
        values.append(schedule_day if schedule_day >= 0 else None)
    if schedule_timezone is not None:
        updates.append("schedule_timezone = ?")
        values.append(schedule_timezone or "Asia/Seoul")
    if skill_command is not None:
        if skill_command == "":
            updates.append("skill_command = NULL")
        else:
            updates.append("skill_command = ?")
            values.append(skill_command)
    if model is not None:
        if model == "":
            updates.append("model = NULL")
        else:
            updates.append("model = ?")
            values.append(model)
    if execution_mode is not None:
        if execution_mode in ("direct", "team"):
            updates.append("execution_mode = ?")
            values.append(execution_mode)
    if team_id is not None:
        if team_id == "":
            updates.append("team_id = NULL")
        else:
            updates.append("team_id = ?")
            values.append(team_id)
    if timeout_seconds is not None:
        if timeout_seconds <= 0:
            updates.append("timeout_seconds = NULL")
        else:
            updates.append("timeout_seconds = ?")
            values.append(timeout_seconds)
    if webhook_secret is not None:
        if webhook_secret == "":
            updates.append("webhook_secret = NULL")
        else:
            updates.append("webhook_secret = ?")
            values.append(webhook_secret)
    if allowed_tools is not None:
        if allowed_tools == "":
            updates.append("allowed_tools = NULL")
        else:
            updates.append("allowed_tools = ?")
            values.append(allowed_tools)
    if sigterm_grace_seconds is not None:
        if sigterm_grace_seconds <= 0:
            updates.append("sigterm_grace_seconds = NULL")
        else:
            updates.append("sigterm_grace_seconds = ?")
            values.append(sigterm_grace_seconds)

    if not updates:
        return False

    values.append(trigger_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE triggers SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def delete_trigger(trigger_id: str) -> bool:
    """Delete a trigger (only if not predefined). Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM triggers WHERE id = ? AND is_predefined = 0", (trigger_id,)
        )
        conn.commit()
        return cursor.rowcount > 0


def get_trigger(trigger_id: str) -> Optional[dict]:
    """Get a single trigger by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM triggers WHERE id = ?", (trigger_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_trigger_by_name(name: str) -> Optional[dict]:
    """Get a trigger by its exact name (case-insensitive). Returns first match or None."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM triggers WHERE LOWER(name) = LOWER(?)", (name,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_triggers() -> List[dict]:
    """Get all triggers with their path counts."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT t.*, COUNT(p.id) as path_count
            FROM triggers t
            LEFT JOIN project_paths p ON t.id = p.trigger_id
            GROUP BY t.id
            ORDER BY t.is_predefined DESC, t.created_at ASC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_webhook_triggers() -> List[dict]:
    """Get all enabled triggers with webhook trigger source."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM triggers WHERE trigger_source = 'webhook' AND enabled = 1"
        )
        return [dict(row) for row in cursor.fetchall()]


def get_triggers_by_trigger_source(trigger_source: str) -> List[dict]:
    """Get all enabled triggers with a specific trigger source."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM triggers WHERE trigger_source = ? AND enabled = 1", (trigger_source,)
        )
        return [dict(row) for row in cursor.fetchall()]


def update_trigger_next_run(trigger_id: str, next_run_at) -> bool:
    """Update the next scheduled run time for a trigger."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE triggers SET next_run_at = ? WHERE id = ?", (next_run_at, trigger_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def update_trigger_last_run(trigger_id: str, last_run_at) -> bool:
    """Update the last run time for a trigger."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE triggers SET last_run_at = ? WHERE id = ?", (last_run_at, trigger_id)
        )
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Symlink management
# =============================================================================


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


def list_paths_for_trigger(trigger_id: str) -> List[dict]:
    """Get all project paths with metadata for a specific trigger."""
    with get_connection() as conn:
        cursor = conn.execute(
            """SELECT pp.id, pp.local_project_path, pp.symlink_name, pp.path_type,
                      pp.github_repo_url, pp.project_id, pp.created_at,
                      p.name as project_name, p.github_repo as project_github_repo
               FROM project_paths pp
               LEFT JOIN projects p ON pp.project_id = p.id
               WHERE pp.trigger_id = ?
               ORDER BY pp.created_at ASC""",
            (trigger_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


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


def log_prompt_template_change(trigger_id: str, old_template: str, new_template: str) -> bool:
    """Record a prompt template change in trigger_template_history. Returns True on success."""
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO trigger_template_history (trigger_id, old_template, new_template)
                VALUES (?, ?, ?)
                """,
                (trigger_id, old_template, new_template),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.warning("Failed to log template change for trigger %s: %s", trigger_id, e)
            return False


def get_prompt_template_history(trigger_id: str, limit: int = 50) -> List[dict]:
    """Get prompt template change history for a trigger, newest first."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, trigger_id, old_template, new_template, changed_at
            FROM trigger_template_history
            WHERE trigger_id = ?
            ORDER BY changed_at DESC
            LIMIT ?
            """,
            (trigger_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_trigger_auto_resolve(trigger_id: str, auto_resolve: bool) -> bool:
    """Set the auto_resolve flag on a trigger."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE triggers SET auto_resolve = ? WHERE id = ?",
            (1 if auto_resolve else 0, trigger_id),
        )
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Execution log operations
# =============================================================================


def create_execution_log(
    execution_id: str,
    trigger_id: str,
    trigger_type: str,
    started_at: str,
    prompt: str,
    backend_type: str,
    command: str,
    trigger_config_snapshot: str = None,
    account_id: int = None,
) -> bool:
    """Create a new execution log entry. Returns True on success."""
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO execution_logs (execution_id, trigger_id, trigger_type, started_at, prompt, backend_type, command, status, trigger_config_snapshot, account_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, ?)
            """,
                (
                    execution_id,
                    trigger_id,
                    trigger_type,
                    started_at,
                    prompt,
                    backend_type,
                    command,
                    trigger_config_snapshot,
                    account_id,
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def update_execution_log(
    execution_id: str,
    status: str = None,
    finished_at: str = None,
    duration_ms: int = None,
    exit_code: int = None,
    error_message: str = None,
    stdout_log: str = None,
    stderr_log: str = None,
) -> bool:
    """Update an execution log entry. Returns True on success."""
    updates = []
    values = []

    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if finished_at is not None:
        updates.append("finished_at = ?")
        values.append(finished_at)
    if duration_ms is not None:
        updates.append("duration_ms = ?")
        values.append(duration_ms)
    if exit_code is not None:
        updates.append("exit_code = ?")
        values.append(exit_code)
    if error_message is not None:
        updates.append("error_message = ?")
        values.append(error_message)
    if stdout_log is not None:
        updates.append("stdout_log = ?")
        values.append(stdout_log)
    if stderr_log is not None:
        updates.append("stderr_log = ?")
        values.append(stderr_log)

    if not updates:
        return False

    values.append(execution_id)

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE execution_logs SET {', '.join(updates)} WHERE execution_id = ?", values
        )
        conn.commit()
        return cursor.rowcount > 0


def mark_stale_executions_interrupted() -> int:
    """Mark running executions from previous sessions as interrupted. Returns count affected.

    This is a public API for use outside init_db() if needed.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE execution_logs SET status = 'interrupted', finished_at = datetime('now') WHERE status = 'running'"
        )
        conn.commit()
        return cursor.rowcount


def update_execution_status_cas(
    execution_id: str,
    new_status: str,
    expected_status: str = "running",
    **kwargs,
) -> bool:
    """Update execution status only if current status matches expected. Returns True if updated.

    Compare-and-swap update to prevent race conditions between cancel and normal completion.
    Accepts optional kwargs: finished_at, duration_ms, exit_code, error_message, stdout_log, stderr_log.
    """
    updates = ["status = ?"]
    values = [new_status]

    allowed_fields = {
        "finished_at",
        "duration_ms",
        "exit_code",
        "error_message",
        "stdout_log",
        "stderr_log",
    }
    for key, value in kwargs.items():
        if key in allowed_fields and value is not None:
            updates.append(f"{key} = ?")
            values.append(value)

    values.extend([execution_id, expected_status])

    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE execution_logs SET {', '.join(updates)} WHERE execution_id = ? AND status = ?",
            values,
        )
        conn.commit()
        return cursor.rowcount > 0


def get_execution_log(execution_id: str) -> Optional[dict]:
    """Get a single execution log by execution_id."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM execution_logs WHERE execution_id = ?", (execution_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_execution_logs_for_trigger(
    trigger_id: str, limit: int = 50, offset: int = 0, status: str = None
) -> List[dict]:
    """Get execution logs for a trigger with pagination."""
    with get_connection() as conn:
        query = "SELECT * FROM execution_logs WHERE trigger_id = ?"
        params = [trigger_id]

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_all_execution_logs(limit: int = 100, offset: int = 0) -> List[dict]:
    """Get all execution logs with pagination."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT e.*, t.name as trigger_name
            FROM execution_logs e
            LEFT JOIN triggers t ON e.trigger_id = t.id
            ORDER BY e.started_at DESC
            LIMIT ? OFFSET ?
        """,
            (limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_running_execution_for_trigger(trigger_id: str) -> Optional[dict]:
    """Get the currently running execution for a trigger, if any."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM execution_logs WHERE trigger_id = ? AND status = 'running' ORDER BY started_at DESC LIMIT 1",
            (trigger_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_latest_execution_for_trigger(trigger_id: str) -> Optional[dict]:
    """Get the latest execution log entry for a trigger (any status)."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM execution_logs WHERE trigger_id = ? ORDER BY started_at DESC LIMIT 1",
            (trigger_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def count_execution_logs_for_trigger(trigger_id: str, status: str = None) -> int:
    """Count execution logs for a trigger with optional status filter."""
    with get_connection() as conn:
        query = "SELECT COUNT(*) FROM execution_logs WHERE trigger_id = ?"
        params: list = [trigger_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        cursor = conn.execute(query, params)
        return cursor.fetchone()[0]


def count_all_execution_logs() -> int:
    """Count all execution logs."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM execution_logs")
        return cursor.fetchone()[0]


def get_active_execution_count() -> int:
    """Get the count of currently running executions."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM execution_logs WHERE status = 'running'")
        return cursor.fetchone()[0]


def delete_old_execution_logs(days: int = 30) -> int:
    """Delete execution logs older than specified days. Returns count of deleted rows."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM execution_logs WHERE started_at < datetime('now', ?)", (f"-{days} days",)
        )
        conn.commit()
        return cursor.rowcount


# =============================================================================
# PR review operations
# =============================================================================


def add_pr_review(
    project_name: str,
    pr_number: int,
    pr_url: str,
    pr_title: str,
    trigger_id: str = "bot-pr-review",
    github_repo_url: str = None,
    pr_author: str = None,
) -> Optional[int]:
    """Add a new PR review record. Returns the row id on success."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO pr_reviews
                    (trigger_id, project_name, github_repo_url, pr_number, pr_url,
                     pr_title, pr_author)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (trigger_id, project_name, github_repo_url, pr_number, pr_url, pr_title, pr_author),
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def update_pr_review(
    review_id: int,
    pr_status: str = None,
    review_status: str = None,
    review_comment: str = None,
    fixes_applied: int = None,
    fix_comment: str = None,
) -> bool:
    """Update a PR review record. Returns True on success."""
    updates = []
    values = []

    if pr_status is not None:
        updates.append("pr_status = ?")
        values.append(pr_status)
    if review_status is not None:
        updates.append("review_status = ?")
        values.append(review_status)
    if review_comment is not None:
        updates.append("review_comment = ?")
        values.append(review_comment)
    if fixes_applied is not None:
        updates.append("fixes_applied = ?")
        values.append(fixes_applied)
    if fix_comment is not None:
        updates.append("fix_comment = ?")
        values.append(fix_comment)

    if not updates:
        return False

    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.append(review_id)

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE pr_reviews SET {', '.join(updates)} WHERE id = ?", values)
        conn.commit()
        return cursor.rowcount > 0


def get_pr_review(review_id: int) -> Optional[dict]:
    """Get a single PR review by id."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM pr_reviews WHERE id = ?", (review_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_pr_reviews_for_trigger(
    trigger_id: str = "bot-pr-review",
    limit: int = 50,
    offset: int = 0,
    pr_status: str = None,
    review_status: str = None,
) -> List[dict]:
    """Get PR reviews for a trigger with optional filtering."""
    with get_connection() as conn:
        query = "SELECT * FROM pr_reviews WHERE trigger_id = ?"
        params: list = [trigger_id]

        if pr_status:
            query += " AND pr_status = ?"
            params.append(pr_status)
        if review_status:
            query += " AND review_status = ?"
            params.append(review_status)

        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_pr_reviews_count(
    trigger_id: str = "bot-pr-review", pr_status: str = None, review_status: str = None
) -> int:
    """Get count of PR reviews with optional filtering."""
    with get_connection() as conn:
        query = "SELECT COUNT(*) as cnt FROM pr_reviews WHERE trigger_id = ?"
        params: list = [trigger_id]

        if pr_status:
            query += " AND pr_status = ?"
            params.append(pr_status)
        if review_status:
            query += " AND review_status = ?"
            params.append(review_status)

        cursor = conn.execute(query, params)
        return cursor.fetchone()["cnt"]


def get_pr_review_stats(trigger_id: str = "bot-pr-review") -> dict:
    """Get aggregate PR review statistics."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                COUNT(*) as total_prs,
                COALESCE(SUM(CASE WHEN pr_status = 'open' THEN 1 ELSE 0 END), 0) as open_prs,
                COALESCE(SUM(CASE WHEN pr_status = 'merged' THEN 1 ELSE 0 END), 0) as merged_prs,
                COALESCE(SUM(CASE WHEN pr_status = 'closed' THEN 1 ELSE 0 END), 0) as closed_prs,
                COALESCE(SUM(CASE WHEN review_status = 'pending' THEN 1 ELSE 0 END), 0) as pending_reviews,
                COALESCE(SUM(CASE WHEN review_status = 'approved' THEN 1 ELSE 0 END), 0) as approved_reviews,
                COALESCE(SUM(CASE WHEN review_status = 'changes_requested' THEN 1 ELSE 0 END), 0) as changes_requested,
                COALESCE(SUM(CASE WHEN review_status = 'fixed' THEN 1 ELSE 0 END), 0) as fixed_reviews
            FROM pr_reviews WHERE trigger_id = ?
        """,
            (trigger_id,),
        )
        row = cursor.fetchone()
        return (
            dict(row)
            if row
            else {
                "total_prs": 0,
                "open_prs": 0,
                "merged_prs": 0,
                "closed_prs": 0,
                "pending_reviews": 0,
                "approved_reviews": 0,
                "changes_requested": 0,
                "fixed_reviews": 0,
            }
        )


def get_all_pr_reviews(limit: int = 100, offset: int = 0) -> List[dict]:
    """Get all PR reviews with pagination."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT pr.*, t.name as trigger_name
            FROM pr_reviews pr
            LEFT JOIN triggers t ON pr.trigger_id = t.id
            ORDER BY pr.updated_at DESC
            LIMIT ? OFFSET ?
        """,
            (limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_pr_review(review_id: int) -> bool:
    """Delete a PR review record. Returns True on success."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM pr_reviews WHERE id = ?", (review_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_pr_review_history(trigger_id: str = "bot-pr-review", days: int = 30) -> List[dict]:
    """Get PR activity grouped by date for time-series visualization."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT date(created_at) as date,
                   COUNT(*) as created,
                   SUM(CASE WHEN pr_status = 'merged' THEN 1 ELSE 0 END) as merged,
                   SUM(CASE WHEN pr_status = 'closed' THEN 1 ELSE 0 END) as closed
            FROM pr_reviews
            WHERE trigger_id = ?
              AND created_at >= date('now', ? || ' days')
            GROUP BY date(created_at)
            ORDER BY date ASC
        """,
            (trigger_id, -days),
        )
        return [dict(row) for row in cursor.fetchall()]
