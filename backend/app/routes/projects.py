"""Project management API endpoints."""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from ..database import (
    add_project,
    add_project_skill,
    add_project_team_edge,
    assign_team_to_project,
    count_projects,
    delete_project,
    delete_project_skill_by_id,
    delete_project_team_edge,
    get_all_projects,
    get_project,
    get_project_detail,
    get_project_skills,
    get_project_team_edges,
    get_project_teams,
    get_team_detail,
    unassign_team_from_project,
    update_project,
    update_project_team_topology_config,
)
from ..models.common import PaginationQuery
from ..services.github_service import GitHubService
from ..services.harness_service import HarnessService
from ..services.project_deploy_service import ProjectDeployService
from ..services.project_install_service import ProjectInstallService
from ..services.project_workspace_service import ProjectWorkspaceService
from ..services.team_execution_service import TeamExecutionService

tag = Tag(name="projects", description="Project management operations")
projects_bp = APIBlueprint("projects", __name__, url_prefix="/admin/projects", abp_tags=[tag])


class ProjectPath(BaseModel):
    project_id: str = Field(..., description="Project ID")


class TeamAssignPath(BaseModel):
    project_id: str = Field(..., description="Project ID")
    team_id: str = Field(..., description="Team ID")


class TeamEdgePath(BaseModel):
    project_id: str = Field(..., description="Project ID")
    edge_id: int = Field(..., description="Edge ID")


@projects_bp.get("/")
def list_projects(query: PaginationQuery):
    """List all projects with team counts and optional pagination."""
    total_count = count_projects()
    projects = get_all_projects(limit=query.limit, offset=query.offset or 0)
    return {"projects": projects, "total_count": total_count}, HTTPStatus.OK


@projects_bp.post("/")
def create_project():
    """Create a new project."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    name = data.get("name")
    if not name:
        return {"error": "name is required"}, HTTPStatus.BAD_REQUEST

    github_repo_raw = data.get("github_repo")
    local_path = data.get("local_path")

    # Normalize github_repo to 'owner/repo' slug and extract host for consistent storage
    github_repo = None
    github_host = None
    if github_repo_raw:
        github_host = ProjectWorkspaceService._extract_github_host(github_repo_raw)
        github_repo = ProjectWorkspaceService._normalize_github_repo(github_repo_raw)

    # Validate GitHub repository exists and is accessible (if provided)
    if github_repo:
        full_url = f"https://{github_host}/{github_repo}"
        if not GitHubService.validate_repo_url(full_url):
            return {
                "error": f"Invalid or inaccessible GitHub repo: {github_repo}"
            }, HTTPStatus.BAD_REQUEST

    project_id = add_project(
        name=name,
        description=data.get("description"),
        status=data.get("status", "active"),
        product_id=data.get("product_id"),
        github_repo=github_repo,
        owner_team_id=data.get("owner_team_id"),
        local_path=local_path,
        github_host=github_host,
    )
    if not project_id:
        return {"error": "Failed to create project"}, HTTPStatus.INTERNAL_SERVER_ERROR

    # Auto-clone if github_repo provided (async background clone)
    if github_repo:
        ProjectWorkspaceService.clone_async(project_id)

    project = get_project(project_id)
    response = {"message": "Project created", "project": project}
    if github_repo:
        response["clone_status"] = "cloning"
    return response, HTTPStatus.CREATED


@projects_bp.get("/<project_id>")
def get_project_detail_endpoint(path: ProjectPath):
    """Get project details with teams."""
    project = get_project_detail(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND
    return project, HTTPStatus.OK


@projects_bp.put("/<project_id>")
def update_project_endpoint(path: ProjectPath):
    """Update a project."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    if not update_project(
        path.project_id,
        name=data.get("name"),
        description=data.get("description"),
        status=data.get("status"),
        product_id=data.get("product_id"),
        github_repo=data.get("github_repo"),
        owner_team_id=data.get("owner_team_id"),
        local_path=data.get("local_path"),
        github_host=data.get("github_host"),
    ):
        return {"error": "Project not found or no changes made"}, HTTPStatus.NOT_FOUND

    project = get_project(path.project_id)
    return project, HTTPStatus.OK


@projects_bp.delete("/<project_id>")
def delete_project_endpoint(path: ProjectPath):
    """Delete a project."""
    if not delete_project(path.project_id):
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Project deleted"}, HTTPStatus.OK


# Team assignment routes
@projects_bp.get("/<project_id>/teams")
def list_project_teams(path: ProjectPath):
    """List teams assigned to a project."""
    teams = get_project_teams(path.project_id)
    return {"teams": teams}, HTTPStatus.OK


@projects_bp.post("/<project_id>/teams/<team_id>")
def assign_team(path: TeamAssignPath):
    """Assign a team to the project."""
    if not assign_team_to_project(path.project_id, path.team_id):
        return {"error": "Failed to assign team (may already be assigned)"}, HTTPStatus.BAD_REQUEST
    return {"message": "Team assigned"}, HTTPStatus.OK


