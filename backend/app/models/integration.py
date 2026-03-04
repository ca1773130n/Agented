"""Pydantic models for integration CRUD and request/response validation."""

from typing import Optional

from pydantic import BaseModel, Field


class IntegrationCreate(BaseModel):
    """Request body for creating an integration."""

    name: str = Field(..., description="Display name for the integration")
    type: str = Field(
        ..., description="Integration type: slack, teams, jira, or linear"
    )
    config: dict = Field(
        default_factory=dict, description="Non-secret configuration (channel, project key, etc.)"
    )
    trigger_id: Optional[str] = Field(
        None, description="Link to a specific trigger, or null for global"
    )
    secret_name: Optional[str] = Field(
        None, description="Name of the secret in the vault containing credentials"
    )


class IntegrationUpdate(BaseModel):
    """Request body for updating an integration."""

    name: Optional[str] = None
    config: Optional[dict] = None
    trigger_id: Optional[str] = None
    enabled: Optional[bool] = None


class IntegrationResponse(BaseModel):
    """Response model for an integration."""

    id: str
    name: str
    type: str
    config: dict
    trigger_id: Optional[str]
    enabled: int
    created_at: str
    updated_at: str


class IntegrationPath(BaseModel):
    """Path parameters for integration endpoints."""

    integration_id: str = Field(..., description="Integration ID")


class IntegrationTestRequest(BaseModel):
    """Request body for testing an integration."""

    integration_id: str = Field(..., description="Integration ID to test")


class IntegrationQuery(BaseModel):
    """Query parameters for listing integrations."""

    type: Optional[str] = Field(None, description="Filter by integration type")
    trigger_id: Optional[str] = Field(None, description="Filter by trigger ID")


class TriggerIntegrationPath(BaseModel):
    """Path parameters for trigger-scoped integration listing."""

    trigger_id: str = Field(..., description="Trigger ID")
