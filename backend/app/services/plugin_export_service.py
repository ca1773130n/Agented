"""Plugin export service for assembling Hive team entities into plugin packages.

Supports two export formats:
- Claude Code plugin: directory structure with .claude-plugin/plugin.json, agents/, skills/, etc.
- Hive package: hive.json + Claude Code plugin structure for bidirectional compatibility.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from app.database import (
    add_plugin_export,
    add_sync_state,
    get_agent,
    get_command,
    get_hook,
    get_rule,
    get_team_agent_assignments,
    get_team_detail,
    get_team_members,
    get_user_skill,
    update_plugin_export,
)
from app.utils.plugin_format import (
    content_hash,
    generate_agent_md,
    generate_command_md,
    generate_hive_manifest,
    generate_hooks_json,
    generate_plugin_manifest,
    generate_rule_script,
    generate_skill_md,
)

log = logging.getLogger(__name__)


class ExportService:
    """Service for exporting Hive teams as Claude Code plugins or Hive packages."""

    @staticmethod
    def export_as_claude_plugin(team_id: str, output_dir: str, plugin_id: str = None) -> dict:
        """Export a team as a Claude Code plugin directory structure.

        Args:
            team_id: The team ID to export.
            output_dir: Base directory to write the plugin into.
            plugin_id: Optional plugin ID for DB tracking.

        Returns:
            Summary dict with export_path, plugin_name, and entity counts.

        Raises:
            ValueError: If team not found.
        """
        entities = ExportService._load_team_entities(team_id)
        team = entities["team"]
        agents = entities["agents"]
        skills = entities["skills"]
        commands = entities["commands"]
        hooks = entities["hooks"]
        rules = entities["rules"]

        plugin_name = ExportService._slugify(team.get("name", "unnamed"))
        base = Path(output_dir)

        # Create .claude-plugin directory with plugin.json
        plugin_dir = base / ".claude-plugin"
        os.makedirs(plugin_dir, exist_ok=True)
        manifest = generate_plugin_manifest(team, agents, skills, commands, hooks)
        _write_json(plugin_dir / "plugin.json", manifest)

        # Write agents
        if agents:
            agents_dir = base / "agents"
            os.makedirs(agents_dir, exist_ok=True)
            for agent in agents:
                agent_slug = ExportService._slugify(agent.get("name", "agent"))
                md_content = generate_agent_md(agent)
                _write_text(agents_dir / f"{agent_slug}.md", md_content)

        # Write skills
        if skills:
            for skill in skills:
                skill_name = skill.get("skill_name", skill.get("name", "skill"))
                skill_slug = ExportService._slugify(skill_name)
                skill_dir = base / "skills" / skill_slug
                os.makedirs(skill_dir, exist_ok=True)
                md_content = generate_skill_md(skill)
                _write_text(skill_dir / "SKILL.md", md_content)

        # Write commands
        if commands:
            commands_dir = base / "commands"
            os.makedirs(commands_dir, exist_ok=True)
            for command in commands:
                cmd_slug = ExportService._slugify(command.get("name", "command"))
                md_content = generate_command_md(command)
                _write_text(commands_dir / f"{cmd_slug}.md", md_content)

        # Write hooks and rule scripts
        if hooks or rules:
            hooks_dir = base / "hooks"
            scripts_dir = base / "scripts"
            os.makedirs(hooks_dir, exist_ok=True)
            os.makedirs(scripts_dir, exist_ok=True)

            hooks_config, scripts = generate_hooks_json(hooks, rules)
            _write_json(hooks_dir / "hooks.json", hooks_config)

            for script_name, script_content in scripts.items():
                script_path = scripts_dir / script_name
                _write_text(script_path, script_content)
                os.chmod(script_path, 0o755)

        # Record export in DB if plugin_id provided
        export_id = None
        if plugin_id:
            export_id = add_plugin_export(
                plugin_id=plugin_id,
                team_id=team_id,
                export_format="claude",
                export_path=str(base),
                version="1.0.0",
            )
            if export_id:
                update_plugin_export(
                    export_id,
                    status="exported",
                    last_exported_at=datetime.now(timezone.utc).isoformat(),
                )
                # Record sync state for each entity
                ExportService._record_sync_states(
                    plugin_id, agents, skills, commands, hooks, rules, base
                )

        return {
            "export_path": str(base),
            "plugin_name": plugin_name,
            "agents": len(agents),
            "skills": len(skills),
            "commands": len(commands),
            "hooks": len(hooks),
            "rules": len(rules),
            "export_id": export_id,
        }

    @staticmethod
    def export_as_hive_package(team_id: str, output_dir: str, plugin_id: str = None) -> dict:
        """Export a team as a Hive package (hive.json + Claude Code plugin structure).

        Args:
            team_id: The team ID to export.
            output_dir: Base directory to write the package into.
            plugin_id: Optional plugin ID for DB tracking.

        Returns:
            Summary dict with export_path, plugin_name, and entity counts.

        Raises:
            ValueError: If team not found.
        """
        entities = ExportService._load_team_entities(team_id)

        # Generate hive.json with all entity data embedded
        hive_manifest = generate_hive_manifest(
            team=entities["team"],
            members=entities["members"],
            assignments=entities["assignments"],
            agents=entities["agents"],
            skills=entities["skills"],
            commands=entities["commands"],
            hooks=entities["hooks"],
            rules=entities["rules"],
        )

        base = Path(output_dir)
        os.makedirs(base, exist_ok=True)
        _write_json(base / "hive.json", hive_manifest)

        # Also generate the Claude Code plugin structure
        result = ExportService.export_as_claude_plugin(team_id, output_dir, plugin_id=None)

        # Record export in DB if plugin_id provided
        export_id = None
        if plugin_id:
            export_id = add_plugin_export(
                plugin_id=plugin_id,
                team_id=team_id,
                export_format="hive",
                export_path=str(base),
                version="1.0.0",
            )
            if export_id:
                update_plugin_export(
                    export_id,
                    status="exported",
                    last_exported_at=datetime.now(timezone.utc).isoformat(),
                )

        result["export_id"] = export_id
        result["format"] = "hive"
        return result

    @staticmethod
    def _load_team_entities(team_id: str) -> dict:
        """Load all entities for a team from the database.

        Returns dict with keys: team, members, assignments, agents, skills,
        commands, hooks, rules.
        """
        team = get_team_detail(team_id)
        if not team:
            raise ValueError(f"Team not found: {team_id}")

        members = get_team_members(team_id)
        assignments = get_team_agent_assignments(team_id)

        # Collect unique entities across all assignments
        seen_agents = {}
        seen_skills = {}
        seen_commands = {}
        seen_hooks = {}
        seen_rules = {}

        # Also include team member agents directly
        for member in members:
            agent_id = member.get("agent_id")
            if agent_id and agent_id not in seen_agents:
                agent = get_agent(agent_id)
                if agent:
                    seen_agents[agent_id] = agent
                else:
                    log.warning("Agent %s referenced in team member but not found in DB", agent_id)

        # Process assignments
        for assignment in assignments:
            entity_type = assignment.get("entity_type", "")
            entity_id = assignment.get("entity_id")

            if not entity_id:
                continue

            try:
                if entity_type == "skill":
                    if entity_id not in seen_skills:
                        # entity_id for skills is INTEGER in the DB
                        skill = get_user_skill(int(entity_id))
                        if skill:
                            seen_skills[entity_id] = skill
                        else:
                            log.warning(
                                "Skill %s referenced in assignment but not found", entity_id
                            )
                elif entity_type == "command":
                    if entity_id not in seen_commands:
                        command = get_command(int(entity_id))
                        if command:
                            seen_commands[entity_id] = command
                        else:
                            log.warning(
                                "Command %s referenced in assignment but not found", entity_id
                            )
                elif entity_type == "hook":
                    if entity_id not in seen_hooks:
                        hook = get_hook(int(entity_id))
                        if hook:
                            seen_hooks[entity_id] = hook
                        else:
                            log.warning("Hook %s referenced in assignment but not found", entity_id)
                elif entity_type == "rule":
                    if entity_id not in seen_rules:
                        rule = get_rule(int(entity_id))
                        if rule:
                            seen_rules[entity_id] = rule
                        else:
                            log.warning("Rule %s referenced in assignment but not found", entity_id)
            except (ValueError, TypeError) as e:
                log.warning("Error loading %s %s: %s", entity_type, entity_id, e)

        return {
            "team": team,
            "members": members,
            "assignments": assignments,
            "agents": list(seen_agents.values()),
            "skills": list(seen_skills.values()),
            "commands": list(seen_commands.values()),
            "hooks": list(seen_hooks.values()),
            "rules": list(seen_rules.values()),
        }

    @staticmethod
    def _slugify(name: str) -> str:
        """Convert a name to kebab-case suitable for file names."""
        slug = name.lower().strip()
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        slug = re.sub(r"-+", "-", slug)
        slug = slug.strip("-")
        return slug or "unnamed"

    @staticmethod
    def _record_sync_states(
        plugin_id: str,
        agents: list,
        skills: list,
        commands: list,
        hooks: list,
        rules: list,
        base: Path,
    ):
        """Record sync state entries for each exported entity."""
        for agent in agents:
            agent_id = agent.get("id", "")
            agent_slug = ExportService._slugify(agent.get("name", "agent"))
            file_path = str(base / "agents" / f"{agent_slug}.md")
            md = generate_agent_md(agent)
            add_sync_state(plugin_id, "agent", str(agent_id), file_path, content_hash(md), "export")

        for skill in skills:
            skill_id = skill.get("id", "")
            skill_name = skill.get("skill_name", skill.get("name", "skill"))
            skill_slug = ExportService._slugify(skill_name)
            file_path = str(base / "skills" / skill_slug / "SKILL.md")
            md = generate_skill_md(skill)
            add_sync_state(plugin_id, "skill", str(skill_id), file_path, content_hash(md), "export")

        for command in commands:
            cmd_id = command.get("id", "")
            cmd_slug = ExportService._slugify(command.get("name", "command"))
            file_path = str(base / "commands" / f"{cmd_slug}.md")
            md = generate_command_md(command)
            add_sync_state(plugin_id, "command", str(cmd_id), file_path, content_hash(md), "export")

        for hook in hooks:
            hook_id = hook.get("id", "")
            hook_slug = ExportService._slugify(hook.get("name", "hook"))
            file_path = str(base / "scripts" / f"{hook_slug}.sh")
            add_sync_state(plugin_id, "hook", str(hook_id), file_path, None, "export")

        for rule in rules:
            rule_id = rule.get("id", "")
            rule_slug = ExportService._slugify(rule.get("name", "rule"))
            file_path = str(base / "scripts" / f"{rule_slug}.sh")
            script = generate_rule_script(rule)
            add_sync_state(
                plugin_id, "rule", str(rule_id), file_path, content_hash(script), "export"
            )


# --- File writing helpers ---


def _write_json(path: Path, data: dict):
    """Write a dict as formatted JSON to a file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _write_text(path: Path, content: str):
    """Write text content to a file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
