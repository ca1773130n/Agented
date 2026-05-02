"""Projects namespace — full /admin/projects/* port (track A, wave 55).

29 handlers covering CRUD, team assignments, deploy, harness, skills,
installations, team-edges, sync, health, manager, sessions. The
auto-clone + GRD-init background thread on POST / is preserved verbatim.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)
from msgspec import Struct

from app.database import (
    add_project_skill,
    add_project_team_edge,
    add_super_agent_document,
    assign_team_to_project,
    count_projects,
    create_super_agent,
    delete_project,
    delete_project_skill_by_id,
    delete_project_team_edge,
    get_all_projects,
    get_project,
    get_project_detail,
    get_project_skills,
    get_project_team_edges,
    get_project_teams,
    get_super_agent,
    get_team_detail,
    unassign_team_from_project,
    update_project,
    update_project_team_topology_config,
)
from app.database import create_project as db_create_project
from app.db.owned_entities import get_for_user
from app.services.github_service import GitHubService
from app.services.grd_planning_service import GrdPlanningService
from app.services.harness_service import HarnessService
from app.services.project_deploy_service import ProjectDeployService
from app.services.project_health_service import ProjectHealthService
from app.services.project_install_service import ProjectInstallService
from app.services.project_workspace_service import ProjectWorkspaceService
from app.services.team_execution_service import TeamExecutionService

from ..auth import Caller


def _result_or_raise(payload: tuple[dict, int]) -> dict:
    body, status = payload
    if status >= 400:
        raise HTTPException(status_code=status, detail=body)
    return body


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@get("/", sync_to_thread=False)
def list_projects(
    caller: Caller, limit: Optional[int] = None, offset: Optional[int] = None
) -> dict[str, Any]:
    if caller.user_id:
        rows = get_for_user(
            "projects", caller.user_id, limit=limit, offset=offset or 0
        )
        return {"projects": rows, "total_count": len(rows)}
    return {
        "projects": get_all_projects(limit=limit, offset=offset or 0),
        "total_count": count_projects(),
    }


@post("/", sync_to_thread=False)
def create_project(data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")

    name = data.get("name")
    if not name:
        raise ClientException(detail="name is required")

    github_repo_raw = data.get("github_repo")
    local_path = data.get("local_path")

    github_repo = None
    github_host = None
    if github_repo_raw:
        github_host = ProjectWorkspaceService._extract_github_host(github_repo_raw)
        github_repo = ProjectWorkspaceService._normalize_github_repo(github_repo_raw)

    if github_repo:
        full_url = f"https://{github_host}/{github_repo}"
        if not GitHubService.validate_repo_url(full_url):
            raise ClientException(
                detail=f"Invalid or inaccessible GitHub repo: {github_repo}"
            )

    project_id = db_create_project(
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
        raise HTTPException(status_code=500, detail="Failed to create project")

    if github_repo:
        ProjectWorkspaceService.clone_async(project_id)

    if local_path and not github_repo:
        GrdPlanningService.auto_init_project(project_id, local_path)
    elif github_repo:
        def _wait_for_clone_and_init(proj_id: str) -> None:
            for _ in range(120):
                time.sleep(2)
                p = get_project(proj_id)
                if not p:
                    return
                status = p.get("clone_status", "none")
                if status == "cloned":
                    lp = p.get("local_path")
                    if lp:
                        GrdPlanningService.auto_init_project(proj_id, lp)
                    return
                if status == "failed":
                    return

        t = threading.Thread(
            target=_wait_for_clone_and_init,
            args=(project_id,),
            daemon=True,
            name=f"grd-clone-wait-{project_id}",
        )
        t.start()

    project = get_project(project_id)
    response: dict[str, Any] = {"message": "Project created", "project": project}
    if github_repo:
        response["clone_status"] = "cloning"
        response["grd_init_status"] = "pending"
    elif local_path:
        response["grd_init_status"] = "initializing"
    return response


@get("/{project_id:str}", sync_to_thread=False)
def get_project_detail_endpoint(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    project = get_project_detail(project_id)
    if not project:
        raise NotFoundException(detail="Project not found")
    return project


@put("/{project_id:str}", sync_to_thread=False)
def update_project_endpoint(
    project_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    if not update_project(
        project_id,
        name=data.get("name"),
        description=data.get("description"),
        status=data.get("status"),
        product_id=data.get("product_id"),
        github_repo=data.get("github_repo"),
        owner_team_id=data.get("owner_team_id"),
        local_path=data.get("local_path"),
        github_host=data.get("github_host"),
    ):
        raise NotFoundException(detail="Project not found or no changes made")
    return get_project(project_id)


@delete("/{project_id:str}", status_code=200, sync_to_thread=False)
def delete_project_endpoint(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    if not delete_project(project_id):
        raise NotFoundException(detail="Project not found")
    return {"message": "Project deleted"}


# ---------------------------------------------------------------------------
# Team assignments
# ---------------------------------------------------------------------------


@get("/{project_id:str}/teams", sync_to_thread=False)
def list_project_teams(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return {"teams": get_project_teams(project_id)}


@post("/{project_id:str}/teams/{team_id:str}", sync_to_thread=False)
def assign_team(project_id: str, team_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    if not assign_team_to_project(project_id, team_id):
        raise ClientException(detail="Failed to assign team (may already be assigned)")
    return {"message": "Team assigned"}


@delete(
    "/{project_id:str}/teams/{team_id:str}", status_code=200, sync_to_thread=False
)
def unassign_team(project_id: str, team_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    if not unassign_team_from_project(project_id, team_id):
        raise NotFoundException(detail="Team assignment not found")
    return {"message": "Team removed"}


class RunTeamBody(Struct):
    message: str = ""


@post("/{project_id:str}/run-team/{team_id:str}", sync_to_thread=False)
def run_team_in_project(
    project_id: str,
    team_id: str,
    data: RunTeamBody,
    caller: Caller,
) -> dict[str, Any]:
    del caller
    project = get_project(project_id)
    if not project:
        raise NotFoundException(detail="Project not found")
    team = get_team_detail(team_id)
    if not team:
        raise NotFoundException(detail="Team not found")

    project_teams = get_project_teams(project_id)
    team_ids = [t["id"] for t in project_teams]
    if project.get("owner_team_id") and project["owner_team_id"] not in team_ids:
        team_ids.append(project["owner_team_id"])
    if team_id not in team_ids:
        raise ClientException(detail="Team is not assigned to this project")

    try:
        working_directory = ProjectWorkspaceService.resolve_working_directory(project_id)
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None

    try:
        team_exec_id = TeamExecutionService.execute_team(
            team_id=team_id,
            message=data.message or "",
            event={},
            trigger_type="manual",
            working_directory=working_directory,
        )
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None
    return {
        "message": "Team execution started",
        "team_execution_id": team_exec_id,
        "working_directory": working_directory,
    }


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------


@post("/{project_id:str}/deploy", sync_to_thread=False)
def deploy_teams(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(ProjectDeployService.deploy_to_project(project_id))


@get("/{project_id:str}/deploy/preview", sync_to_thread=False)
def preview_deploy(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(ProjectDeployService.get_deploy_preview(project_id))


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


@get("/{project_id:str}/harness/status", sync_to_thread=False)
def harness_status(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(HarnessService.check_harness_exists(project_id))


@post("/{project_id:str}/harness/load", sync_to_thread=False)
def load_harness(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(HarnessService.load_from_github(project_id))


@post("/{project_id:str}/harness/deploy", sync_to_thread=False)
def deploy_harness(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(HarnessService.deploy_to_github(project_id))


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


@get("/{project_id:str}/skills", sync_to_thread=False)
def list_project_skills(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return {"skills": get_project_skills(project_id)}


@post("/{project_id:str}/skills", sync_to_thread=False)
def add_skill_to_project(
    project_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    skill_name = data.get("skill_name")
    if not skill_name:
        raise ClientException(detail="skill_name is required")
    skill_id = add_project_skill(
        project_id=project_id,
        skill_name=skill_name,
        skill_path=data.get("skill_path"),
        source=data.get("source", "manual"),
    )
    if not skill_id:
        raise ClientException(detail="Failed to add skill (may already exist)")
    return {"message": "Skill added", "skill_id": skill_id}


@delete(
    "/{project_id:str}/skills/{skill_id:int}", status_code=200, sync_to_thread=False
)
def remove_skill_from_project(
    project_id: str, skill_id: int, caller: Caller
) -> dict[str, Any]:
    del caller, project_id
    if not delete_project_skill_by_id(skill_id):
        raise NotFoundException(detail="Skill not found")
    return {"message": "Skill removed"}


# ---------------------------------------------------------------------------
# Installations
# ---------------------------------------------------------------------------


_VALID_COMPONENT_TYPES = ("agent", "skill", "hook", "command", "rule")


@get("/{project_id:str}/installations", sync_to_thread=False)
def list_installations(
    project_id: str, caller: Caller, component_type: Optional[str] = None
) -> dict[str, Any]:
    del caller
    try:
        installations = ProjectInstallService.list_installations(
            project_id, component_type=component_type
        )
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None
    return {"installations": installations}


def _install_op(
    fn,
    project_id: str,
    data: dict,
):
    if not data:
        raise ClientException(detail="JSON body required")
    component_type = data.get("component_type")
    component_id = data.get("component_id")
    if component_type not in _VALID_COMPONENT_TYPES:
        raise ClientException(
            detail=f"Valid component_type required ({', '.join(_VALID_COMPONENT_TYPES)})"
        )
    if not component_id:
        raise ClientException(detail="component_id is required")
    try:
        return fn(project_id, component_type, component_id)
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"Operation failed: {exc}"
        ) from None


@post("/{project_id:str}/install", sync_to_thread=False)
def install_component(
    project_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    return _install_op(ProjectInstallService.install_component, project_id, data)


@post("/{project_id:str}/uninstall", sync_to_thread=False)
def uninstall_component(
    project_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    return _install_op(ProjectInstallService.uninstall_component, project_id, data)


# ---------------------------------------------------------------------------
# Team edges (project-scoped org chart)
# ---------------------------------------------------------------------------


@get("/{project_id:str}/team-edges", sync_to_thread=False)
def list_team_edges(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return {"edges": get_project_team_edges(project_id)}


@post("/{project_id:str}/team-edges", sync_to_thread=False)
def create_team_edge(
    project_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    source_team_id = data.get("source_team_id")
    target_team_id = data.get("target_team_id")
    if not source_team_id or not target_team_id:
        raise ClientException(
            detail="source_team_id and target_team_id required"
        )
    edge_id = add_project_team_edge(
        project_id=project_id,
        source_team_id=source_team_id,
        target_team_id=target_team_id,
        edge_type=data.get("edge_type", "dependency"),
        label=data.get("label"),
        weight=data.get("weight", 1),
    )
    if not edge_id:
        raise ClientException(detail="Failed to create edge (may already exist)")
    return {"message": "Edge created", "edge_id": edge_id}


@delete(
    "/{project_id:str}/team-edges/{edge_id:int}",
    status_code=200,
    sync_to_thread=False,
)
def delete_team_edge_endpoint(
    project_id: str, edge_id: int, caller: Caller
) -> dict[str, Any]:
    del caller, project_id
    if not delete_project_team_edge(edge_id):
        raise NotFoundException(detail="Edge not found")
    return {"message": "Edge deleted"}


@put("/{project_id:str}/team-topology", sync_to_thread=False)
def update_team_topology(
    project_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    config = data.get("team_topology_config", "{}")
    if isinstance(config, dict):
        config = json.dumps(config)
    update_project_team_topology_config(project_id, config)
    return {"message": "Team topology config updated"}


# ---------------------------------------------------------------------------
# Sync / health / clone-status / manager / sessions
# ---------------------------------------------------------------------------


@post("/{project_id:str}/sync", sync_to_thread=False)
def sync_project_repo(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    project = get_project(project_id)
    if not project:
        raise NotFoundException(detail="Project not found")
    clone_status = project.get("clone_status", "none")
    if clone_status in ("error", "none") and project.get("github_repo"):
        ProjectWorkspaceService.clone_async(project_id)
        return {"status": "cloning", "message": "Clone re-triggered"}
    result = ProjectWorkspaceService.sync_repo(project_id)
    if result["status"] != "ok":
        raise HTTPException(status_code=400, detail=result)
    return result


@get("/{project_id:str}/health-scorecard", sync_to_thread=False)
def get_health_scorecard(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    scorecard = ProjectHealthService.compute_scorecard(project_id)
    if scorecard is None:
        raise NotFoundException(detail="Project not found")
    return scorecard


@get("/{project_id:str}/clone-status", sync_to_thread=False)
def get_clone_status(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    project = get_project(project_id)
    if not project:
        raise NotFoundException(detail="Project not found")
    return {
        "clone_status": project.get("clone_status", "none"),
        "clone_error": project.get("clone_error"),
        "last_synced_at": project.get("last_synced_at"),
    }


@get("/{project_id:str}/manager", sync_to_thread=False)
def get_or_create_manager(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    project = get_project(project_id)
    if not project:
        raise NotFoundException(detail="Project not found")

    sa_id = project.get("manager_super_agent_id")
    if sa_id:
        sa = get_super_agent(sa_id)
        if sa:
            return {"super_agent_id": sa_id, "created": False}
        # linked agent gone — fall through to recreate

    project_name = project.get("name", "Unnamed Project")
    sa_id = create_super_agent(
        name=f"{project_name} Manager",
        description=f"AI manager for project '{project_name}'.",
        backend_type="claude",
    )
    if not sa_id:
        raise HTTPException(status_code=500, detail="Failed to create manager agent")

    role_content = (
        f"You are the project manager for '{project_name}'.\n\n"
        "Manage the kanban board by emitting plan-action markers in your responses."
    )
    add_super_agent_document(sa_id, "ROLE", "Project Manager Role", role_content)
    update_project(project_id, manager_super_agent_id=sa_id)
    return {"super_agent_id": sa_id, "created": True}


@get("/{project_id:str}/sessions", sync_to_thread=False)
def list_project_sessions(
    project_id: str, caller: Caller, status: Optional[str] = None
) -> dict[str, Any]:
    del caller
    from app.db.super_agents import get_sessions_for_project

    return {"sessions": get_sessions_for_project(project_id, status=status)}


projects_router = Router(
    path="/admin/projects",
    route_handlers=[
        list_projects,
        create_project,
        get_project_detail_endpoint,
        update_project_endpoint,
        delete_project_endpoint,
        list_project_teams,
        assign_team,
        unassign_team,
        run_team_in_project,
        deploy_teams,
        preview_deploy,
        harness_status,
        load_harness,
        deploy_harness,
        list_project_skills,
        add_skill_to_project,
        remove_skill_from_project,
        list_installations,
        install_component,
        uninstall_component,
        list_team_edges,
        create_team_edge,
        delete_team_edge_endpoint,
        update_team_topology,
        sync_project_repo,
        get_health_scorecard,
        get_clone_status,
        get_or_create_manager,
        list_project_sessions,
    ],
)
