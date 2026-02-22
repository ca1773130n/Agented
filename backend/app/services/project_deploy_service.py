"""Service for deploying project team configurations to Claude Code format."""

import json
from http import HTTPStatus
from typing import Tuple

import yaml

from ..database import (
    get_project_detail,
    get_team_detail,
    get_team_members,
)


class ProjectDeployService:
    """Service for generating and deploying project team configurations."""

    @classmethod
    def generate_team_config(cls, team: dict) -> dict:
        """Generate Claude Code team config.json format.

        Args:
            team: Team dict with id, name, description, members, etc.

        Returns:
            Dict in Claude Code team config format.
        """
        config = {
            "name": team.get("name", ""),
            "description": team.get("description", ""),
        }

        # Add leader if present
        if team.get("leader_id"):
            config["lead"] = team.get("leader_name", "")

        # Add members
        members = team.get("members", [])
        if members:
            config["members"] = []
            for member in members:
                member_entry = {
                    "name": member.get("name", ""),
                    "role": member.get("role", "member"),
                }
                if member.get("description"):
                    member_entry["description"] = member["description"]
                config["members"].append(member_entry)

        return config

    @classmethod
    def generate_team_md(cls, team: dict) -> str:
        """Generate TEAM.md with YAML frontmatter in Claude Code format.

        Args:
            team: Team dict with id, name, description, members, etc.

        Returns:
            String content for TEAM.md file.
        """
        frontmatter = {
            "name": team.get("name", ""),
        }

        if team.get("description"):
            frontmatter["description"] = team["description"]

        if team.get("leader_name"):
            frontmatter["lead"] = team["leader_name"]

        # Add members
        members = team.get("members", [])
        if members:
            frontmatter["members"] = []
            for member in members:
                member_entry = {
                    "name": member.get("name", ""),
                    "role": member.get("role", "member"),
                }
                if member.get("description"):
                    member_entry["description"] = member["description"]
                frontmatter["members"].append(member_entry)

        # Generate YAML frontmatter
        yaml_content = yaml.dump(
            frontmatter,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        # Build markdown content
        md_content = f"---\n{yaml_content}---\n\n"

        # Add team description as markdown body if present
        if team.get("description"):
            md_content += f"# {team['name']}\n\n{team['description']}\n"

        return md_content

    @classmethod
    def deploy_to_project(cls, project_id: str) -> Tuple[dict, HTTPStatus]:
        """Generate .claude/teams/ files for all project teams.

        Args:
            project_id: The project ID to deploy teams for.

        Returns:
            Tuple of (result dict, HTTP status).
        """
        project = get_project_detail(project_id)
        if not project:
            return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

        teams = project.get("teams", [])
        if not teams:
            return {
                "error": "No teams assigned to this project",
                "project_id": project_id,
            }, HTTPStatus.BAD_REQUEST

        generated_files = []

        for team in teams:
            team_id = team.get("id")
            if not team_id:
                continue

            # Get full team details including members
            team_detail = get_team_detail(team_id)
            if not team_detail:
                continue

            # Get members
            members = get_team_members(team_id)
            team_detail["members"] = members

            # Generate safe folder name from team name
            team_name = team_detail.get("name", f"team-{team_id}")
            # Remove plugin prefix if present
            if ":" in team_name:
                team_name = team_name.split(":", 1)[1]
            safe_name = team_name.lower().replace(" ", "-").replace(":", "-")

            # Generate TEAM.md content
            team_md_content = cls.generate_team_md(team_detail)

            # Generate config.json content
            team_config = cls.generate_team_config(team_detail)
            config_content = json.dumps(team_config, indent=2)

            generated_files.append(
                {
                    "team_name": team_name,
                    "folder_name": safe_name,
                    "files": {
                        f".claude/teams/{safe_name}/TEAM.md": team_md_content,
                        f".claude/teams/{safe_name}/config.json": config_content,
                    },
                }
            )

        return {
            "project_id": project_id,
            "project_name": project.get("name"),
            "teams_count": len(generated_files),
            "generated": generated_files,
        }, HTTPStatus.OK

    @classmethod
    def get_deploy_preview(cls, project_id: str) -> Tuple[dict, HTTPStatus]:
        """Get a preview of what will be deployed without actually deploying.

        Same as deploy_to_project but doesn't write any files.
        """
        return cls.deploy_to_project(project_id)
