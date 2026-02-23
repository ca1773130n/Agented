"""Skill harness service — user skills CRUD, harness integration, agent export."""

import json
from http import HTTPStatus
from typing import Tuple

from ..database import (
    add_user_skill,
    delete_user_skill,
    get_all_user_skills,
    get_harness_skills,
    get_user_skill,
    get_user_skill_by_name,
    toggle_skill_harness,
    update_user_skill,
)
from .skill_marketplace_service import SkillMarketplaceService


class SkillHarnessService(SkillMarketplaceService):
    """Service for user skills CRUD, harness integration, and agent export."""

    # =========================================================================
    # User Skills Management
    # =========================================================================

    @classmethod
    def list_user_skills(cls) -> Tuple[dict, HTTPStatus]:
        """List all user-configured skills."""
        skills = get_all_user_skills()
        return {"skills": skills}, HTTPStatus.OK

    @classmethod
    def get_single_skill(cls, skill_id: int) -> Tuple[dict, HTTPStatus]:
        """Get a single user skill by ID."""
        skill = get_user_skill(skill_id)
        if not skill:
            return {"error": "Skill not found"}, HTTPStatus.NOT_FOUND
        return {"skill": skill}, HTTPStatus.OK

    @classmethod
    def add_skill(cls, data: dict) -> Tuple[dict, HTTPStatus]:
        """Add a skill to the user's collection."""
        skill_name = data.get("skill_name")
        skill_path = data.get("skill_path")

        if not skill_name or not skill_path:
            return {"error": "skill_name and skill_path are required"}, HTTPStatus.BAD_REQUEST

        # Check if skill already exists
        existing = get_user_skill_by_name(skill_name)
        if existing:
            return {"error": "Skill already exists"}, HTTPStatus.CONFLICT

        skill_id = add_user_skill(
            skill_name=skill_name,
            skill_path=skill_path,
            description=data.get("description"),
            enabled=data.get("enabled", 1),
            selected_for_harness=data.get("selected_for_harness", 0),
            metadata=data.get("metadata"),
        )

        if skill_id:
            return {
                "message": "Skill added",
                "id": skill_id,
                "skill_name": skill_name,
            }, HTTPStatus.CREATED
        else:
            return {"error": "Failed to add skill"}, HTTPStatus.INTERNAL_SERVER_ERROR

    @classmethod
    def update_skill(cls, skill_id: int, data: dict) -> Tuple[dict, HTTPStatus]:
        """Update a user skill."""
        skill = get_user_skill(skill_id)
        if not skill:
            return {"error": "Skill not found"}, HTTPStatus.NOT_FOUND

        success = update_user_skill(
            skill_id,
            skill_name=data.get("skill_name"),
            skill_path=data.get("skill_path"),
            description=data.get("description"),
            enabled=data.get("enabled"),
            selected_for_harness=data.get("selected_for_harness"),
            metadata=data.get("metadata"),
        )

        if success:
            return {"message": "Skill updated"}, HTTPStatus.OK
        else:
            return {"error": "No changes made"}, HTTPStatus.BAD_REQUEST

    @classmethod
    def remove_skill(cls, skill_id: int) -> Tuple[dict, HTTPStatus]:
        """Remove a skill from the user's collection."""
        skill = get_user_skill(skill_id)
        if not skill:
            return {"error": "Skill not found"}, HTTPStatus.NOT_FOUND

        success = delete_user_skill(skill_id)
        if success:
            return {"message": "Skill removed"}, HTTPStatus.OK
        else:
            return {"error": "Failed to remove skill"}, HTTPStatus.INTERNAL_SERVER_ERROR

    # =========================================================================
    # Harness Integration
    # =========================================================================

    @classmethod
    def get_harness_selected_skills(cls) -> Tuple[dict, HTTPStatus]:
        """Get skills selected for harness integration."""
        skills = get_harness_skills()
        return {"skills": skills}, HTTPStatus.OK

    @classmethod
    def toggle_harness_selection(cls, skill_id: int, selected: bool) -> Tuple[dict, HTTPStatus]:
        """Toggle a skill's harness selection."""
        skill = get_user_skill(skill_id)
        if not skill:
            return {"error": "Skill not found"}, HTTPStatus.NOT_FOUND

        success = toggle_skill_harness(skill_id, selected)
        if success:
            return {
                "message": f"Skill {'added to' if selected else 'removed from'} harness"
            }, HTTPStatus.OK
        else:
            return {"error": "Failed to update"}, HTTPStatus.INTERNAL_SERVER_ERROR

    @classmethod
    def generate_harness_config(cls) -> Tuple[dict, HTTPStatus]:
        """Generate harness configuration for claude-plugin-marketplace."""
        skills = get_harness_skills()

        # Generate config for one-harness
        config = {
            "name": "custom-harness",
            "version": "1.0.0",
            "description": "Custom skill harness generated from Agented",
            "skills": [],
        }

        for skill in skills:
            skill_config = {
                "name": skill["skill_name"],
                "path": skill["skill_path"],
                "description": skill.get("description", ""),
                "enabled": bool(skill.get("enabled", 1)),
            }
            config["skills"].append(skill_config)

        return {"skills": skills, "config_json": json.dumps(config, indent=2)}, HTTPStatus.OK

    # =========================================================================
    # Agent Export
    # =========================================================================

    @classmethod
    def export_agent_to_harness(cls, agent_id: str) -> Tuple[dict, HTTPStatus]:
        """Export an agent to harness plugin format (YAML frontmatter + markdown).

        Generates a markdown file with YAML frontmatter containing all agent fields.
        This allows bidirectional sync between the harness UI and plugin files.
        """
        from ..database import get_agent

        agent = get_agent(agent_id)
        if not agent:
            return {"error": "Agent not found"}, HTTPStatus.NOT_FOUND

        # Build YAML frontmatter
        frontmatter = {}

        # Basic fields
        if agent.get("name"):
            # Remove plugin prefix if present (e.g., "plugin:agent-name" -> "agent-name")
            name = agent["name"]
            if ":" in name:
                name = name.split(":", 1)[1]
            frontmatter["name"] = name

        if agent.get("description"):
            frontmatter["description"] = agent["description"]

        if agent.get("role"):
            frontmatter["role"] = agent["role"]

        # Parse JSON fields back to lists
        if agent.get("skills"):
            try:
                skills = json.loads(agent["skills"])
                if skills:
                    frontmatter["skills"] = skills
            except (json.JSONDecodeError, TypeError):
                if agent["skills"]:
                    frontmatter["skills"] = agent["skills"]

        if agent.get("goals"):
            try:
                goals = json.loads(agent["goals"])
                if goals:
                    frontmatter["goals"] = goals
            except (json.JSONDecodeError, TypeError):
                if agent["goals"]:
                    frontmatter["goals"] = agent["goals"]

        if agent.get("context"):
            frontmatter["context"] = agent["context"]

        # Extended harness fields
        if agent.get("triggers"):
            try:
                triggers = json.loads(agent["triggers"])
                if triggers:
                    frontmatter["triggers"] = triggers
            except (json.JSONDecodeError, TypeError):
                pass

        if agent.get("color"):
            frontmatter["color"] = agent["color"]

        if agent.get("icon"):
            frontmatter["icon"] = agent["icon"]

        if agent.get("model"):
            frontmatter["model"] = agent["model"]

        if agent.get("temperature") is not None:
            frontmatter["temperature"] = agent["temperature"]

        if agent.get("tools"):
            try:
                tools = json.loads(agent["tools"])
                if tools:
                    frontmatter["tools"] = tools
            except (json.JSONDecodeError, TypeError):
                pass

        if agent.get("autonomous"):
            frontmatter["autonomous"] = True

        if agent.get("allowed_tools"):
            try:
                allowed_tools = json.loads(agent["allowed_tools"])
                if allowed_tools:
                    frontmatter["allowed_tools"] = allowed_tools
            except (json.JSONDecodeError, TypeError):
                pass

        # Generate markdown content
        import yaml

        yaml_str = yaml.dump(
            frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False
        )

        # System prompt becomes the markdown body
        system_prompt = agent.get("system_prompt", "")

        content = f"---\n{yaml_str}---\n\n{system_prompt}"

        # Generate filename from agent name
        safe_name = agent.get("name", "agent").replace(":", "-").replace(" ", "-").lower()
        filename = f"{safe_name}.md"

        return {
            "filename": filename,
            "content": content,
            "agent_id": agent_id,
            "agent_name": agent.get("name"),
        }, HTTPStatus.OK
