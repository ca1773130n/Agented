"""Project-related Pydantic models."""

from typing import List, Optional

from pydantic import BaseModel, Field


class ProjectTeam(BaseModel):
    """Simplified team for project detail."""

    id: str
    name: str
    color: str = "#00d4ff"


class Project(BaseModel):
    """Project entity."""

    id: str = Field(..., pattern=r"^proj-[a-z0-9]+$", examples=["proj-abc123"])
    name: str = Field(..., examples=["API Gateway"])
    description: Optional[str] = None
    status: str = Field(default="active")
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    github_repo: Optional[str] = None
    team_count: int = Field(default=0)
    grd_config: Optional[str] = None
    grd_sync_hash: Optional[str] = None
    grd_sync_at: Optional[str] = None
    current_milestone_id: Optional[str] = None
    worktree_base_path: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProjectDetail(Project):
    """Project with full team list."""

    teams: List[ProjectTeam] = Field(default_factory=list)


class ProjectListResponse(BaseModel):
    """Response for list projects endpoint."""

    projects: List[Project]


class CreateProjectRequest(BaseModel):
    """Request body for creating a project."""

    name: str = Field(..., min_length=1, examples=["API Gateway"])
    description: Optional[str] = None
    status: Optional[str] = Field(default="active")
    product_id: Optional[str] = None
    github_repo: str = Field(..., min_length=1, examples=["org/repo"])


class CreateProjectResponse(BaseModel):
    """Response for create project endpoint."""

    message: str
    project: Project


class UpdateProjectRequest(BaseModel):
    """Request body for updating a project."""

    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    product_id: Optional[str] = None
    github_repo: Optional[str] = None
    grd_config: Optional[str] = None
    current_milestone_id: Optional[str] = None
    worktree_base_path: Optional[str] = None


class AssignTeamRequest(BaseModel):
    """Request body for assigning a team to a project."""

    team_id: str = Field(..., min_length=1)


class InstallComponentRequest(BaseModel):
    """Request body for installing a component to a project."""

    component_type: str = Field(..., pattern=r"^(agent|skill|hook|command|rule)$")
    component_id: str = Field(..., min_length=1)


class InstallComponentResponse(BaseModel):
    """Response for install/uninstall component endpoint."""

    installed: bool = False
    uninstalled: bool = False
    path: Optional[str] = None
    error: Optional[str] = None


class ProjectInstallation(BaseModel):
    """A component installation record."""

    id: int
    project_id: str
    component_type: str
    component_id: str
    component_name: Optional[str] = None
    installed_at: Optional[str] = None
