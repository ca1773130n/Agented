"""Plugin persistence service — save parsed plugin data to database."""

import json
import logging
from pathlib import Path

from app.database import (
    add_agent,
    add_command,
    add_hook,
    add_plugin_component,
    add_rule,
)
from app.utils.plugin_format import parse_yaml_frontmatter

logger = logging.getLogger(__name__)


class PluginPersistenceService:
    """DB-writing methods for parsed plugin data."""

    @classmethod
    def _import_agents(cls, plugin_path: Path, plugin_id: str) -> int:
        """Import agent markdown files from agents/ directory.

        Returns:
            Number of agents successfully imported.
        """
        agents_dir = plugin_path / "agents"
        agent_files = cls._scan_directory(str(agents_dir), "*.md")
        count = 0

        for agent_file in agent_files:
            try:
                content = agent_file.read_text(encoding="utf-8")
                frontmatter, body = parse_yaml_frontmatter(content)

                name = frontmatter.get("name") or agent_file.stem
                description = frontmatter.get("description", "")

                # Skip if agent with this name already exists
                from ..database import get_connection

                with get_connection() as conn:
                    exists = conn.execute(
                        "SELECT 1 FROM agents WHERE name = ? LIMIT 1", (name,)
                    ).fetchone()
                if exists:
                    logger.debug("Agent '%s' already exists, skipping import", name)
                    continue

                # Extract goals from ## Goals section if present
                goals = cls._extract_section(body, "Goals")
                goals_json = json.dumps(goals) if goals else None

                # Extract context from ## Context section if present
                context = cls._extract_section_text(body, "Context")

                agent_id = add_agent(
                    name=name,
                    description=description,
                    system_prompt=body,
                    role=frontmatter.get("role") or cls._extract_section_text(body, "Role"),
                    goals=goals_json,
                    context=context,
                )
                if agent_id:
                    add_plugin_component(plugin_id, name, "agent", content=body)
                    count += 1
                    logger.info("Imported agent '%s' (%s)", name, agent_id)
                else:
                    logger.warning("Failed to create agent from '%s'", agent_file.name)
            except Exception as e:
                logger.warning("Error importing agent '%s': %s", agent_file.name, e)

        return count

    @classmethod
    def _import_skills(cls, plugin_path: Path, plugin_id: str) -> int:
        """Import skill directories from skills/ directory.

        Each skill is a subdirectory containing a SKILL.md file.

        Returns:
            Number of skills successfully imported.
        """
        skills_dir = plugin_path / "skills"
        if not skills_dir.is_dir():
            return 0

        count = 0
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                content = skill_md.read_text(encoding="utf-8")
                frontmatter, body = parse_yaml_frontmatter(content)

                name = frontmatter.get("name") or skill_dir.name

                comp_id = add_plugin_component(plugin_id, name, "skill", content=body)
                if comp_id:
                    count += 1
                    logger.info("Imported skill '%s'", name)
                else:
                    logger.warning("Failed to create skill from '%s'", skill_dir.name)
            except Exception as e:
                logger.warning("Error importing skill '%s': %s", skill_dir.name, e)

        return count

    @classmethod
    def _import_commands(cls, plugin_path: Path, plugin_id: str) -> int:
        """Import command markdown files from commands/ directory.

        Returns:
            Number of commands successfully imported.
        """
        commands_dir = plugin_path / "commands"
        command_files = cls._scan_directory(str(commands_dir), "*.md")
        count = 0

        for cmd_file in command_files:
            try:
                content = cmd_file.read_text(encoding="utf-8")
                frontmatter, body = parse_yaml_frontmatter(content)

                name = frontmatter.get("name") or cmd_file.stem
                description = frontmatter.get("description", "")
                parameters = frontmatter.get("parameters")
                arguments = json.dumps(parameters) if parameters else None

                cmd_id = add_command(
                    name=name,
                    description=description,
                    content=body,
                    arguments=arguments,
                )
                if cmd_id:
                    add_plugin_component(plugin_id, name, "command", content=body)
                    count += 1
                    logger.info("Imported command '%s'", name)
                else:
                    logger.warning("Failed to create command from '%s'", cmd_file.name)
            except Exception as e:
                logger.warning("Error importing command '%s': %s", cmd_file.name, e)

        return count

    @classmethod
    def _import_hooks_and_rules(cls, plugin_path: Path, plugin_id: str) -> tuple:
        """Import hooks and rules from hooks/hooks.json.

        Classifies entries as hooks or rules based on the script name:
        - Scripts starting with 'rule-' are classified as Hive rules.
        - All other entries are classified as Hive hooks.

        Returns:
            Tuple of (hooks_count, rules_count).
        """
        hooks_json_path = plugin_path / "hooks" / "hooks.json"
        if not hooks_json_path.exists():
            return 0, 0

        try:
            hooks_data = json.loads(hooks_json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not parse hooks.json: %s", e)
            return 0, 0

        # hooks.json can have top-level "hooks" key or be the hooks dict directly
        hooks_dict = hooks_data.get("hooks", hooks_data) if isinstance(hooks_data, dict) else {}

        hooks_count = 0
        rules_count = 0
        scripts_dir = plugin_path / "scripts"

        for event_type, entries in hooks_dict.items():
            if not isinstance(entries, list):
                continue

            for entry in entries:
                try:
                    # Each entry can have a "hooks" array with command references
                    hook_commands = entry.get("hooks", []) if isinstance(entry, dict) else []
                    matcher = entry.get("matcher", "") if isinstance(entry, dict) else ""

                    for hook_cmd in hook_commands:
                        if not isinstance(hook_cmd, dict):
                            continue

                        command_str = hook_cmd.get("command", "")
                        # Extract script name from command path
                        script_name = cls._extract_script_name(command_str)

                        # Read script content if available
                        script_content = cls._read_script_content(scripts_dir, script_name)

                        # Classify: rule- prefix -> rule, else -> hook
                        if script_name.startswith("rule-"):
                            rule_type = cls._RULE_EVENT_MAP.get(event_type, "validation")
                            rule_name = script_name.replace("rule-", "").replace(".sh", "")
                            rule_id = add_rule(
                                name=rule_name,
                                rule_type=rule_type,
                                description=f"Imported from {event_type} hook",
                                condition=matcher if matcher else None,
                                action=script_content,
                            )
                            if rule_id:
                                add_plugin_component(
                                    plugin_id, rule_name, "rule", content=script_content
                                )
                                rules_count += 1
                                logger.info("Imported rule '%s' (type=%s)", rule_name, rule_type)
                        else:
                            hook_name = script_name.replace(".sh", "")
                            hook_id = add_hook(
                                name=hook_name or f"hook-{event_type.lower()}",
                                event=event_type,
                                description="Imported from hooks.json",
                                content=script_content,
                            )
                            if hook_id:
                                add_plugin_component(
                                    plugin_id, hook_name, "hook", content=script_content
                                )
                                hooks_count += 1
                                logger.info("Imported hook '%s' (event=%s)", hook_name, event_type)

                    # Handle entries that are direct commands (no nested hooks array)
                    if not hook_commands and isinstance(entry, dict):
                        command_str = entry.get("command", "")
                        if command_str:
                            script_name = cls._extract_script_name(command_str)
                            script_content = cls._read_script_content(scripts_dir, script_name)
                            hook_name = (
                                script_name.replace(".sh", "") or f"hook-{event_type.lower()}"
                            )
                            hook_id = add_hook(
                                name=hook_name,
                                event=event_type,
                                description="Imported from hooks.json",
                                content=script_content,
                            )
                            if hook_id:
                                add_plugin_component(
                                    plugin_id, hook_name, "hook", content=script_content
                                )
                                hooks_count += 1

                except Exception as e:
                    logger.warning("Error importing hook entry for event '%s': %s", event_type, e)

        return hooks_count, rules_count
