"""Skills management API endpoints."""

import os
from http import HTTPStatus
from typing import Optional

from flask import Response, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..services.skills_service import SkillsService, get_playground_working_dir

tag = Tag(name="skills", description="Skills management and playground")
skills_bp = APIBlueprint("skills", __name__, url_prefix="/api/skills", abp_tags=[tag])


class SkillPath(BaseModel):
    skill_name: str = Field(..., description="Skill name")


class SkillIdPath(BaseModel):
    skill_id: int = Field(..., description="User skill ID")


class TestPath(BaseModel):
    test_id: str = Field(..., description="Test session ID")


class SkillQuery(BaseModel):
    trigger_id: Optional[str] = Field(None, description="Filter skills by trigger ID")


# =============================================================================
# Skill Discovery
# =============================================================================


@skills_bp.get("/")
def list_skills(query: SkillQuery):
    """List all discovered skills."""
    result, status = SkillsService.list_skills(trigger_id=query.trigger_id)
    return result, status


@skills_bp.get("/discover/<skill_name>")
def get_skill_detail(path: SkillPath):
    """Get details for a specific discovered skill."""
    result, status = SkillsService.get_skill_detail(path.skill_name)
    return result, status


# =============================================================================
# User Skills Management
# =============================================================================


@skills_bp.get("/user")
def list_user_skills():
    """List all user-configured skills."""
    result, status = SkillsService.list_user_skills()
    return result, status


@skills_bp.get("/user/<int:skill_id>")
def get_single_user_skill(path: SkillIdPath):
    """Get a single user skill by ID."""
    result, status = SkillsService.get_single_skill(path.skill_id)
    return result, status


@skills_bp.post("/user")
def add_user_skill():
    """Add a skill to the user's collection."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    result, status = SkillsService.add_skill(data)
    return result, status


@skills_bp.put("/user/<int:skill_id>")
def update_user_skill(path: SkillIdPath):
    """Update a user skill."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    result, status = SkillsService.update_skill(path.skill_id, data)
    return result, status


@skills_bp.delete("/user/<int:skill_id>")
def delete_user_skill(path: SkillIdPath):
    """Remove a skill from the user's collection."""
    result, status = SkillsService.remove_skill(path.skill_id)
    return result, status


# =============================================================================
# Harness Integration
# =============================================================================


@skills_bp.get("/harness")
def get_harness_skills():
    """Get skills selected for harness integration."""
    result, status = SkillsService.get_harness_selected_skills()
    return result, status


@skills_bp.put("/harness/<int:skill_id>")
def toggle_harness_skill(path: SkillIdPath):
    """Toggle a skill's harness selection."""
    data = request.get_json()
    if data is None:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST
    selected = bool(data.get("selected", False))
    result, status = SkillsService.toggle_harness_selection(path.skill_id, selected)
    return result, status


@skills_bp.get("/harness/config")
def get_harness_config():
    """Generate harness configuration for claude-plugin-marketplace."""
    result, status = SkillsService.generate_harness_config()
    return result, status


@skills_bp.post("/harness/load-from-marketplace")
def load_from_marketplace():
    """Load skills from the configured marketplace plugin.

    Fetches the plugin from the marketplace based on settings,
    parses the plugin.json, and imports skills into user skills.
    """
    result, status = SkillsService.load_from_marketplace()
    return result, status


@skills_bp.post("/harness/deploy-to-marketplace")
def deploy_to_marketplace():
    """Deploy the current harness config to the marketplace.

    Generates the plugin configuration and prepares it for
    deployment to the configured marketplace repository.
    """
    result, status = SkillsService.deploy_to_marketplace()
    return result, status


# =============================================================================
# Skill Playground (Testing)
# =============================================================================


@skills_bp.get("/playground/files")
def list_playground_files():
    """List files in the playground working directory."""
    working_dir = get_playground_working_dir()

    def build_tree(path: str, depth: int = 0, max_depth: int = 5) -> list:
        """Recursively build a file tree."""
        if depth > max_depth:
            return []

        items = []
        try:
            entries = sorted(os.listdir(path))
        except OSError:
            return []

        for entry in entries:
            # Skip hidden files/directories and common non-essential dirs
            if entry.startswith(".") or entry in (
                "node_modules",
                "__pycache__",
                "dist",
                "build",
                ".git",
            ):
                continue

            full_path = os.path.join(path, entry)
            rel_path = os.path.relpath(full_path, working_dir)

            if os.path.isdir(full_path):
                children = build_tree(full_path, depth + 1, max_depth)
                items.append(
                    {
                        "name": entry,
                        "path": rel_path,
                        "type": "directory",
                        "children": children,
                    }
                )
            else:
                items.append(
                    {
                        "name": entry,
                        "path": rel_path,
                        "type": "file",
                    }
                )

        return items

    file_tree = build_tree(working_dir)
    return {
        "working_dir": working_dir,
        "files": file_tree,
    }, HTTPStatus.OK


@skills_bp.post("/test")
def test_skill():
    """Start a skill test in the playground."""
    data = request.get_json()
    if not data or not data.get("skill_name"):
        return {"error": "skill_name is required"}, HTTPStatus.BAD_REQUEST
    skill_name = data["skill_name"]
    test_input = data.get("input", "")
    result, status = SkillsService.test_skill(skill_name, test_input)
    return result, status


@skills_bp.get("/test/<test_id>/stream")
def stream_test(path: TestPath):
    """SSE endpoint for skill test streaming.

    Returns Server-Sent Events with the following event types:
    - start: Test started
    - output: Output line from the skill
    - error_output: Error output from the skill
    - complete: Test completed
    - error: An error occurred
    """

    def generate():
        for event in SkillsService.subscribe_test(path.test_id):
            yield event

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@skills_bp.post("/test/<test_id>/stop")
def stop_test(path: TestPath):
    """Stop a running skill test."""
    result, status = SkillsService.stop_test(path.test_id)
    return result, status


# =============================================================================
# Skills.sh Integration
# =============================================================================


@skills_bp.get("/skills-sh/search")
def search_skills_sh():
    """Search skills from skills.sh marketplace."""
    query = request.args.get("q", "").strip()
    from ..services.skills_sh_service import SkillsShService

    result, status = SkillsShService.search(query)
    return result, status


@skills_bp.post("/skills-sh/install")
def install_skills_sh():
    """Install a skill from skills.sh."""
    data = request.get_json()
    if not data or not data.get("source"):
        return {"error": "source is required"}, HTTPStatus.BAD_REQUEST
    from ..services.skills_sh_service import SkillsShService

    client_ip = request.remote_addr or "unknown"
    result, status = SkillsShService.install_skill(data["source"], client_ip=client_ip)
    return result, status
