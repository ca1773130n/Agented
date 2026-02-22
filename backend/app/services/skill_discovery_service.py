"""Skill discovery service — project, global, and plugin skill scanning."""

import json
import logging
import os
from http import HTTPStatus
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

from app.config import PROJECT_ROOT

from ..database import (
    get_all_triggers,
    get_paths_for_trigger,
    get_setting,
)

# Example webapp directory for skills playground testing
PLAYGROUND_WEBAPP_DIR = os.path.join(PROJECT_ROOT, "examples", "playground-webapp")


def get_playground_working_dir() -> str:
    """Get the working directory for skills playground.

    Checks for:
    1. SKILLS_PLAYGROUND_CWD environment variable
    2. skills_playground_cwd setting in database
    3. Falls back to example playground-webapp if it exists
    4. Falls back to PROJECT_ROOT
    """
    # Check environment variable first
    env_cwd = os.environ.get("SKILLS_PLAYGROUND_CWD")
    if env_cwd and os.path.isdir(env_cwd):
        return env_cwd

    # Check database setting
    try:
        db_setting = get_setting("skills_playground_cwd")
        if db_setting and os.path.isdir(db_setting):
            return db_setting
    except Exception as e:
        logger.debug("Skill playground setting: %s", e)

    # Use example webapp if it exists
    if os.path.isdir(PLAYGROUND_WEBAPP_DIR):
        return PLAYGROUND_WEBAPP_DIR

    # Fall back to project root
    return PROJECT_ROOT


