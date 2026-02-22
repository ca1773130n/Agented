"""Skill marketplace service — marketplace load and deploy operations."""

import datetime
import json
import os
import subprocess
from http import HTTPStatus
from typing import Tuple

from ..database import (
    add_agent,
    add_plugin_component,
    add_team,
    add_team_member,
    add_user_skill,
    get_agent_by_name,
    get_marketplace,
    get_plugin_component_by_name,
    get_setting,
    get_team_by_name,
    get_user_skill_by_name,
)
from .skill_discovery_service import SkillDiscoveryService


class SkillMarketplaceService:
    """Service for marketplace load and deploy operations."""

    @classmethod
    def load_from_marketplace(cls) -> Tuple[dict, HTTPStatus]:
        """Load skills from the configured marketplace plugin.

        Fetches the plugin from the marketplace based on settings,
        parses the plugin.json, and imports skills into user skills.
        """
        # Get harness plugin settings
        marketplace_id = get_setting("harness_marketplace_id")
        plugin_name = get_setting("harness_plugin_name")

        if not marketplace_id or not plugin_name:
            return {
                "error": "Harness plugin not configured. Go to Settings > Harness Plugin to configure."
            }, HTTPStatus.BAD_REQUEST

        # Get marketplace info
        marketplace = get_marketplace(marketplace_id)
        if not marketplace:
            return {"error": "Configured marketplace not found"}, HTTPStatus.NOT_FOUND

        marketplace_url = marketplace.get("url", "")
        marketplace_type = marketplace.get("type", "git")

        if marketplace_type != "git" or "github.com" not in marketplace_url:
            return {
                "error": "Only GitHub-based marketplaces are currently supported"
            }, HTTPStatus.BAD_REQUEST

        # Clone/update the marketplace repo and fetch plugin
        try:
            # Create temp directory for clone
            import shutil
            import tempfile

            temp_dir = tempfile.mkdtemp(prefix="harness_marketplace_")

            try:
                # Clone the repository (shallow clone for speed)
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", marketplace_url, temp_dir],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if result.returncode != 0:
                    return {
                        "error": f"Failed to clone marketplace: {result.stderr}"
                    }, HTTPStatus.INTERNAL_SERVER_ERROR

                # Find the plugin directory
                plugin_dir = os.path.join(temp_dir, plugin_name)
                if not os.path.isdir(plugin_dir):
                    # Try plugins subdirectory
                    plugin_dir = os.path.join(temp_dir, "plugins", plugin_name)
                    if not os.path.isdir(plugin_dir):
                        return {
                            "error": f"Plugin '{plugin_name}' not found in marketplace"
                        }, HTTPStatus.NOT_FOUND

                # Read plugin.json
                plugin_json_path = os.path.join(plugin_dir, "plugin.json")
                if not os.path.isfile(plugin_json_path):
                    return {
                        "error": f"plugin.json not found in '{plugin_name}'"
                    }, HTTPStatus.NOT_FOUND

                with open(plugin_json_path, "r", encoding="utf-8") as f:
                    plugin_config = json.load(f)

                # Extract all components from plugin
                imported_skills = []
                imported_commands = []
                imported_hooks = []
                imported_agents = []

                # Use plugin_name as a pseudo plugin_id for component storage
                plugin_id = f"marketplace:{plugin_name}"

                # 1. Import skills
                skills_dir = os.path.join(plugin_dir, "skills")
                if os.path.isdir(skills_dir):
                    for skill_name in os.listdir(skills_dir):
                        skill_path = os.path.join(skills_dir, skill_name)
                        if not os.path.isdir(skill_path):
                            continue

                        skill_md_path = os.path.join(skill_path, "SKILL.md")
                        if not os.path.isfile(skill_md_path):
                            continue

                        skill_info = SkillDiscoveryService._parse_skill_file(
                            skill_md_path, skill_name
                        )
                        if skill_info:
                            full_skill_name = f"{plugin_name}:{skill_info['name']}"
                            existing = get_user_skill_by_name(full_skill_name)
                            if not existing:
                                skill_id = add_user_skill(
                                    skill_name=full_skill_name,
                                    skill_path=f"~/.claude/plugins/marketplace/{plugin_name}/skills/{skill_name}",
                                    description=skill_info.get("description", ""),
                                    enabled=1,
                                    selected_for_harness=1,
                                )
                                if skill_id:
                                    imported_skills.append(full_skill_name)

                # 2. Import commands
                commands_dir = os.path.join(plugin_dir, "commands")
                if os.path.isdir(commands_dir):
                    for cmd_file in os.listdir(commands_dir):
                        cmd_path = os.path.join(commands_dir, cmd_file)
                        if not os.path.isfile(cmd_path) or not cmd_file.endswith(".md"):
                            continue

                        cmd_name = cmd_file[:-3]  # Remove .md extension
                        cmd_info = SkillDiscoveryService._parse_skill_file(cmd_path, cmd_name)
                        if cmd_info:
                            full_cmd_name = f"{plugin_name}:{cmd_info['name']}"
                            # Store in plugin_components table
                            existing = get_plugin_component_by_name(
                                plugin_id, full_cmd_name, "command"
                            )
                            if not existing:
                                try:
                                    with open(cmd_path, "r", encoding="utf-8") as f:
                                        content = f.read()
                                    component_id = add_plugin_component(
                                        plugin_id=plugin_id,
                                        name=full_cmd_name,
                                        component_type="command",
                                        content=content,
                                    )
                                    if component_id:
                                        imported_commands.append(full_cmd_name)
                                except Exception:
                                    pass

                # 3. Import hooks
                hooks_dir = os.path.join(plugin_dir, "hooks")
                if os.path.isdir(hooks_dir):
                    for hook_file in os.listdir(hooks_dir):
                        hook_path = os.path.join(hooks_dir, hook_file)
                        if not os.path.isfile(hook_path):
                            continue

                        # Support both .md and .json hook files
                        if hook_file.endswith(".md"):
                            hook_name = hook_file[:-3]
                        elif hook_file.endswith(".json"):
                            hook_name = hook_file[:-5]
                        else:
                            continue

                        full_hook_name = f"{plugin_name}:{hook_name}"
                        existing = get_plugin_component_by_name(plugin_id, full_hook_name, "hook")
                        if not existing:
                            try:
                                with open(hook_path, "r", encoding="utf-8") as f:
                                    content = f.read()
                                component_id = add_plugin_component(
                                    plugin_id=plugin_id,
                                    name=full_hook_name,
                                    component_type="hook",
                                    content=content,
                                )
                                if component_id:
                                    imported_hooks.append(full_hook_name)
                            except Exception:
                                pass

                # 4. Import agents
                agents_dir = os.path.join(plugin_dir, "agents")
                if os.path.isdir(agents_dir):
                    for agent_file in os.listdir(agents_dir):
                        agent_path = os.path.join(agents_dir, agent_file)
                        if not os.path.isfile(agent_path) or not agent_file.endswith(".md"):
                            continue

                        agent_name = agent_file[:-3]  # Remove .md extension
                        agent_info = SkillDiscoveryService._parse_skill_file(agent_path, agent_name)
                        if agent_info:
                            full_agent_name = f"{plugin_name}:{agent_info['name']}"
                            existing = get_agent_by_name(full_agent_name)
                            if not existing:
                                try:
                                    with open(agent_path, "r", encoding="utf-8") as f:
                                        content = f.read()

                                    # Convert skills list to JSON string if present
                                    skills_value = agent_info.get("skills", [])
                                    if isinstance(skills_value, list):
                                        skills_value = json.dumps(skills_value)
                                    elif skills_value:
                                        skills_value = json.dumps([skills_value])
                                    else:
                                        skills_value = None

                                    # Convert goals list to JSON string if present
                                    goals_value = agent_info.get("goals", [])
                                    if isinstance(goals_value, list):
                                        goals_value = json.dumps(goals_value)
                                    elif goals_value:
                                        goals_value = json.dumps([goals_value])
                                    else:
                                        goals_value = None

                                    # Convert tools/allowed_tools to JSON if present
                                    tools_value = agent_info.get("tools")
                                    if isinstance(tools_value, list):
                                        tools_value = json.dumps(tools_value)

                                    allowed_tools_value = agent_info.get("allowed_tools")
                                    if isinstance(allowed_tools_value, list):
                                        allowed_tools_value = json.dumps(allowed_tools_value)

                                    # Convert triggers to JSON if present
                                    triggers_value = agent_info.get("triggers")
                                    if isinstance(triggers_value, list):
                                        triggers_value = json.dumps(triggers_value)

                                    agent_id = add_agent(
                                        name=full_agent_name,
                                        description=agent_info.get("description", ""),
                                        role=agent_info.get("role", ""),
                                        skills=skills_value,
                                        goals=goals_value,
                                        context=agent_info.get("context", ""),
                                        system_prompt=content,
                                        triggers=triggers_value,
                                        color=agent_info.get("color"),
                                        icon=agent_info.get("icon"),
                                        model=agent_info.get("model"),
                                        temperature=agent_info.get("temperature"),
                                        tools=tools_value,
                                        autonomous=1 if agent_info.get("autonomous") else 0,
                                        allowed_tools=allowed_tools_value,
                                    )
                                    if agent_id:
                                        imported_agents.append(full_agent_name)
                                except Exception:
                                    pass

                # Also check plugin.json for agents defined inline
                agents_in_config = plugin_config.get("agents", [])
                for agent_def in agents_in_config:
                    if isinstance(agent_def, dict):
                        agent_name = agent_def.get("name", "")
                        if agent_name:
                            full_agent_name = f"{plugin_name}:{agent_name}"
                            existing = get_agent_by_name(full_agent_name)
                            if not existing:
                                agent_id = add_agent(
                                    name=full_agent_name,
                                    description=agent_def.get("description", ""),
                                    role=agent_def.get("role", ""),
                                    system_prompt=agent_def.get("system_prompt", ""),
                                    color=agent_def.get("color"),
                                    icon=agent_def.get("icon"),
                                    model=agent_def.get("model"),
                                    temperature=agent_def.get("temperature"),
                                    autonomous=1 if agent_def.get("autonomous") else 0,
                                )
                                if agent_id:
                                    imported_agents.append(full_agent_name)

                # 5. Import teams
                imported_teams = []
                teams_dir = os.path.join(plugin_dir, "teams")
                if os.path.isdir(teams_dir):
                    for team_folder in os.listdir(teams_dir):
                        team_path = os.path.join(teams_dir, team_folder)
                        if not os.path.isdir(team_path):
                            continue

                        # Parse TEAM.md or TEAM.json
                        team_md = os.path.join(team_path, "TEAM.md")
                        team_json = os.path.join(team_path, "TEAM.json")

                        team_info = None
                        if os.path.isfile(team_md):
                            team_info = SkillDiscoveryService._parse_skill_file(
                                team_md, team_folder
                            )
                        elif os.path.isfile(team_json):
                            try:
                                with open(team_json, "r", encoding="utf-8") as f:
                                    team_info = json.load(f)
                            except (json.JSONDecodeError, IOError):
                                continue

                        if team_info:
                            full_team_name = f"{plugin_name}:{team_info.get('name', team_folder)}"
                            existing = get_team_by_name(full_team_name)
                            if not existing:
                                team_id = add_team(
                                    name=full_team_name,
                                    description=team_info.get("description", ""),
                                    color=team_info.get("color", "#00d4ff"),
                                )
                                if team_id:
                                    imported_teams.append(full_team_name)
                                    # Load members if present (Claude Code teams format)
                                    members = team_info.get("members", [])
                                    for member in members:
                                        if isinstance(member, dict):
                                            add_team_member(
                                                team_id=team_id,
                                                name=member.get("name", "Unknown"),
                                                email=member.get("email"),
                                                role=member.get("role", "member"),
                                                layer=member.get("layer", "backend"),
                                                description=member.get("description"),
                                                agent_id=member.get("agent_id"),
                                            )

                # Also check plugin.json for teams defined inline
                teams_in_config = plugin_config.get("teams", [])
                for team_def in teams_in_config:
                    if isinstance(team_def, dict):
                        team_name = team_def.get("name", "")
                        if team_name:
                            full_team_name = f"{plugin_name}:{team_name}"
                            existing = get_team_by_name(full_team_name)
                            if not existing:
                                team_id = add_team(
                                    name=full_team_name,
                                    description=team_def.get("description", ""),
                                    color=team_def.get("color", "#00d4ff"),
                                )
                                if team_id:
                                    imported_teams.append(full_team_name)
                                    # Load members if present
                                    members = team_def.get("members", [])
                                    for member in members:
                                        if isinstance(member, dict):
                                            add_team_member(
                                                team_id=team_id,
                                                name=member.get("name", "Unknown"),
                                                email=member.get("email"),
                                                role=member.get("role", "member"),
                                                layer=member.get("layer", "backend"),
                                                agent_id=member.get("agent_id"),
                                            )

                total_imported = (
                    len(imported_skills)
                    + len(imported_commands)
                    + len(imported_hooks)
                    + len(imported_agents)
                    + len(imported_teams)
                )

                return {
                    "message": f"Loaded {total_imported} components from '{plugin_name}'",
                    "imported_skills": imported_skills,
                    "imported_commands": imported_commands,
                    "imported_hooks": imported_hooks,
                    "imported_agents": imported_agents,
                    "imported_teams": imported_teams,
                    "plugin_name": plugin_name,
                    "marketplace": marketplace.get("name", "Unknown"),
                }, HTTPStatus.OK

            finally:
                # Clean up temp directory
                shutil.rmtree(temp_dir, ignore_errors=True)

        except subprocess.TimeoutExpired:
            return {"error": "Marketplace clone timed out"}, HTTPStatus.GATEWAY_TIMEOUT
        except Exception as e:
            return {
                "error": f"Failed to load from marketplace: {str(e)}"
            }, HTTPStatus.INTERNAL_SERVER_ERROR

    @classmethod
    def deploy_to_marketplace(cls) -> Tuple[dict, HTTPStatus]:
        """Deploy the current harness config to the marketplace.

        Generates the plugin configuration and prepares deployment info.
        Actual git push requires user authentication and is done client-side.
        """
        # Get harness plugin settings
        marketplace_id = get_setting("harness_marketplace_id")
        plugin_name = get_setting("harness_plugin_name")

        if not marketplace_id or not plugin_name:
            return {
                "error": "Harness plugin not configured. Go to Settings > Harness Plugin to configure."
            }, HTTPStatus.BAD_REQUEST

        # Get marketplace info
        marketplace = get_marketplace(marketplace_id)
        if not marketplace:
            return {"error": "Configured marketplace not found"}, HTTPStatus.NOT_FOUND

        # Generate the config
        config_result, _ = cls.generate_harness_config()
        config_json = config_result.get("config_json", "{}")

        # Parse and enhance the config for deployment
        try:
            config = json.loads(config_json)
            config["name"] = plugin_name
            config["generated_at"] = datetime.datetime.now().isoformat()
            config["marketplace"] = marketplace.get("name", "Unknown")
        except json.JSONDecodeError:
            config = {"name": plugin_name, "skills": []}

        return {
            "message": "Deploy configuration generated",
            "plugin_name": plugin_name,
            "marketplace": marketplace.get("name", "Unknown"),
            "marketplace_url": marketplace.get("url", ""),
            "config": config,
            "config_json": json.dumps(config, indent=2),
            "instructions": [
                f"1. Clone the marketplace repository: {marketplace.get('url', '')}",
                f"2. Navigate to the plugin directory: cd {plugin_name}",
                "3. Update plugin.json with the generated config",
                "4. Commit and push your changes",
                "5. Create a pull request to the marketplace",
            ],
        }, HTTPStatus.OK
