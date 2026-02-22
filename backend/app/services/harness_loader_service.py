"""Harness loader service — load configs from GitHub repos."""

import json
import os
from http import HTTPStatus
from typing import List, Tuple

import yaml

from ..database import (
    add_agent,
    add_command,
    add_hook,
    add_project_skill,
    add_team,
    add_team_member,
    get_project_detail,
)
from .github_service import GitHubService
from .layer_detection_service import LayerDetectionService


class HarnessLoaderService(LayerDetectionService):
    """Service for loading Claude Code harness settings from GitHub repos."""

    @staticmethod
    def _parse_yaml_frontmatter(content: str) -> Tuple[dict, str]:
        """Parse YAML frontmatter from markdown content.

        Returns:
            Tuple of (frontmatter dict, body content)
        """
        if not content.startswith("---"):
            return {}, content

        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}, content

        try:
            frontmatter = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
            return frontmatter, body
        except yaml.YAMLError:
            return {}, content

    @classmethod
    def check_harness_exists(cls, project_id: str) -> Tuple[dict, HTTPStatus]:
        """Check if .claude folder exists in the project's GitHub repo.

        Returns:
            Tuple of (result dict with exists flag, HTTP status)
        """
        project = get_project_detail(project_id)
        if not project:
            return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

        github_repo = project.get("github_repo")
        if not github_repo:
            return {
                "exists": False,
                "error": "No GitHub repository configured for this project",
                "project_id": project_id,
            }, HTTPStatus.OK

        # Clone repo temporarily to check
        clone_path = None
        try:
            repo_url = f"https://github.com/{github_repo}"
            clone_path = GitHubService.clone_repo(repo_url)

            claude_path = os.path.join(clone_path, ".claude")
            exists = os.path.isdir(claude_path)

            # Check what subdirectories exist
            subdirs = {}
            if exists:
                for subdir in ["agents", "skills", "hooks", "commands", "teams"]:
                    subdir_path = os.path.join(claude_path, subdir)
                    subdirs[subdir] = os.path.isdir(subdir_path)

            return {
                "exists": exists,
                "subdirs": subdirs if exists else {},
                "project_id": project_id,
                "github_repo": github_repo,
            }, HTTPStatus.OK

        except Exception as e:
            return {
                "exists": False,
                "error": str(e),
                "project_id": project_id,
            }, HTTPStatus.OK
        finally:
            if clone_path:
                GitHubService.cleanup_clone(clone_path)

    @classmethod
    def load_from_github(cls, project_id: str) -> Tuple[dict, HTTPStatus]:
        """Load harness settings from a project's GitHub repository.

        Imports agents, skills, hooks, commands, and teams from .claude folder.

        Returns:
            Tuple of (result dict with import stats, HTTP status)
        """
        project = get_project_detail(project_id)
        if not project:
            return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

        github_repo = project.get("github_repo")
        if not github_repo:
            return {
                "error": "No GitHub repository configured for this project",
                "project_id": project_id,
            }, HTTPStatus.BAD_REQUEST

        clone_path = None
        try:
            repo_url = f"https://github.com/{github_repo}"
            clone_path = GitHubService.clone_repo(repo_url)

            claude_path = os.path.join(clone_path, ".claude")
            if not os.path.isdir(claude_path):
                return {
                    "error": ".claude folder not found in repository",
                    "project_id": project_id,
                    "github_repo": github_repo,
                }, HTTPStatus.NOT_FOUND

            imported = {
                "agents": [],
                "skills": [],
                "hooks": [],
                "commands": [],
                "teams": [],
            }

            # Import agents
            agents_path = os.path.join(claude_path, "agents")
            if os.path.isdir(agents_path):
                imported["agents"] = cls._import_agents(agents_path, project_id)

            # Import skills
            skills_path = os.path.join(claude_path, "skills")
            if os.path.isdir(skills_path):
                imported["skills"] = cls._import_skills(skills_path, project_id)

            # Import hooks
            hooks_path = os.path.join(claude_path, "hooks")
            if os.path.isdir(hooks_path):
                imported["hooks"] = cls._import_hooks(hooks_path, project_id)

            # Import commands
            commands_path = os.path.join(claude_path, "commands")
            if os.path.isdir(commands_path):
                imported["commands"] = cls._import_commands(commands_path, project_id)

            # Import teams
            teams_path = os.path.join(claude_path, "teams")
            if os.path.isdir(teams_path):
                imported["teams"] = cls._import_teams(teams_path, project_id)

            return {
                "message": "Harness settings loaded successfully",
                "project_id": project_id,
                "github_repo": github_repo,
                "imported": imported,
                "counts": {k: len(v) for k, v in imported.items()},
            }, HTTPStatus.OK

        except Exception as e:
            return {
                "error": f"Failed to load harness settings: {str(e)}",
                "project_id": project_id,
            }, HTTPStatus.INTERNAL_SERVER_ERROR
        finally:
            if clone_path:
                GitHubService.cleanup_clone(clone_path)

    @classmethod
    def _import_agents(cls, agents_path: str, project_id: str) -> List[str]:
        """Import agents from .claude/agents directory with enhanced detection."""
        imported = []

        for item in os.listdir(agents_path):
            item_path = os.path.join(agents_path, item)

            # Check for AGENT.md file
            if os.path.isdir(item_path):
                agent_md = os.path.join(item_path, "AGENT.md")
                if os.path.isfile(agent_md):
                    with open(agent_md, "r") as f:
                        content = f.read()
                    frontmatter, body = cls._parse_yaml_frontmatter(content)

                    agent_name = frontmatter.get("name", item)
                    full_content = f"{body}\n{frontmatter.get('description', '')}\n{frontmatter.get('role', '')}"

                    # Skip if agent with this name already exists
                    from ..database import get_connection as _get_conn

                    with _get_conn() as _conn:
                        _exists = _conn.execute(
                            "SELECT 1 FROM agents WHERE name = ? LIMIT 1", (agent_name,)
                        ).fetchone()
                    if _exists:
                        continue

                    # Enhanced detection
                    detected_layer = cls._detect_layer(full_content, frontmatter.get("role"))
                    detected_role = cls._detect_role(full_content, agent_name)
                    skills_list = frontmatter.get("skills", [])

                    try:
                        add_agent(
                            name=agent_name,
                            description=frontmatter.get("description"),
                            role=frontmatter.get("role"),
                            goals=json.dumps(frontmatter.get("goals", [])),
                            context=body if body else None,
                            backend_type="claude",
                            skills=json.dumps(skills_list),
                            system_prompt=frontmatter.get("system_prompt"),
                            triggers=json.dumps(frontmatter.get("triggers", [])),
                            color=frontmatter.get("color"),
                            model=frontmatter.get("model"),
                            autonomous=1 if frontmatter.get("autonomous") else 0,
                            allowed_tools=json.dumps(frontmatter.get("tools", [])),
                            layer=detected_layer,
                            detected_role=detected_role,
                            matched_skills=json.dumps(
                                skills_list
                            ),  # Store agent's skills for later matching
                        )
                        imported.append(agent_name)
                    except Exception as e:
                        print(f"Failed to import agent {agent_name}: {e}")

            # Also handle .md files directly in agents folder
            elif item.endswith(".md"):
                with open(item_path, "r") as f:
                    content = f.read()
                frontmatter, body = cls._parse_yaml_frontmatter(content)

                agent_name = frontmatter.get("name", item.replace(".md", ""))

                # Skip if agent with this name already exists
                with _get_conn() as _conn:
                    _exists = _conn.execute(
                        "SELECT 1 FROM agents WHERE name = ? LIMIT 1", (agent_name,)
                    ).fetchone()
                if _exists:
                    continue

                full_content = (
                    f"{body}\n{frontmatter.get('description', '')}\n{frontmatter.get('role', '')}"
                )

                # Enhanced detection
                detected_layer = cls._detect_layer(full_content, frontmatter.get("role"))
                detected_role = cls._detect_role(full_content, agent_name)
                skills_list = frontmatter.get("skills", [])

                try:
                    add_agent(
                        name=agent_name,
                        description=frontmatter.get("description"),
                        role=frontmatter.get("role"),
                        goals=json.dumps(frontmatter.get("goals", [])),
                        context=body if body else None,
                        backend_type="claude",
                        skills=json.dumps(skills_list),
                        system_prompt=frontmatter.get("system_prompt"),
                        triggers=json.dumps(frontmatter.get("triggers", [])),
                        color=frontmatter.get("color"),
                        model=frontmatter.get("model"),
                        autonomous=1 if frontmatter.get("autonomous") else 0,
                        allowed_tools=json.dumps(frontmatter.get("tools", [])),
                        layer=detected_layer,
                        detected_role=detected_role,
                        matched_skills=json.dumps(skills_list),
                    )
                    imported.append(agent_name)
                except Exception as e:
                    print(f"Failed to import agent {agent_name}: {e}")

        return imported

    @classmethod
    def _import_skills(cls, skills_path: str, project_id: str) -> List[str]:
        """Import skills from .claude/skills directory."""
        imported = []

        for item in os.listdir(skills_path):
            item_path = os.path.join(skills_path, item)

            # Check for SKILL.md file
            if os.path.isdir(item_path):
                skill_md = os.path.join(item_path, "SKILL.md")
                if os.path.isfile(skill_md):
                    skill_name = item
                    try:
                        add_project_skill(
                            project_id=project_id,
                            skill_name=skill_name,
                            skill_path=f".claude/skills/{item}",
                            source="github_sync",
                        )
                        imported.append(skill_name)
                    except Exception as e:
                        print(f"Failed to import skill {skill_name}: {e}")

        return imported

    @classmethod
    def _import_hooks(cls, hooks_path: str, project_id: str) -> List[str]:
        """Import hooks from .claude/hooks directory."""
        imported = []

        for item in os.listdir(hooks_path):
            if not item.endswith(".md"):
                continue

            item_path = os.path.join(hooks_path, item)
            with open(item_path, "r") as f:
                content = f.read()

            frontmatter, body = cls._parse_yaml_frontmatter(content)

            hook_name = frontmatter.get("name", item.replace(".md", ""))
            event = frontmatter.get("event", "PreToolUse")

            # Validate event type
            valid_events = [
                "PreToolUse",
                "PostToolUse",
                "Stop",
                "SubagentStop",
                "SessionStart",
                "SessionEnd",
                "UserPromptSubmit",
                "PreCompact",
                "Notification",
            ]
            if event not in valid_events:
                event = "PreToolUse"

            try:
                add_hook(
                    name=hook_name,
                    event=event,
                    description=frontmatter.get("description"),
                    content=body if body else content,
                    enabled=True,
                    project_id=project_id,
                    source_path=f".claude/hooks/{item}",
                )
                imported.append(hook_name)
            except Exception as e:
                print(f"Failed to import hook {hook_name}: {e}")

        return imported

    @classmethod
    def _import_commands(cls, commands_path: str, project_id: str) -> List[str]:
        """Import commands from .claude/commands directory."""
        imported = []

        for item in os.listdir(commands_path):
            if not item.endswith(".md"):
                continue

            item_path = os.path.join(commands_path, item)
            with open(item_path, "r") as f:
                content = f.read()

            frontmatter, body = cls._parse_yaml_frontmatter(content)

            command_name = frontmatter.get("name", item.replace(".md", ""))

            try:
                add_command(
                    name=command_name,
                    description=frontmatter.get("description"),
                    content=body if body else content,
                    arguments=json.dumps(frontmatter.get("arguments", [])),
                    enabled=True,
                    project_id=project_id,
                    source_path=f".claude/commands/{item}",
                )
                imported.append(command_name)
            except Exception as e:
                print(f"Failed to import command {command_name}: {e}")

        return imported

    @classmethod
    def _import_teams(cls, teams_path: str, project_id: str) -> List[str]:
        """Import teams from .claude/teams directory.

        Each team is a folder with a TEAM.md file containing YAML frontmatter.
        Teams imported from GitHub are marked with source='github_sync'.
        """
        imported = []

        for item in os.listdir(teams_path):
            item_path = os.path.join(teams_path, item)

            # Check for TEAM.md file in team folder
            if os.path.isdir(item_path):
                team_md = os.path.join(item_path, "TEAM.md")
                if os.path.isfile(team_md):
                    with open(team_md, "r") as f:
                        content = f.read()
                    frontmatter, body = cls._parse_yaml_frontmatter(content)

                    team_name = frontmatter.get("name", item)
                    description = frontmatter.get("description", body.strip() if body else None)
                    color = frontmatter.get("color", "#00d4ff")

                    try:
                        # Create team with github_sync source
                        team_id = add_team(
                            name=team_name,
                            description=description,
                            color=color,
                            source="github_sync",
                        )

                        if team_id:
                            # Import team members if present
                            members = frontmatter.get("members", [])
                            for member in members:
                                if isinstance(member, dict):
                                    member_name = member.get("name", "")
                                    member_role = member.get("role", "member")
                                    member_desc = member.get("description", "")
                                    member_layer = member.get("layer", "backend")

                                    if member_name:
                                        add_team_member(
                                            team_id=team_id,
                                            name=member_name,
                                            role=member_role,
                                            description=member_desc,
                                            layer=member_layer,
                                        )

                            imported.append(team_name)
                    except Exception as e:
                        print(f"Failed to import team {team_name}: {e}")

        return imported
