"""Bot template CRUD operations and curated template seed data."""

import json
import logging
from typing import List, Optional

from .connection import get_connection
from .triggers import create_trigger, get_trigger_by_name

logger = logging.getLogger(__name__)


# =============================================================================
# Curated bot templates
# =============================================================================

CURATED_BOT_TEMPLATES = [
    {
        "slug": "pr-reviewer",
        "name": "PR Reviewer",
        "description": (
            "Automatically reviews pull requests when they are opened or updated. "
            "Analyzes code changes, identifies potential issues, and provides "
            "constructive feedback as PR comments."
        ),
        "category": "code-review",
        "icon": "git-pull-request",
        "config_json": json.dumps(
            {
                "name": "PR Reviewer",
                "prompt_template": (
                    "Review the following pull request thoroughly.\n\n"
                    "PR: {pr_url}\n"
                    "Title: {pr_title}\n"
                    "Author: {pr_author}\n\n"
                    "Analyze the code changes for:\n"
                    "1. Potential bugs or logic errors\n"
                    "2. Code style and best practices\n"
                    "3. Security concerns\n"
                    "4. Performance implications\n"
                    "5. Test coverage gaps\n\n"
                    "Provide constructive, actionable feedback."
                ),
                "backend_type": "claude",
                "trigger_source": "github",
                "model": None,
            }
        ),
        "sort_order": 1,
    },
    {
        "slug": "dependency-updater",
        "name": "Dependency Updater",
        "description": (
            "Runs on a schedule to check project dependencies for available updates. "
            "Identifies outdated packages, security vulnerabilities in dependencies, "
            "and suggests safe upgrade paths."
        ),
        "category": "dependency",
        "icon": "package",
        "config_json": json.dumps(
            {
                "name": "Dependency Updater",
                "prompt_template": (
                    "Check the project dependencies for updates and security issues.\n\n"
                    "Project paths:\n{paths}\n\n"
                    "Tasks:\n"
                    "1. Identify outdated dependencies\n"
                    "2. Check for known security vulnerabilities\n"
                    "3. Suggest safe upgrade paths\n"
                    "4. Flag any breaking changes in major version updates\n"
                    "5. Generate a summary report of recommended actions"
                ),
                "backend_type": "claude",
                "trigger_source": "scheduled",
                "model": None,
                "schedule_type": "weekly",
                "schedule_value": "monday",
            }
        ),
        "sort_order": 2,
    },
    {
        "slug": "security-scanner",
        "name": "Security Scanner",
        "description": (
            "Performs security audits on the codebase when triggered via webhook. "
            "Scans for common vulnerabilities, insecure patterns, hardcoded secrets, "
            "and provides remediation recommendations."
        ),
        "category": "security",
        "icon": "shield",
        "config_json": json.dumps(
            {
                "name": "Security Scanner",
                "prompt_template": (
                    "Perform a comprehensive security audit on the following project.\n\n"
                    "Project paths:\n{paths}\n\n"
                    "Scan for:\n"
                    "1. Hardcoded secrets, API keys, or credentials\n"
                    "2. SQL injection vulnerabilities\n"
                    "3. Cross-site scripting (XSS) risks\n"
                    "4. Insecure authentication patterns\n"
                    "5. Dependency vulnerabilities\n"
                    "6. Improper error handling that leaks information\n\n"
                    "Trigger message: {message}\n\n"
                    "Provide severity ratings and remediation steps for each finding."
                ),
                "backend_type": "claude",
                "trigger_source": "webhook",
                "model": None,
            }
        ),
        "sort_order": 3,
    },
    {
        "slug": "changelog-generator",
        "name": "Changelog Generator",
        "description": (
            "Generates formatted changelogs from recent commits and merged PRs. "
            "Categorizes changes by type (features, fixes, breaking changes) and "
            "produces release-ready documentation."
        ),
        "category": "changelog",
        "icon": "file-text",
        "config_json": json.dumps(
            {
                "name": "Changelog Generator",
                "prompt_template": (
                    "Generate a changelog for the project based on recent activity.\n\n"
                    "Project paths:\n{paths}\n\n"
                    "Instructions: {message}\n\n"
                    "Tasks:\n"
                    "1. Analyze recent git commits and merged PRs\n"
                    "2. Categorize changes: Features, Bug Fixes, Breaking Changes, "
                    "Documentation, Performance\n"
                    "3. Write clear, user-facing descriptions for each change\n"
                    "4. Follow Keep a Changelog format\n"
                    "5. Include contributor attribution where applicable"
                ),
                "backend_type": "claude",
                "trigger_source": "webhook",
                "model": None,
            }
        ),
        "sort_order": 4,
    },
    {
        "slug": "test-writer",
        "name": "Test Writer",
        "description": (
            "Analyzes source code and generates comprehensive test suites. "
            "Identifies untested code paths, edge cases, and creates tests "
            "following project conventions and testing best practices."
        ),
        "category": "testing",
        "icon": "check-circle",
        "config_json": json.dumps(
            {
                "name": "Test Writer",
                "prompt_template": (
                    "Generate tests for the specified code in the project.\n\n"
                    "Project paths:\n{paths}\n\n"
                    "Instructions: {message}\n\n"
                    "Tasks:\n"
                    "1. Analyze the source code and identify untested areas\n"
                    "2. Generate unit tests covering happy paths and edge cases\n"
                    "3. Include error handling and boundary condition tests\n"
                    "4. Follow the project's existing test conventions and framework\n"
                    "5. Ensure tests are isolated and deterministic"
                ),
                "backend_type": "claude",
                "trigger_source": "webhook",
                "model": None,
            }
        ),
        "sort_order": 5,
    },
]