@projects_bp.delete("/<project_id>/teams/<team_id>")
def unassign_team(path: TeamAssignPath):
    """Remove a team from the project."""
    if not unassign_team_from_project(path.project_id, path.team_id):
        return {"error": "Team assignment not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Team removed"}, HTTPStatus.OK


# Run team in project context
@projects_bp.post("/<project_id>/run-team/<team_id>")
def run_team_in_project(path: TeamAssignPath):
    """Run a team in the context of this project's working directory."""
    # Validate project exists
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    # Validate team exists
    team = get_team_detail(path.team_id)
    if not team:
        return {"error": "Team not found"}, HTTPStatus.NOT_FOUND

    # Validate team is assigned to this project
    project_teams = get_project_teams(path.project_id)
    team_ids = [t["id"] for t in project_teams]
    if project.get("owner_team_id") and project["owner_team_id"] not in team_ids:
        team_ids.append(project["owner_team_id"])
    if path.team_id not in team_ids:
        return {"error": "Team is not assigned to this project"}, HTTPStatus.BAD_REQUEST

    # Resolve working directory
    try:
        working_directory = ProjectWorkspaceService.resolve_working_directory(path.project_id)
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.BAD_REQUEST

    # Get optional message from request body
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")

    # Execute team
    try:
        team_exec_id = TeamExecutionService.execute_team(
            team_id=path.team_id,
            message=message,
            event={},
            trigger_type="manual",
            working_directory=working_directory,
        )
        return {
            "message": "Team execution started",
            "team_execution_id": team_exec_id,
            "working_directory": working_directory,
        }, HTTPStatus.OK
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.BAD_REQUEST


# Deploy routes
@projects_bp.post("/<project_id>/deploy")
def deploy_teams(path: ProjectPath):
    """Generate .claude/teams/ files for project teams.

    Returns generated file contents that can be saved to the project repo.
    """
    result, status = ProjectDeployService.deploy_to_project(path.project_id)
    return result, status


@projects_bp.get("/<project_id>/deploy/preview")
def preview_deploy(path: ProjectPath):
    """Preview what will be deployed without actually deploying.

    Returns the same structure as deploy but doesn't write files.
    """
    result, status = ProjectDeployService.get_deploy_preview(path.project_id)
    return result, status


# Harness routes
@projects_bp.get("/<project_id>/harness/status")
def harness_status(path: ProjectPath):
    """Check if .claude folder exists in the project's GitHub repo.

    Returns exists flag and list of available subdirectories.
    """
    result, status = HarnessService.check_harness_exists(path.project_id)
    return result, status


@projects_bp.post("/<project_id>/harness/load")
def load_harness(path: ProjectPath):
    """Load harness settings from GitHub repository.

    Imports agents, skills, hooks, commands from .claude folder.
    """
    result, status = HarnessService.load_from_github(path.project_id)
    return result, status


@projects_bp.post("/<project_id>/harness/deploy")
def deploy_harness(path: ProjectPath):
    """Deploy harness settings to GitHub repository.

    Generates .claude folder with teams and skills, creates a PR.
    """
    result, status = HarnessService.deploy_to_github(path.project_id)
    return result, status


# Project skills routes
@projects_bp.get("/<project_id>/skills")
def list_project_skills(path: ProjectPath):
    """List skills associated with a project."""
    skills = get_project_skills(path.project_id)
    return {"skills": skills}, HTTPStatus.OK


@projects_bp.post("/<project_id>/skills")
def add_skill_to_project(path: ProjectPath):
    """Add a skill to a project."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    skill_name = data.get("skill_name")
    if not skill_name:
        return {"error": "skill_name is required"}, HTTPStatus.BAD_REQUEST

    skill_id = add_project_skill(
        project_id=path.project_id,
        skill_name=skill_name,
        skill_path=data.get("skill_path"),
        source=data.get("source", "manual"),
    )
    if not skill_id:
        return {"error": "Failed to add skill (may already exist)"}, HTTPStatus.BAD_REQUEST

    return {"message": "Skill added", "skill_id": skill_id}, HTTPStatus.CREATED


class SkillPath(BaseModel):
    project_id: str = Field(..., description="Project ID")
    skill_id: int = Field(..., description="Skill ID")


@projects_bp.delete("/<project_id>/skills/<int:skill_id>")
def remove_skill_from_project(path: SkillPath):
    """Remove a skill from a project."""
    if not delete_project_skill_by_id(path.skill_id):
        return {"error": "Skill not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Skill removed"}, HTTPStatus.OK


# Component installation routes
@projects_bp.get("/<project_id>/installations")
def list_installations(path: ProjectPath):
    """List components installed to this project's .claude/ directory."""
    component_type = request.args.get("component_type")
    try:
        installations = ProjectInstallService.list_installations(
            path.project_id, component_type=component_type
        )
        return {"installations": installations}, HTTPStatus.OK
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.BAD_REQUEST


