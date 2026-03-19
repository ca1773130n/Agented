"""Project instance-related Pydantic models."""

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class CreateInstanceRequest(BaseModel):
    """Request body for creating a project instance (SA or team)."""

    team_id: Optional[str] = Field(None, description="Team ID to create a team instance from")
    super_agent_id: Optional[str] = Field(
        None, description="Super agent ID to create an SA instance from"
    )

    @model_validator(mode="after")
    def require_one_of(self) -> "CreateInstanceRequest":
        """Ensure at least one of team_id or super_agent_id is provided."""
        if self.team_id is None and self.super_agent_id is None:
            raise ValueError("At least one of team_id or super_agent_id must be provided")
        return self


class ProjectSAInstance(BaseModel):
    """Project super-agent instance entity."""

    id: str = Field(
        ...,
        pattern=r"^psa-[a-z0-9]+$",
        description="Instance ID",
        examples=["psa-abc123"],
    )
    project_id: str = Field(..., description="Project this instance belongs to")
    template_sa_id: str = Field(
        ..., description="Template super agent ID this instance is based on"
    )
    worktree_path: Optional[str] = Field(None, description="Git worktree path for this instance")
    default_chat_mode: str = Field(default="management", description="Default chat mode")
    config_overrides: Optional[str] = Field(None, description="JSON config overrides")
    created_at: Optional[str] = Field(None, description="Creation timestamp (ISO 8601)")
    updated_at: Optional[str] = Field(None, description="Last update timestamp (ISO 8601)")
    # Joined fields from template super agent
    sa_name: Optional[str] = Field(None, description="Name of the template super agent")
    sa_description: Optional[str] = Field(
        None, description="Description of the template super agent"
    )
    sa_backend_type: Optional[str] = Field(
        None, description="Backend type of the template super agent"
    )


class ProjectTeamInstance(BaseModel):
    """Project team instance entity."""

    id: str = Field(
        ...,
        pattern=r"^pti-[a-z0-9]+$",
        description="Instance ID",
        examples=["pti-abc123"],
    )
    project_id: str = Field(..., description="Project this instance belongs to")
    template_team_id: str = Field(..., description="Template team ID this instance is based on")
    config_overrides: Optional[str] = Field(None, description="JSON config overrides")
    created_at: Optional[str] = Field(None, description="Creation timestamp (ISO 8601)")
    updated_at: Optional[str] = Field(None, description="Last update timestamp (ISO 8601)")


class SAInstanceInfo(BaseModel):
    """Abbreviated SA instance info used in create response."""

    id: str = Field(..., description="Instance ID")
    template_sa_id: str = Field(..., description="Template super agent ID")
    worktree_path: Optional[str] = Field(None, description="Git worktree path for this instance")
    session_id: Optional[str] = Field(None, description="Active session ID, if any")


class CreateInstanceResponse(BaseModel):
    """Response after creating project instances."""

    team_instance_id: Optional[str] = Field(None, description="Created team instance ID, if any")
    sa_instances: List[SAInstanceInfo] = Field(
        default_factory=list, description="Created SA instances"
    )


class InstanceListResponse(BaseModel):
    """Response for listing project SA instances."""

    instances: List[ProjectSAInstance]


class ProjectInstancePath(BaseModel):
    """Path parameters for project instance endpoints."""

    project_id: str = Field(..., description="Project ID")
    instance_id: str = Field(..., description="Instance ID")
