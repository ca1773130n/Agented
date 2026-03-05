"""Pydantic models for campaign management."""

from typing import List, Optional

from pydantic import BaseModel, Field


class CampaignCreate(BaseModel):
    """Request body for creating a new campaign."""

    name: str = Field(..., min_length=1, max_length=200, description="Campaign name")
    trigger_id: str = Field(..., description="Trigger to execute across repos")
    repo_urls: List[str] = Field(
        ..., min_length=1, description="List of repository URLs (at least 1)"
    )


class CampaignResponse(BaseModel):
    """Response model for a campaign."""

    id: str
    name: str
    trigger_id: str
    status: str
    repo_urls: List[str]
    total_repos: int
    completed_repos: int
    failed_repos: int
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    created_at: Optional[str] = None


class CampaignExecutionResponse(BaseModel):
    """Response model for a single campaign execution (per-repo)."""

    campaign_id: str
    execution_id: Optional[str] = None
    repo_url: str
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_message: Optional[str] = None


class CampaignPath(BaseModel):
    """Path parameter for campaign endpoints."""

    campaign_id: str = Field(..., description="Campaign ID")


class CampaignListQuery(BaseModel):
    """Query parameters for listing campaigns."""

    trigger_id: Optional[str] = Field(None, description="Filter by trigger ID")
    status: Optional[str] = Field(None, description="Filter by status")


class TriggerCampaignPath(BaseModel):
    """Path parameter for trigger-scoped campaign endpoints."""

    trigger_id: str = Field(..., description="Trigger ID")