@projects_bp.post("/<project_id>/install")
def install_component(path: ProjectPath):
    """Install a component to the project's .claude/ directory."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    component_type = data.get("component_type")
    component_id = data.get("component_id")

    if not component_type or component_type not in (
        "agent",
        "skill",
        "hook",
        "command",
        "rule",
    ):
        return {
            "error": "Valid component_type required (agent, skill, hook, command, rule)"
        }, HTTPStatus.BAD_REQUEST

    if not component_id:
        return {"error": "component_id is required"}, HTTPStatus.BAD_REQUEST

    try:
        result = ProjectInstallService.install_component(
            path.project_id, component_type, component_id
        )
        return result, HTTPStatus.OK
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.BAD_REQUEST
    except Exception as e:
        return {"error": f"Install failed: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR


@projects_bp.post("/<project_id>/uninstall")
def uninstall_component(path: ProjectPath):
    """Uninstall a component from the project's .claude/ directory."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    component_type = data.get("component_type")
    component_id = data.get("component_id")

    if not component_type or component_type not in (
        "agent",
        "skill",
        "hook",
        "command",
        "rule",
    ):
        return {"error": "Valid component_type required"}, HTTPStatus.BAD_REQUEST

    if not component_id:
        return {"error": "component_id is required"}, HTTPStatus.BAD_REQUEST

    try:
        result = ProjectInstallService.uninstall_component(
            path.project_id, component_type, component_id
        )
        return result, HTTPStatus.OK
    except ValueError as e:
        return {"error": str(e)}, HTTPStatus.BAD_REQUEST
    except Exception as e:
        return {"error": f"Uninstall failed: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR


# Project team topology routes
@projects_bp.get("/<project_id>/team-edges")
def list_team_edges(path: ProjectPath):
    """List team-to-team edges for project org chart."""
    edges = get_project_team_edges(path.project_id)
    return {"edges": edges}, HTTPStatus.OK


@projects_bp.post("/<project_id>/team-edges")
def create_team_edge(path: ProjectPath):
    """Create a team-to-team edge in project org chart."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    source_team_id = data.get("source_team_id")
    target_team_id = data.get("target_team_id")
    if not source_team_id or not target_team_id:
        return {"error": "source_team_id and target_team_id required"}, HTTPStatus.BAD_REQUEST

    edge_id = add_project_team_edge(
        project_id=path.project_id,
        source_team_id=source_team_id,
        target_team_id=target_team_id,
        edge_type=data.get("edge_type", "dependency"),
        label=data.get("label"),
        weight=data.get("weight", 1),
    )
    if not edge_id:
        return {"error": "Failed to create edge (may already exist)"}, HTTPStatus.BAD_REQUEST

    return {"message": "Edge created", "edge_id": edge_id}, HTTPStatus.CREATED


@projects_bp.delete("/<project_id>/team-edges/<int:edge_id>")
def delete_team_edge(path: TeamEdgePath):
    """Delete a team-to-team edge."""
    if not delete_project_team_edge(path.edge_id):
        return {"error": "Edge not found"}, HTTPStatus.NOT_FOUND
    return {"message": "Edge deleted"}, HTTPStatus.OK


@projects_bp.put("/<project_id>/team-topology")
def update_team_topology(path: ProjectPath):
    """Update project team topology config (canvas positions)."""
    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    config = data.get("team_topology_config", "{}")
    if isinstance(config, dict):
        import json

        config = json.dumps(config)

    update_project_team_topology_config(path.project_id, config)
    return {"message": "Team topology config updated"}, HTTPStatus.OK


# Repository sync routes
@projects_bp.post("/<project_id>/sync")
def sync_project_repo(path: ProjectPath):
    """Trigger a git pull on the project's cloned repository.

    If the project's clone_status is 'error' or 'none', re-triggers an async clone.
    """
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    clone_status = project.get("clone_status", "none")
    if clone_status in ("error", "none") and project.get("github_repo"):
        ProjectWorkspaceService.clone_async(path.project_id)
        return {"status": "cloning", "message": "Clone re-triggered"}, HTTPStatus.OK

    result = ProjectWorkspaceService.sync_repo(path.project_id)
    status_code = HTTPStatus.OK if result["status"] == "ok" else HTTPStatus.BAD_REQUEST
    return result, status_code


@projects_bp.get("/<project_id>/clone-status")
def get_clone_status(path: ProjectPath):
    """Get the current clone status for a project."""
    project = get_project(path.project_id)
    if not project:
        return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

    return {
        "clone_status": project.get("clone_status", "none"),
        "clone_error": project.get("clone_error"),
        "last_synced_at": project.get("last_synced_at"),
    }, HTTPStatus.OK