# =============================================================================
# CRUD operations
# =============================================================================


def get_all_templates() -> List[dict]:
    """Get all published bot templates, sorted by sort_order."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM bot_templates WHERE is_published = 1 ORDER BY sort_order ASC"
        )
        return [dict(row) for row in cursor.fetchall()]


def get_template(template_id: str) -> Optional[dict]:
    """Get a single bot template by ID."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM bot_templates WHERE id = ?", (template_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_template_by_slug(slug: str) -> Optional[dict]:
    """Get a single bot template by slug."""
    with get_connection() as conn:
        cursor = conn.execute("SELECT * FROM bot_templates WHERE slug = ?", (slug,))
        row = cursor.fetchone()
        return dict(row) if row else None


def deploy_template(template_id: str) -> Optional[str]:
    """Deploy a bot template by creating a trigger from its config.

    Returns the new trigger_id on success, None on failure.
    """
    template = get_template(template_id)
    if not template:
        logger.warning("Template %s not found for deployment", template_id)
        return None

    try:
        config = json.loads(template["config_json"])
    except (json.JSONDecodeError, TypeError) as e:
        logger.error("Failed to parse config_json for template %s: %s", template_id, e)
        return None

    # Determine unique name
    base_name = config.get("name", template["name"])
    trigger_name = base_name

    # Check for name conflicts and append suffix if needed
    counter = 2
    while get_trigger_by_name(trigger_name) is not None:
        trigger_name = f"{base_name} ({counter})"
        counter += 1

    # Create the trigger via create_trigger() directly
    trigger_id = create_trigger(
        name=trigger_name,
        prompt_template=config.get("prompt_template", ""),
        backend_type=config.get("backend_type", "claude"),
        trigger_source=config.get("trigger_source", "webhook"),
        model=config.get("model"),
        schedule_type=config.get("schedule_type"),
    )

    if trigger_id:
        logger.info(
            "Deployed template %s as trigger %s (%s)", template_id, trigger_id, trigger_name
        )
    else:
        logger.error("Failed to deploy template %s", template_id)

    return trigger_id
