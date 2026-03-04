"""Pydantic models for GitOps management endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


class GitOpsRepoCreate(BaseModel):
    """Request model for creating a GitOps repo configuration."""

    name: str = Field(..., description="Human-readable name for this repo")
    repo_url: str = Field(..., description="Git repository URL")
    branch: str = Field("main", description="Branch to watch")
    config_path: str = Field("agented/", description="Path within repo for configs")
    poll_interval_seconds: int = Field(60, description="Polling interval in seconds", ge=10)


class GitOpsRepoUpdate(BaseModel):
    """Request model for updating a GitOps repo configuration."""

    name: Optional[str] = Field(None, description="Human-readable name")
    repo_url: Optional[str] = Field(None, description="Git repository URL")
    branch: Optional[str] = Field(None, description="Branch to watch")
    config_path: Optional[str] = Field(None, description="Path within repo for configs")
    poll_interval_seconds: Optional[int] = Field(None, description="Polling interval in seconds")
    enabled: Optional[bool] = Field(None, description="Whether sync is enabled")


class GitOpsRepoPath(BaseModel):
    """Path parameter for repo ID."""

    repo_id: str = Field(..., description="GitOps repo ID")


class GitOpsSyncQuery(BaseModel):
    """Query params for sync endpoint."""

    dry_run: Optional[bool] = Field(False, description="Preview changes without applying")


class GitOpsSyncLogQuery(BaseModel):
    """Query params for sync log listing."""

    limit: Optional[int] = Field(20, description="Max entries to return", ge=1, le=100)
