"""Plugin parser service — scan directories, read manifests, extract content."""

import json
import logging
from pathlib import Path
from typing import Optional

from app.database import (
    add_agent,
    add_command,
    add_hook,
    add_plugin,
    add_plugin_component,
    add_rule,
    add_team,
    add_team_member,
)

logger = logging.getLogger(__name__)


class PluginParserService:
    """Orchestrator + parsing helpers for plugin import."""

    # Claude Code event types that map to Agented rule entities
    _RULE_EVENT_MAP = {
        "PreToolUse": "pre_check",
        "PostToolUse": "post_check",
    }

    # Event types that are always hooks (not rules)
    _HOOK_EVENTS = {"PreToolUse", "PostToolUse", "Notification", "Stop", "SubagentStop"}

    @classmethod
    def import_plugin_directory(
        cls,
        plugin_dir: str,
        plugin_name: Optional[str] = None,
    ) -> dict:
        """Parse a Claude Code plugin directory and create Agented entities.

        Args:
            plugin_dir: Path to the plugin directory.
            plugin_name: Override name for the plugin. If not provided, reads
                from plugin.json manifest or uses directory name.

        Returns:
            Dict with plugin_id, plugin_name, and counts of imported entities.

        Raises:
            FileNotFoundError: If plugin_dir does not exist.
            NotADirectoryError: If plugin_dir is not a directory.
        """
        plugin_path = Path(plugin_dir)

        if not plugin_path.exists():
            raise FileNotFoundError(f"Plugin directory not found: {plugin_dir}")
        if not plugin_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {plugin_dir}")

        # Step 1: Read plugin.json manifest (optional)
        manifest = cls._read_plugin_manifest(plugin_path)
        name = plugin_name or manifest.get("name") or plugin_path.name
        description = manifest.get("description", "")
        version = manifest.get("version", "1.0.0")

        # Step 2: Create Agented plugin record
        plugin_id = add_plugin(
            name=name,
            description=description,
            version=version,
            status="imported",
        )
        if not plugin_id:
            logger.error("Failed to create plugin record for '%s'", name)
            return {
                "plugin_id": None,
                "plugin_name": name,
                "agents_imported": 0,
                "skills_imported": 0,
                "commands_imported": 0,
                "hooks_imported": 0,
                "rules_imported": 0,
            }

        # Step 3: Import agents
        agents_count = cls._import_agents(plugin_path, plugin_id)

        # Step 4: Import skills
        skills_count = cls._import_skills(plugin_path, plugin_id)

        # Step 5: Import commands
        commands_count = cls._import_commands(plugin_path, plugin_id)

        # Step 6: Import hooks and rules from hooks.json
        hooks_count, rules_count = cls._import_hooks_and_rules(plugin_path, plugin_id)

        return {
            "plugin_id": plugin_id,
            "plugin_name": name,
            "agents_imported": agents_count,
            "skills_imported": skills_count,
            "commands_imported": commands_count,
            "hooks_imported": hooks_count,
            "rules_imported": rules_count,
        }

    @classmethod
    def import_from_agented_package(cls, package_dir: str) -> dict:
        """Import entities from a Agented package (agented.json manifest).

        Args:
            package_dir: Path to the Agented package directory containing agented.json.

        Returns:
            Dict with plugin_id, plugin_name, and counts of imported entities.

        Raises:
            FileNotFoundError: If package_dir or agented.json does not exist.
        """
        package_path = Path(package_dir)

        if not package_path.exists():
            raise FileNotFoundError(f"Package directory not found: {package_dir}")

        agented_json_path = package_path / "agented.json"
        if not agented_json_path.exists():
            raise FileNotFoundError(f"agented.json not found in: {package_dir}")

        try:
            manifest = json.loads(agented_json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to parse agented.json: %s", e)
            raise

        name = manifest.get("name", package_path.name)
        description = manifest.get("description", "")
        version = manifest.get("version", "1.0.0")

        # Create plugin record
        plugin_id = add_plugin(
            name=name,
            description=description,
            version=version,
            status="imported",
        )
        if not plugin_id:
            logger.error("Failed to create plugin record for Agented package '%s'", name)
            return {
                "plugin_id": None,
                "plugin_name": name,
                "agents_imported": 0,
                "skills_imported": 0,
                "commands_imported": 0,
                "hooks_imported": 0,
                "rules_imported": 0,
            }

        agents_count = 0
        skills_count = 0
        commands_count = 0
        hooks_count = 0
        rules_count = 0

        # Import team if present
        team_data = manifest.get("team")
        team_id = None
        if team_data:
            team_id = add_team(
                name=team_data.get("name", name),
                description=team_data.get("description", ""),
                topology=team_data.get("topology"),
                topology_config=(
                    json.dumps(team_data["topology_config"])
                    if team_data.get("topology_config")
                    else None
                ),
                source="plugin_import",
            )

        # Import agents
        for agent_data in manifest.get("agents", []):
            try:
                agent_id = add_agent(
                    name=agent_data.get("name", "Unnamed Agent"),
                    description=agent_data.get("description"),
                    role=agent_data.get("role"),
                    goals=(json.dumps(agent_data["goals"]) if agent_data.get("goals") else None),
                    context=agent_data.get("context"),
                    system_prompt=agent_data.get("system_prompt"),
                    backend_type=agent_data.get("backend_type", "claude"),
                )
                if agent_id:
                    add_plugin_component(plugin_id, agent_data.get("name", "agent"), "agent")
                    agents_count += 1
                    # Add to team if team was created
                    if team_id:
                        add_team_member(team_id, agent_id, "agent")
            except Exception as e:
                logger.warning("Failed to import agent '%s': %s", agent_data.get("name"), e)

        # Import skills
        for skill_data in manifest.get("skills", []):
            try:
                add_plugin_component(
                    plugin_id,
                    skill_data.get("name", "skill"),
                    "skill",
                    content=skill_data.get("content"),
                )
                skills_count += 1
            except Exception as e:
                logger.warning("Failed to import skill '%s': %s", skill_data.get("name"), e)

        # Import commands
        for cmd_data in manifest.get("commands", []):
            try:
                cmd_id = add_command(
                    name=cmd_data.get("name", "unnamed-command"),
                    description=cmd_data.get("description"),
                    content=cmd_data.get("content"),
                    arguments=(
                        json.dumps(cmd_data["arguments"]) if cmd_data.get("arguments") else None
                    ),
                )
                if cmd_id:
                    add_plugin_component(plugin_id, cmd_data.get("name", "command"), "command")
                    commands_count += 1
            except Exception as e:
                logger.warning("Failed to import command '%s': %s", cmd_data.get("name"), e)

        # Import hooks
        for hook_data in manifest.get("hooks", []):
            try:
                hook_id = add_hook(
                    name=hook_data.get("name", "unnamed-hook"),
                    event=hook_data.get("event", "PreToolUse"),
                    description=hook_data.get("description"),
                    content=hook_data.get("content"),
                )
                if hook_id:
                    add_plugin_component(plugin_id, hook_data.get("name", "hook"), "hook")
                    hooks_count += 1
            except Exception as e:
                logger.warning("Failed to import hook '%s': %s", hook_data.get("name"), e)

        # Import rules
        for rule_data in manifest.get("rules", []):
            try:
                rule_id = add_rule(
                    name=rule_data.get("name", "unnamed-rule"),
                    rule_type=rule_data.get("rule_type", "validation"),
                    description=rule_data.get("description"),
                    condition=rule_data.get("condition"),
                    action=rule_data.get("action"),
                )
                if rule_id:
                    add_plugin_component(plugin_id, rule_data.get("name", "rule"), "rule")
                    rules_count += 1
            except Exception as e:
                logger.warning("Failed to import rule '%s': %s", rule_data.get("name"), e)

        return {
            "plugin_id": plugin_id,
            "plugin_name": name,
            "agents_imported": agents_count,
            "skills_imported": skills_count,
            "commands_imported": commands_count,
            "hooks_imported": hooks_count,
            "rules_imported": rules_count,
        }

    # -------------------------------------------------------------------------
    # Parsing helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _scan_directory(dir_path: str, pattern: str) -> list:
        """Return sorted list of files matching glob pattern in directory.

        Args:
            dir_path: Directory to scan.
            pattern: Glob pattern (e.g., '*.md').

        Returns:
            Sorted list of Path objects. Empty list if directory doesn't exist.
        """
        path = Path(dir_path)
        if not path.is_dir():
            return []
        return sorted(path.glob(pattern))

    @staticmethod
    def _read_plugin_manifest(plugin_path: Path) -> dict:
        """Read .claude-plugin/plugin.json if it exists.

        Returns:
            Parsed manifest dict, or empty dict if not found/invalid.
        """
        manifest_path = plugin_path / ".claude-plugin" / "plugin.json"
        if not manifest_path.exists():
            return {}

        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not parse plugin.json: %s", e)
            return {}

    @staticmethod
    def _extract_script_name(command_str: str) -> str:
        """Extract script filename from a command string.

        Handles patterns like:
        - '${CLAUDE_PLUGIN_ROOT}/scripts/lint-check.sh'
        - '/path/to/scripts/rule-validate.sh'
        - 'my-script.sh'

        Returns:
            Script filename (e.g., 'lint-check.sh'), or empty string if not found.
        """
        if not command_str:
            return ""
        # Take the last path component
        parts = command_str.replace("\\", "/").split("/")
        return parts[-1] if parts else ""

    @staticmethod
    def _read_script_content(scripts_dir: Path, script_name: str) -> str:
        """Read script file content if it exists.

        Args:
            scripts_dir: Path to the scripts/ directory.
            script_name: Filename of the script.

        Returns:
            Script content string, or empty string if not found.
        """
        if not script_name or not scripts_dir.is_dir():
            return ""

        script_path = scripts_dir / script_name
        if not script_path.exists():
            logger.warning("Script file not found: %s", script_path)
            return ""

        try:
            return script_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Could not read script '%s': %s", script_name, e)
            return ""

    @staticmethod
    def _extract_section(body: str, section_name: str) -> list:
        """Extract a markdown section as a list of items.

        Looks for ## Section Name and extracts bullet points as a list.

        Args:
            body: Markdown body text.
            section_name: Section heading to find (without ##).

        Returns:
            List of strings from bullet points, or empty list.
        """
        lines = body.split("\n")
        in_section = False
        items = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## "):
                if stripped == f"## {section_name}":
                    in_section = True
                    continue
                elif in_section:
                    break  # Hit next section
            if in_section and stripped.startswith(("- ", "* ", "1. ")):
                # Remove bullet prefix
                item = stripped.lstrip("-*0123456789. ").strip()
                if item:
                    items.append(item)

        return items

    @staticmethod
    def _extract_section_text(body: str, section_name: str) -> Optional[str]:
        """Extract a markdown section as raw text.

        Looks for ## Section Name and returns all text until the next ## heading.

        Args:
            body: Markdown body text.
            section_name: Section heading to find (without ##).

        Returns:
            Section text content, or None if section not found.
        """
        lines = body.split("\n")
        in_section = False
        section_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## "):
                if stripped == f"## {section_name}":
                    in_section = True
                    continue
                elif in_section:
                    break
            if in_section:
                section_lines.append(line)

        if not section_lines:
            return None

        result = "\n".join(section_lines).strip()
        return result if result else None
