"""Service for installing/uninstalling components to project .claude/ directories."""

import json
import logging
import os
import re

import yaml

from ..database import (
    add_project_installation,
    delete_project_installation,
    get_agent,
    get_command,
    get_hook,
    get_project_installation,
    get_project_installations,
    get_rule,
)
from .project_workspace_service import ProjectWorkspaceService

logger = logging.getLogger(__name__)

# Component type to .claude/ subdirectory mapping
COMPONENT_SUBDIRS = {
    "agent": "agents",
    "skill": "skills",
    "hook": "hooks",
    "command": "commands",
    "rule": "rules",
}

VALID_COMPONENT_TYPES = set(COMPONENT_SUBDIRS.keys())


class ProjectInstallService:
    """Service for installing and uninstalling Hive components as .claude/ files."""

    @staticmethod
    def install_component(project_id: str, component_type: str, component_id: str) -> dict:
        """Install a component to the project's .claude/ directory.

        Args:
            project_id: The project to install to.
            component_type: One of 'agent', 'skill', 'hook', 'command', 'rule'.
            component_id: The ID of the component to install.

        Returns:
            Dict with installed=True and path on success.

        Raises:
            ValueError: If component not found or workspace cannot be resolved.
        """
        if component_type not in VALID_COMPONENT_TYPES:
            raise ValueError(
                f"Invalid component_type: {component_type}. "
                f"Must be one of: {', '.join(sorted(VALID_COMPONENT_TYPES))}"
            )

        # 1. Get component from DB
        component = ProjectInstallService._get_component(component_type, component_id)
        if not component:
            raise ValueError(f"{component_type} not found: {component_id}")

        # 2. Resolve workspace
        workspace = ProjectWorkspaceService.resolve_working_directory(project_id)

        # 3. Generate file content
        content = ProjectInstallService._generate_file_content(component_type, component)

        # 4. Determine target path
        name = ProjectInstallService._get_component_name(component_type, component)
        subdir = COMPONENT_SUBDIRS[component_type]

        if component_type == "skill":
            # Skills use directory structure: .claude/skills/{name}/SKILL.md
            relative_path = f".claude/{subdir}/{name}/SKILL.md"
        else:
            relative_path = f".claude/{subdir}/{name}.md"

        full_path = os.path.join(workspace, relative_path)

        # 5. Write file
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(content)

        # 6. For hooks: also update settings.json
        if component_type == "hook":
            ProjectInstallService._update_settings_json_hooks(workspace, component, action="add")

        # 7. Record in DB
        add_project_installation(project_id, component_type, component_id)

        logger.info(f"Installed {component_type} {component_id} to {relative_path}")
        return {"installed": True, "path": relative_path}

    @staticmethod
    def uninstall_component(project_id: str, component_type: str, component_id: str) -> dict:
        """Uninstall a component from the project's .claude/ directory.

        Args:
            project_id: The project to uninstall from.
            component_type: One of 'agent', 'skill', 'hook', 'command', 'rule'.
            component_id: The ID of the component to uninstall.

        Returns:
            Dict with uninstalled=True and path on success.

        Raises:
            ValueError: If installation record not found or workspace cannot be resolved.
        """
        if component_type not in VALID_COMPONENT_TYPES:
            raise ValueError(f"Invalid component_type: {component_type}")

        # 1. Get installation record
        installation = get_project_installation(project_id, component_type, component_id)
        if not installation:
            raise ValueError(
                f"No installation found for {component_type} {component_id} in project {project_id}"
            )

        # 2. Resolve workspace
        workspace = ProjectWorkspaceService.resolve_working_directory(project_id)

        # 3. Determine file path and remove it
        component = ProjectInstallService._get_component(component_type, component_id)
        if component:
            name = ProjectInstallService._get_component_name(component_type, component)
        else:
            # Component may have been deleted from DB, use a fallback
            name = str(component_id)

        subdir = COMPONENT_SUBDIRS[component_type]

        if component_type == "skill":
            relative_path = f".claude/{subdir}/{name}/SKILL.md"
            full_path = os.path.join(workspace, relative_path)
            # Remove the skill directory
            skill_dir = os.path.dirname(full_path)
            try:
                if os.path.isfile(full_path):
                    os.remove(full_path)
                if os.path.isdir(skill_dir) and not os.listdir(skill_dir):
                    os.rmdir(skill_dir)
            except FileNotFoundError:
                pass
        else:
            relative_path = f".claude/{subdir}/{name}.md"
            full_path = os.path.join(workspace, relative_path)
            try:
                os.remove(full_path)
            except FileNotFoundError:
                pass

        # 4. For hooks: also remove from settings.json
        if component_type == "hook" and component:
            ProjectInstallService._update_settings_json_hooks(workspace, component, action="remove")

        # 5. Delete DB record
        delete_project_installation(project_id, component_type, component_id)

        logger.info(f"Uninstalled {component_type} {component_id} from {relative_path}")
        return {"uninstalled": True, "path": relative_path}

    @staticmethod
    def list_installations(project_id: str, component_type: str = None) -> list:
        """List all installed components for a project with enriched names.

        Args:
            project_id: The project to list installations for.
            component_type: Optional filter by component type.

        Returns:
            List of installation records with component names.
        """
        installations = get_project_installations(project_id, component_type)

        enriched = []
        for inst in installations:
            component = ProjectInstallService._get_component(
                inst["component_type"], inst["component_id"]
            )
            component_name = None
            if component:
                component_name = component.get("name", str(inst["component_id"]))

            enriched.append(
                {
                    "id": inst["id"],
                    "project_id": inst["project_id"],
                    "component_type": inst["component_type"],
                    "component_id": inst["component_id"],
                    "component_name": component_name,
                    "installed_at": inst["installed_at"],
                }
            )

        return enriched

    @staticmethod
    def _get_component(component_type: str, component_id: str) -> dict | None:
        """Get a component from the database by type and ID."""
        if component_type == "agent":
            return get_agent(str(component_id))
        elif component_type == "hook":
            return get_hook(int(component_id))
        elif component_type == "command":
            return get_command(int(component_id))
        elif component_type == "rule":
            return get_rule(int(component_id))
        elif component_type == "skill":
            # Skills don't have a direct ID lookup; they're in project_skills.
            # The component_id for skills is the skill name.
            return {"name": str(component_id), "skill_name": str(component_id)}
        return None

    @staticmethod
    def _get_component_name(component_type: str, component: dict) -> str:
        """Return a sanitized name suitable for filename."""
        if component_type == "skill":
            raw_name = component.get("skill_name", component.get("name", "unnamed"))
        else:
            raw_name = component.get("name", "unnamed")

        # Sanitize: lowercase, spaces to hyphens, remove special chars
        name = raw_name.lower().strip()
        name = re.sub(r"\s+", "-", name)
        name = re.sub(r"[^a-z0-9\-_]", "", name)
        return name or "unnamed"

    @staticmethod
    def _generate_file_content(component_type: str, component: dict) -> str:
        """Generate .claude/ file content for a component."""
        if component_type == "agent":
            return ProjectInstallService._generate_agent_content(component)
        elif component_type == "skill":
            return ProjectInstallService._generate_skill_content(component)
        elif component_type == "hook":
            return ProjectInstallService._generate_hook_content(component)
        elif component_type == "command":
            return ProjectInstallService._generate_command_content(component)
        elif component_type == "rule":
            return ProjectInstallService._generate_rule_content(component)
        return ""

    @staticmethod
    def _generate_agent_content(component: dict) -> str:
        """Generate agent .md file with YAML frontmatter."""
        frontmatter = {"name": component.get("name", "unnamed")}

        if component.get("description"):
            frontmatter["description"] = component["description"]
        if component.get("role"):
            frontmatter["role"] = component["role"]

        # Parse tools from allowed_tools (JSON string)
        tools = component.get("allowed_tools")
        if tools:
            if isinstance(tools, str):
                try:
                    tools = json.loads(tools)
                except json.JSONDecodeError:
                    tools = []
            if tools:
                frontmatter["tools"] = tools

        yaml_content = yaml.dump(
            frontmatter,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        body = component.get("context") or component.get("system_prompt") or ""
        return f"---\n{yaml_content}---\n\n{body}\n"

    @staticmethod
    def _generate_skill_content(component: dict) -> str:
        """Generate skill SKILL.md file with YAML frontmatter."""
        name = component.get("skill_name", component.get("name", "unnamed"))
        frontmatter = {"name": name}

        yaml_content = yaml.dump(
            frontmatter,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        body = component.get("content", f"# {name}\n\nSkill placeholder.")
        return f"---\n{yaml_content}---\n\n{body}\n"

    @staticmethod
    def _generate_hook_content(component: dict) -> str:
        """Generate hook .md file with YAML frontmatter."""
        frontmatter = {
            "name": component.get("name", "unnamed"),
            "event": component.get("event", "PreToolUse"),
        }

        if component.get("description"):
            frontmatter["description"] = component["description"]

        yaml_content = yaml.dump(
            frontmatter,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        body = component.get("content", "")
        return f"---\n{yaml_content}---\n\n{body}\n"

    @staticmethod
    def _generate_command_content(component: dict) -> str:
        """Generate command .md file with YAML frontmatter."""
        frontmatter = {"name": component.get("name", "unnamed")}

        if component.get("description"):
            frontmatter["description"] = component["description"]

        yaml_content = yaml.dump(
            frontmatter,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        body = component.get("content", "")
        return f"---\n{yaml_content}---\n\n{body}\n"

    @staticmethod
    def _generate_rule_content(component: dict) -> str:
        """Generate rule .md file with YAML frontmatter."""
        frontmatter = {
            "name": component.get("name", "unnamed"),
            "rule_type": component.get("rule_type", "validation"),
        }

        if component.get("description"):
            frontmatter["description"] = component["description"]

        yaml_content = yaml.dump(
            frontmatter,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        body_parts = []
        if component.get("condition"):
            body_parts.append(f"## Condition\n\n{component['condition']}")
        if component.get("action"):
            body_parts.append(f"## Action\n\n{component['action']}")

        body = "\n\n".join(body_parts) if body_parts else ""
        return f"---\n{yaml_content}---\n\n{body}\n"

    @staticmethod
    def _update_settings_json_hooks(workspace: str, hook: dict, action: str = "add"):
        """Update .claude/settings.json with hook entries.

        Args:
            workspace: The project workspace directory.
            hook: The hook component dict.
            action: 'add' or 'remove'.
        """
        settings_path = os.path.join(workspace, ".claude", "settings.json")

        # Read existing settings
        settings = {}
        if os.path.isfile(settings_path):
            try:
                with open(settings_path, "r") as f:
                    settings = json.load(f)
            except (json.JSONDecodeError, IOError):
                settings = {}

        # Ensure hooks section exists
        if "hooks" not in settings:
            settings["hooks"] = {}

        event = hook.get("event", "PreToolUse")
        hook_name = hook.get("name", "unnamed")

        if event not in settings["hooks"]:
            settings["hooks"][event] = []

        hook_entry = {
            "name": hook_name,
            "description": hook.get("description", ""),
        }

        if action == "add":
            # Don't add duplicates
            existing_names = [h.get("name") for h in settings["hooks"][event]]
            if hook_name not in existing_names:
                settings["hooks"][event].append(hook_entry)
        elif action == "remove":
            settings["hooks"][event] = [
                h for h in settings["hooks"][event] if h.get("name") != hook_name
            ]
            # Clean up empty event arrays
            if not settings["hooks"][event]:
                del settings["hooks"][event]
            # Clean up empty hooks section
            if not settings["hooks"]:
                del settings["hooks"]

        # Write back
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)
