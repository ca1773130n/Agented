"""Pydantic models for bot template API requests and responses."""

from typing import Optional

from pydantic import BaseModel, Field


class BotTemplateResponse(BaseModel):
    """Response model for a single bot template."""

    id: str
    slug: str
    name: str
    description: str
    category: str
    icon: str = ""
    config_json: str
    sort_order: int = 0
    source: str = "built-in"
    is_published: int = 1
    created_at: Optional[str] = None


class BotTemplateDeployResponse(BaseModel):
    """Response model for deploying a bot template."""

    trigger_id: str = Field(..., description="ID of the newly created trigger")
    template_id: str = Field(..., description="ID of the deployed template")
    trigger_name: str = Field(..., description="Name assigned to the new trigger")
    message: str = Field(..., description="Human-readable deployment status message")
