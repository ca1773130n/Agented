"""Seed data and startup functions for Agented.

This module contains seed data (preset MCP servers) and startup seeding
functions that were previously mixed into migrations.py. Separating seeds
from migrations follows the industry-standard pattern (cf. Django fixtures,
Rails db/seeds.rb) and keeps the migration file as a pure schema-evolution
record.

Functions:
    seed_predefined_triggers  -- Insert/update predefined triggers on startup.
    seed_preset_mcp_servers   -- Insert/update preset MCP server definitions.
    migrate_existing_paths    -- Create symlinks for paths missing them.
    auto_register_project_root -- Auto-register project root for security trigger.
"""

import logging
import sqlite3

import app.config as config

from .connection import get_connection
from .ids import _get_unique_mcp_server_id
from .triggers import PREDEFINED_TRIGGER_ID, PREDEFINED_TRIGGERS

logger = logging.getLogger(__name__)

# =============================================================================
# Preset MCP server definitions
# =============================================================================

PRESET_MCP_SERVERS = [
    {
        "name": "context7",
        "display_name": "Context7",
        "description": "Up-to-date code documentation for LLMs",
        "category": "documentation",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "@upstash/context7-mcp"]',
        "env_json": "{}",
        "is_preset": 1,
        "icon": "book",
        "npm_package": "@upstash/context7-mcp",
        "documentation_url": "https://github.com/upstash/context7",
    },
    {
        "name": "playwright",
        "display_name": "Playwright",
        "description": "Browser automation via structured accessibility trees",
        "category": "testing",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "@playwright/mcp@latest"]',
        "env_json": "{}",
        "is_preset": 1,
        "icon": "globe",
        "npm_package": "@playwright/mcp",
        "documentation_url": "https://github.com/microsoft/playwright-mcp",
    },
    {
        "name": "github",
        "display_name": "GitHub",
        "description": "GitHub API -- issues, PRs, repos, search",
        "category": "vcs",
        "server_type": "http",
        "command": None,
        "args": "[]",
        "env_json": "{}",
        "url": "https://api.githubcopilot.com/mcp/",
        "is_preset": 1,
        "icon": "git-branch",
        "npm_package": "@modelcontextprotocol/server-github",
        "documentation_url": "https://github.com/github/github-mcp-server",
    },
    {
        "name": "chrome-devtools",
        "display_name": "Chrome DevTools",
        "description": "Chrome DevTools for AI agents -- inspect, debug, profile",
        "category": "debugging",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "chrome-devtools-mcp@latest"]',
        "env_json": "{}",
        "is_preset": 1,
        "icon": "chrome",
        "npm_package": "chrome-devtools-mcp",
        "documentation_url": "https://github.com/nichochar/chrome-devtools-mcp",
    },
    {
        "name": "serena",
        "display_name": "Serena",
        "description": "Context-aware code refactoring engine",
        "category": "development",
        "server_type": "stdio",
        "command": "uvx",
        "args": '["--from", "git+https://github.com/oraios/serena", "serena", "start-mcp-server"]',
        "env_json": "{}",
        "is_preset": 1,
        "icon": "code",
        "npm_package": None,
        "documentation_url": "https://github.com/oraios/serena",
    },
    {
        "name": "jira",
        "display_name": "Jira",
        "description": "Atlassian Jira -- issues, projects, JQL search",
        "category": "project-management",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "@aashari/mcp-server-atlassian-jira"]',
        "env_json": '{"JIRA_URL": "", "JIRA_EMAIL": "", "JIRA_API_TOKEN": ""}',
        "is_preset": 1,
        "icon": "clipboard",
        "npm_package": "@aashari/mcp-server-atlassian-jira",
        "documentation_url": "https://github.com/aashari/mcp-server-atlassian-jira",
    },
    {
        "name": "linear",
        "display_name": "Linear",
        "description": "Linear issue tracking integration",
        "category": "project-management",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "@mcp-devtools/linear"]',
        "env_json": '{"LINEAR_API_KEY": ""}',
        "is_preset": 1,
        "icon": "zap",
        "npm_package": "@mcp-devtools/linear",
        "documentation_url": "https://linear.app",
    },
    {
        "name": "slack",
        "display_name": "Slack",
        "description": "Slack workspace interaction -- channels, messages, users",
        "category": "communication",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "@modelcontextprotocol/server-slack"]',
        "env_json": '{"SLACK_BOT_TOKEN": "", "SLACK_TEAM_ID": ""}',
        "is_preset": 1,
        "icon": "message-square",
        "npm_package": "@modelcontextprotocol/server-slack",
        "documentation_url": "https://github.com/modelcontextprotocol/servers",
    },
    {
        "name": "telegram",
        "display_name": "Telegram",
        "description": "Telegram bot messaging and channel interaction",
        "category": "communication",
        "server_type": "stdio",
        "command": "npx",
        "args": '["-y", "@iqai/mcp-telegram"]',
        "env_json": '{"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}',
        "is_preset": 1,
        "icon": "send",
        "npm_package": "@iqai/mcp-telegram",
        "documentation_url": "https://github.com/IQAIcom/mcp-telegram",
    },
]


