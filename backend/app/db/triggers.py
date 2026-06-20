"""Trigger CRUD operations.

Includes trigger management, path/symlink operations, execution logs,
and PR review records. This module exceeds 500 lines because execution_logs
and PR reviews are kept here for domain cohesion — triggers own their
execution history and review records.
"""

import difflib
import logging
import sqlite3
from typing import List, Optional

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
    # --- BOT-01: Dependency Vulnerability Scanner (scheduled weekly) ---
    {
        "id": "bot-vuln-scan",
        "name": "Dependency Vulnerability Scanner",
        "group_id": 0,
        "detection_keyword": "",
        "prompt_template": "/vulnerability-scan {paths}",
        "backend_type": "claude",
        "trigger_source": "scheduled",
        "match_field_path": None,
        "match_field_value": None,
        "text_field_path": "text",
        "is_predefined": 1,
        "schedule_type": "weekly",
        "schedule_time": "02:00",
        "schedule_day": 1,
    },
    # --- BOT-02: Code Tour Generator (manual) ---
    {
        "id": "bot-code-tour",
        "name": "Code Tour Generator",
        "group_id": 0,
        "detection_keyword": "",
        "prompt_template": "/code-tour {paths}",
        "backend_type": "claude",
        "trigger_source": "manual",
        "match_field_path": None,
        "match_field_value": None,
        "text_field_path": "text",
        "is_predefined": 1,
    },
    # --- BOT-03: Test Coverage Gap Detector (github PR trigger) ---
    {
        "id": "bot-test-coverage",
        "name": "Test Coverage Gap Detector",
        "group_id": 0,
        "detection_keyword": "",
        "prompt_template": "/test-coverage-gaps {pr_url} {pr_title} {repo_full_name}",
        "backend_type": "claude",
        "trigger_source": "github",
        "match_field_path": None,
        "match_field_value": None,
        "text_field_path": "text",
        "is_predefined": 1,
    },
    # --- BOT-04: Incident Postmortem Assistant (manual) ---
    {
        "id": "bot-postmortem",
        "name": "Incident Postmortem Assistant",
        "group_id": 0,
        "detection_keyword": "",
        "prompt_template": "/incident-postmortem {message}",
        "backend_type": "claude",
        "trigger_source": "manual",
        "match_field_path": None,
        "match_field_value": None,
        "text_field_path": "text",
        "is_predefined": 1,
    },
    # --- BOT-05: Changelog Generator (manual) ---
    {
        "id": "bot-changelog",
        "name": "Changelog Generator",
        "group_id": 0,
        "detection_keyword": "",
        "prompt_template": "/generate-changelog {paths} {message}",
        "backend_type": "claude",
        "trigger_source": "manual",
        "match_field_path": None,
        "match_field_value": None,
        "text_field_path": "text",
        "is_predefined": 1,
    },
    # --- BOT-06: PR Summary (github PR trigger) ---
    {
        "id": "bot-pr-summary",
        "name": "PR Summary",
        "group_id": 0,
        "detection_keyword": "",
        "prompt_template": "/pr-summary {pr_url} {pr_title} {pr_author} {repo_full_name}",
        "backend_type": "claude",
        "trigger_source": "github",
        "match_field_path": None,
        "match_field_value": None,
        "text_field_path": "text",
        "is_predefined": 1,
    },
    # --- BOT-07: Execution Log Search (manual) ---
    {
        "id": "bot-log-search",
        "name": "Execution Log Search",
        "group_id": 0,
        "detection_keyword": "",
        "prompt_template": "/search-logs {message}",
        "backend_type": "claude",
        "trigger_source": "manual",
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


def create_trigger(
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
    dispatch_type: str = "bot",
    super_agent_id: str = None,
) -> Optional[str]:
    """Add a new trigger. Returns trigger_id (string) on success, None on failure."""
    if backend_type not in VALID_BACKENDS:
        logger.warning(
            "Invalid backend_type %r for trigger %r; falling back to 'claude'. Valid values: %s",
            backend_type,
            name,
            VALID_BACKENDS,
        )
        backend_type = "claude"
    if trigger_source not in VALID_TRIGGER_SOURCES:
        logger.warning(
            "Invalid trigger_source %r for trigger %r; falling back to 'webhook'. Valid values: %s",
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
                                      sigterm_grace_seconds, dispatch_type, super_agent_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    dispatch_type,
                    super_agent_id,
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
    dispatch_type: str = None,
    super_agent_id: str = None,
    auto_redispatch: int = None,
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
    if dispatch_type is not None:
        updates.append("dispatch_type = ?")
        values.append(dispatch_type)
    if super_agent_id is not None:
        if super_agent_id == "":
            updates.append("super_agent_id = NULL")
        else:
            updates.append("super_agent_id = ?")
            values.append(super_agent_id)
    if auto_redispatch is not None:
        updates.append("auto_redispatch = ?")
        values.append(1 if auto_redispatch else 0)

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


def get_all_triggers(limit=None, offset=0) -> List[dict]:
    """Get all triggers with their path counts."""
    with get_connection() as conn:
        query = """
            SELECT t.*, COUNT(p.id) as path_count
            FROM triggers t
            LEFT JOIN project_paths p ON t.id = p.trigger_id
            GROUP BY t.id
            ORDER BY t.is_predefined DESC, t.created_at ASC
        """
        params: list = []
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def count_all_triggers() -> int:
    """Count all triggers."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM triggers")
        return cursor.fetchone()[0]


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


def log_prompt_template_change(
    trigger_id: str, old_template: str, new_template: str, author: str = "system"
) -> bool:
    """Record a prompt template change in trigger_template_history. Returns True on success."""
    # Compute unified diff
    diff_lines = list(
        difflib.unified_diff(
            old_template.splitlines(keepends=True),
            new_template.splitlines(keepends=True),
            fromfile="previous",
            tofile="current",
            lineterm="",
        )
    )
    diff_text = "\n".join(diff_lines)

    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO trigger_template_history
                    (trigger_id, old_template, new_template, author, diff_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (trigger_id, old_template, new_template, author, diff_text),
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
            SELECT id, trigger_id, old_template, new_template, author, diff_text, changed_at
            FROM trigger_template_history
            WHERE trigger_id = ?
            ORDER BY changed_at DESC, id DESC
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


# --- Backward-compat re-exports (v0.7.3 split) ---
# These imports preserve the existing public API. New code should
# import from the focused module directly (e.g.
# `from app.db.execution_logs import create_execution_log`).
from .execution_logs import (  # noqa: F401, E402
    count_all_execution_logs,
    count_execution_logs_for_trigger,
    create_execution_log,
    delete_old_execution_logs,
    get_active_execution_count,
    get_all_execution_logs,
    get_execution_log,
    get_execution_logs_filtered,
    get_execution_logs_for_trigger,
    get_execution_stats,
    get_latest_execution_for_trigger,
    get_running_execution_for_trigger,
    mark_stale_executions_interrupted,
    update_execution_log,
    update_execution_status_cas,
)
from .pr_reviews import (  # noqa: F401, E402
    add_pr_review,
    delete_pr_review,
    get_all_pr_reviews,
    get_pr_review,
    get_pr_review_history,
    get_pr_review_learning_loop,
    get_pr_review_stats,
    get_pr_reviews_count,
    get_pr_reviews_for_trigger,
    update_pr_review,
)
from .trigger_paths import (  # noqa: F401, E402
    _create_symlink,
    _ensure_symlink_dir,
    _generate_symlink_name,
    _remove_symlink,
    _sanitize_name,
    add_github_repo,
    add_project_path,
    add_project_to_trigger,
    count_paths_for_trigger,
    get_paths_for_trigger,
    get_paths_for_trigger_detailed,
    get_symlink_paths_for_trigger,
    list_paths_for_trigger,
    remove_github_repo,
    remove_project_from_trigger,
    remove_project_path,
)