class SkillDiscoveryService:
    """Service for discovering skills from filesystem and plugins."""

    @classmethod
    def discover_all_skills(
        cls, trigger_id: Optional[str] = None, paths: Optional[List[str]] = None
    ) -> List[dict]:
        """Discover skills and commands from all sources.

        Scans:
        1. Project .claude/skills/ directories
        2. Global ~/.claude/skills/ directory
        3. Plugin skills: ~/.claude/plugins/marketplaces/*/plugins/*/skills/*/SKILL.md
        4. Plugin commands: ~/.claude/plugins/marketplaces/*/plugins/*/commands/*.md

        Plugin items are prefixed with plugin name (e.g., pr-review-toolkit:review-pr).

        Args:
            trigger_id: If provided, scan paths registered to this trigger
            paths: If provided, scan these specific paths
        """
        scan_paths = set()

        # Always include project root
        scan_paths.add(PROJECT_ROOT)

        if trigger_id:
            # Get paths from specified trigger
            trigger_paths = get_paths_for_trigger(trigger_id)
            scan_paths.update(trigger_paths)
        elif paths:
            # Use provided paths
            scan_paths.update(paths)
        else:
            # Scan all registered trigger paths
            triggers = get_all_triggers()
            for trigger_item in triggers:
                trigger_paths = get_paths_for_trigger(trigger_item["id"])
                scan_paths.update(trigger_paths)

        skills = []
        seen_names = set()

        # 1. Scan project-based skills directories
        for base_path in scan_paths:
            if not base_path or not os.path.isdir(base_path):
                continue
            skills_dir = os.path.join(base_path, ".claude", "skills")
            if not os.path.isdir(skills_dir):
                continue

            for skill_name in os.listdir(skills_dir):
                skill_path = os.path.join(skills_dir, skill_name)
                if not os.path.isdir(skill_path):
                    continue

                skill_md_path = os.path.join(skill_path, "SKILL.md")
                if not os.path.isfile(skill_md_path):
                    continue

                skill_info = cls._parse_skill_file(skill_md_path, skill_name)
                if skill_info and skill_info["name"] not in seen_names:
                    skill_info["source_path"] = skill_path
                    skills.append(skill_info)
                    seen_names.add(skill_info["name"])

        # 2. Scan global ~/.claude/skills/ directory
        global_skills_dir = Path.home() / ".claude" / "skills"
        if global_skills_dir.is_dir():
            for skill_dir in sorted(global_skills_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue

                skill_md_path = skill_dir / "SKILL.md"
                if not skill_md_path.is_file():
                    continue

                skill_info = cls._parse_skill_file(str(skill_md_path), skill_dir.name)
                if skill_info and skill_info["name"] not in seen_names:
                    skill_info["source_path"] = str(skill_dir)
                    skills.append(skill_info)
                    seen_names.add(skill_info["name"])

        # 3. Scan user-scoped plugins from ~/.claude/plugins/installed_plugins.json
        # Only user-scoped plugins are available in Claude CLI headless mode
        installed_plugins_path = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
        if installed_plugins_path.is_file():
            try:
                with open(installed_plugins_path, "r", encoding="utf-8") as f:
                    installed_data = json.load(f)

                plugins = installed_data.get("plugins", {})
                for plugin_key, installations in plugins.items():
                    # plugin_key format: "plugin-name@marketplace-name"
                    plugin_name = plugin_key.split("@")[0]

                    for installation in installations:
                        # Only include user-scoped plugins (globally available)
                        if installation.get("scope") != "user":
                            continue

                        install_path = Path(installation.get("installPath", ""))
                        if not install_path.is_dir():
                            continue

                        # 3a. Scan plugin skills
                        plugin_skills_dir = install_path / "skills"
                        if plugin_skills_dir.is_dir():
                            for skill_dir in sorted(plugin_skills_dir.iterdir()):
                                if not skill_dir.is_dir():
                                    continue

                                skill_md_path = skill_dir / "SKILL.md"
                                if not skill_md_path.is_file():
                                    continue

                                skill_info = cls._parse_skill_file(
                                    str(skill_md_path), skill_dir.name
                                )
                                if skill_info:
                                    # Plugin skills use format: plugin-name:skill-name
                                    prefixed_name = f"{plugin_name}:{skill_info['name']}"
                                    if prefixed_name not in seen_names:
                                        seen_names.add(prefixed_name)
                                        skills.append(
                                            {
                                                "name": prefixed_name,
                                                "description": skill_info.get("description", ""),
                                                "source_path": str(install_path),
                                            }
                                        )

                        # 3b. Scan plugin commands
                        plugin_commands_dir = install_path / "commands"
                        if plugin_commands_dir.is_dir():
                            for cmd_file in sorted(plugin_commands_dir.iterdir()):
                                if not cmd_file.is_file() or cmd_file.suffix != ".md":
                                    continue

                                cmd_info = cls._parse_skill_file(str(cmd_file), cmd_file.stem)
                                if cmd_info:
                                    # Plugin commands use format: plugin-name:command-name
                                    prefixed_name = f"{plugin_name}:{cmd_info['name']}"
                                    if prefixed_name not in seen_names:
                                        seen_names.add(prefixed_name)
                                        skills.append(
                                            {
                                                "name": prefixed_name,
                                                "description": cmd_info.get("description", ""),
                                                "source_path": str(install_path),
                                            }
                                        )
            except (json.JSONDecodeError, KeyError, TypeError):
                # If installed_plugins.json is invalid, skip plugin discovery
                pass

        return skills

    @classmethod
    def _parse_skill_file(cls, skill_md_path: str, default_name: str) -> Optional[dict]:
        """Parse a SKILL.md or agent markdown file to extract metadata.

        Returns all frontmatter fields plus computed defaults.
        """
        try:
            with open(skill_md_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse YAML frontmatter - returns all fields
            frontmatter = cls._parse_frontmatter(content)

            name = frontmatter.get("name", default_name)
            description = frontmatter.get("description", "")

            # If no frontmatter description, try to extract from content
            if not description:
                # Look for first paragraph as description
                lines = content.strip().split("\n")
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("---"):
                        description = line[:200]  # First 200 chars
                        break

            # Build result with all frontmatter fields plus defaults
            result = {
                "name": name,
                "description": description,
            }

            # Copy over additional agent/skill fields from frontmatter
            for field in [
                "role",
                "skills",
                "goals",
                "context",
                "triggers",
                "color",
                "icon",
                "model",
                "temperature",
                "tools",
                "autonomous",
                "allowed_tools",
                "lead",
                "members",
            ]:
                if field in frontmatter:
                    value = frontmatter[field]
                    # Handle comma-separated lists
                    if field in ["skills", "goals", "tools", "allowed_tools"]:
                        if isinstance(value, str) and "," in value:
                            value = [v.strip() for v in value.split(",") if v.strip()]
                    result[field] = value

            return result
        except Exception as e:
            logger.debug("Skill file parse: %s", e)
            return None

    @staticmethod
    def _parse_frontmatter(content: str) -> dict:
        """Parse YAML frontmatter from markdown content."""
        frontmatter = {}

        if not content.startswith("---"):
            return frontmatter

        try:
            end_idx = content.index("---", 3)
            yaml_content = content[3:end_idx].strip()

            for line in yaml_content.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    frontmatter[key.strip()] = value.strip().strip('"').strip("'")
        except ValueError:
            pass

        return frontmatter

    @classmethod
    def discover_cli_skills(cls, scan_paths: list[str]) -> list[dict]:
        """Discover skills and commands from filesystem paths and installed plugins.

        Returns skills with slash-prefixed names (e.g., /skill-name, /plugin:skill-name)
        suitable for CLI skill selection.
        """
        skills = []
        seen_names: set[str] = set()

        # 1. Scan project-based skills directories
        for base_path in scan_paths:
            skills_dir = Path(base_path) / ".claude" / "skills"
            if not skills_dir.is_dir():
                continue

            for skill_dir in sorted(skills_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue

                skill_md = skill_dir / "SKILL.md"
                if not skill_md.is_file():
                    continue

                parsed = cls._parse_frontmatter_from_file(str(skill_md))
                skill_name = parsed.get("name", skill_dir.name)
                slash_name = f"/{skill_name}"

                if slash_name not in seen_names:
                    seen_names.add(slash_name)
                    skills.append(
                        {
                            "name": slash_name,
                            "description": parsed.get("description", ""),
                            "source_path": str(base_path),
                        }
                    )

        # 2. Scan global ~/.claude/skills/ directory
        global_skills_dir = Path.home() / ".claude" / "skills"
        if global_skills_dir.is_dir():
            for skill_dir in sorted(global_skills_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue

                skill_md = skill_dir / "SKILL.md"
                if not skill_md.is_file():
                    continue

                parsed = cls._parse_frontmatter_from_file(str(skill_md))
                skill_name = parsed.get("name", skill_dir.name)
                slash_name = f"/{skill_name}"

                if slash_name not in seen_names:
                    seen_names.add(slash_name)
                    skills.append(
                        {
                            "name": slash_name,
                            "description": parsed.get("description", ""),
                            "source_path": str(global_skills_dir),
                        }
                    )

        # 3. Scan user-scoped plugins from ~/.claude/plugins/installed_plugins.json
        # Only user-scoped plugins are available in Claude CLI headless mode
        installed_plugins_path = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
        if installed_plugins_path.is_file():
            try:
                with open(installed_plugins_path, "r", encoding="utf-8") as f:
                    installed_data = json.load(f)

                plugins = installed_data.get("plugins", {})
                for plugin_key, installations in plugins.items():
                    # plugin_key format: "plugin-name@marketplace-name"
                    plugin_name = plugin_key.split("@")[0]

                    for installation in installations:
                        # Only include user-scoped plugins (globally available)
                        if installation.get("scope") != "user":
                            continue

                        install_path = Path(installation.get("installPath", ""))
                        if not install_path.is_dir():
                            continue

                        # 3a. Scan plugin skills
                        plugin_skills_dir = install_path / "skills"
                        if plugin_skills_dir.is_dir():
                            for skill_dir in sorted(plugin_skills_dir.iterdir()):
                                if not skill_dir.is_dir():
                                    continue

                                skill_md = skill_dir / "SKILL.md"
                                if not skill_md.is_file():
                                    continue

                                parsed = cls._parse_frontmatter_from_file(str(skill_md))
                                skill_name = parsed.get("name", skill_dir.name)
                                # Plugin skills use format: /plugin-name:skill-name
                                slash_name = f"/{plugin_name}:{skill_name}"

                                if slash_name not in seen_names:
                                    seen_names.add(slash_name)
                                    skills.append(
                                        {
                                            "name": slash_name,
                                            "description": parsed.get("description", ""),
                                            "source_path": str(install_path),
                                        }
                                    )

                        # 3b. Scan plugin commands
                        plugin_commands_dir = install_path / "commands"
                        if plugin_commands_dir.is_dir():
                            for cmd_file in sorted(plugin_commands_dir.iterdir()):
                                if not cmd_file.is_file() or cmd_file.suffix != ".md":
                                    continue

                                parsed = cls._parse_frontmatter_from_file(str(cmd_file))
                                # Command name is the filename without .md
                                cmd_name = parsed.get("name", cmd_file.stem)
                                # Plugin commands use format: /plugin-name:command-name
                                slash_name = f"/{plugin_name}:{cmd_name}"

                                if slash_name not in seen_names:
                                    seen_names.add(slash_name)
                                    skills.append(
                                        {
                                            "name": slash_name,
                                            "description": parsed.get("description", ""),
                                            "source_path": str(install_path),
                                        }
                                    )
            except (json.JSONDecodeError, KeyError, TypeError):
                # If installed_plugins.json is invalid, skip plugin discovery
                pass

        return skills

    @staticmethod
    def _parse_frontmatter_from_file(md_path: str) -> dict:
        """Parse YAML frontmatter from a markdown file to extract name and description."""
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Check for YAML frontmatter delimiters
            if not content.startswith("---"):
                return {}

            # Find the closing ---
            end_idx = content.find("---", 3)
            if end_idx == -1:
                return {}

            frontmatter = content[3:end_idx].strip()
            result = {}
            for line in frontmatter.split("\n"):
                line = line.strip()
                if ":" in line and not line.startswith("#"):
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key in ("name", "description") and value:
                        result[key] = value

            return result
        except Exception as e:
            logger.debug("Frontmatter parse: %s", e)
            return {}

    @classmethod
    def list_skills(cls, trigger_id: Optional[str] = None) -> Tuple[dict, HTTPStatus]:
        """List all discovered skills."""
        skills = cls.discover_all_skills(trigger_id=trigger_id)
        return {"skills": skills}, HTTPStatus.OK

    @classmethod
    def get_skill_detail(cls, skill_name: str) -> Tuple[dict, HTTPStatus]:
        """Get details for a specific skill."""
        skills = cls.discover_all_skills()
        for skill in skills:
            if skill["name"] == skill_name:
                return skill, HTTPStatus.OK
        return {"error": "Skill not found"}, HTTPStatus.NOT_FOUND