# =============================================================================
# Seeding
# =============================================================================


def seed_predefined_triggers():
    """Insert all predefined triggers if they don't exist, or update if changed."""
    with get_connection() as conn:
        for trigger_def in PREDEFINED_TRIGGERS:
            cursor = conn.execute(
                "SELECT id, prompt_template, trigger_source, match_field_path, match_field_value, text_field_path FROM triggers WHERE id = ?",
                (trigger_def["id"],),
            )
            row = cursor.fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO triggers (id, name, group_id, detection_keyword, prompt_template, backend_type,
                                          trigger_source, match_field_path, match_field_value, text_field_path, is_predefined)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        trigger_def["id"],
                        trigger_def["name"],
                        trigger_def["group_id"],
                        trigger_def["detection_keyword"],
                        trigger_def["prompt_template"],
                        trigger_def["backend_type"],
                        trigger_def["trigger_source"],
                        trigger_def.get("match_field_path"),
                        trigger_def.get("match_field_value"),
                        trigger_def.get("text_field_path", "text"),
                        trigger_def["is_predefined"],
                    ),
                )
                print(f"Seeded predefined trigger: {trigger_def['name']} ({trigger_def['id']})")
            else:
                # Update if any configurable fields changed
                updates = []
                values = []
                if row["prompt_template"] != trigger_def["prompt_template"]:
                    updates.append("prompt_template = ?")
                    values.append(trigger_def["prompt_template"])
                if row["trigger_source"] != trigger_def["trigger_source"]:
                    updates.append("trigger_source = ?")
                    values.append(trigger_def["trigger_source"])
                if row["match_field_path"] != trigger_def.get("match_field_path"):
                    updates.append("match_field_path = ?")
                    values.append(trigger_def.get("match_field_path"))
                if row["match_field_value"] != trigger_def.get("match_field_value"):
                    updates.append("match_field_value = ?")
                    values.append(trigger_def.get("match_field_value"))
                if row["text_field_path"] != trigger_def.get("text_field_path", "text"):
                    updates.append("text_field_path = ?")
                    values.append(trigger_def.get("text_field_path", "text"))
                if updates:
                    values.append(trigger_def["id"])
                    conn.execute(f"UPDATE triggers SET {', '.join(updates)} WHERE id = ?", values)
                    print(f"Updated predefined trigger: {trigger_def['id']}")
        conn.commit()


def seed_preset_mcp_servers():
    """Insert/update preset MCP servers. Idempotent -- safe to call on every startup."""
    with get_connection() as conn:
        for preset in PRESET_MCP_SERVERS:
            existing = conn.execute(
                "SELECT id FROM mcp_servers WHERE name = ? AND is_preset = 1",
                (preset["name"],),
            ).fetchone()
            if existing:
                # Update existing preset to keep definitions current
                conn.execute(
                    """UPDATE mcp_servers SET
                        display_name=?, description=?, category=?, server_type=?,
                        command=?, args=?, env_json=?, url=?, icon=?,
                        npm_package=?, documentation_url=?, headers_json='{}',
                        timeout_ms=30000, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?""",
                    (
                        preset["display_name"],
                        preset["description"],
                        preset["category"],
                        preset["server_type"],
                        preset.get("command"),
                        preset.get("args", "[]"),
                        preset.get("env_json", "{}"),
                        preset.get("url"),
                        preset.get("icon"),
                        preset.get("npm_package"),
                        preset.get("documentation_url"),
                        existing["id"],
                    ),
                )
            else:
                # Insert new preset
                server_id = _get_unique_mcp_server_id(conn)
                conn.execute(
                    """INSERT INTO mcp_servers
                        (id, name, display_name, description, category, server_type,
                         command, args, env_json, url, is_preset, icon,
                         npm_package, documentation_url, headers_json, timeout_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, '{}', 30000)""",
                    (
                        server_id,
                        preset["name"],
                        preset["display_name"],
                        preset["description"],
                        preset["category"],
                        preset["server_type"],
                        preset.get("command"),
                        preset.get("args", "[]"),
                        preset.get("env_json", "{}"),
                        preset.get("url"),
                        preset.get("icon"),
                        preset.get("npm_package"),
                        preset.get("documentation_url"),
                    ),
                )
                logger.info("Seeded preset MCP server: %s (%s)", preset["display_name"], server_id)
        conn.commit()


# =============================================================================
# Path migration helpers
# =============================================================================


def migrate_existing_paths():
    """Create symlinks for any existing paths that don't have them."""
    # Import lazily to avoid circular dependency with database.py during transition
    from app.database import _create_symlink, _generate_symlink_name

    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, trigger_id, local_project_path FROM project_paths WHERE symlink_name IS NULL"
        )
        rows = cursor.fetchall()

        for row in rows:
            path_id = row["id"]
            trigger_id = row["trigger_id"]
            local_path = row["local_project_path"]

            # Generate and create symlink
            symlink_name = _generate_symlink_name(trigger_id, local_path)
            if _create_symlink(symlink_name, local_path):
                conn.execute(
                    "UPDATE project_paths SET symlink_name = ? WHERE id = ?",
                    (symlink_name, path_id),
                )
                print(f"Migrated path {local_path} -> {symlink_name}")

        conn.commit()


def auto_register_project_root():
    """Auto-register the project root directory for the predefined security trigger."""
    # Import lazily to avoid circular dependency with database.py during transition
    from app.database import _create_symlink, _generate_symlink_name, _remove_symlink

    with get_connection() as conn:
        # Check if predefined trigger exists
        cursor = conn.execute("SELECT id FROM triggers WHERE id = ?", (PREDEFINED_TRIGGER_ID,))
        if cursor.fetchone() is None:
            return  # Trigger doesn't exist yet

        # Check if project root is already registered
        cursor = conn.execute(
            "SELECT id FROM project_paths WHERE trigger_id = ? AND local_project_path = ?",
            (PREDEFINED_TRIGGER_ID, config.PROJECT_ROOT),
        )
        if cursor.fetchone() is not None:
            return  # Already registered

        # Register project root
        symlink_name = _generate_symlink_name(PREDEFINED_TRIGGER_ID, config.PROJECT_ROOT)
        if _create_symlink(symlink_name, config.PROJECT_ROOT):
            try:
                conn.execute(
                    "INSERT INTO project_paths (trigger_id, local_project_path, symlink_name) VALUES (?, ?, ?)",
                    (PREDEFINED_TRIGGER_ID, config.PROJECT_ROOT, symlink_name),
                )
                conn.commit()
                print(f"Auto-registered project root for security trigger: {config.PROJECT_ROOT}")
            except sqlite3.IntegrityError:
                _remove_symlink(symlink_name)
