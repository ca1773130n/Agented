"""Command-related Pydantic models."""

from typing import Optional

from pydantic import BaseModel, Field


class CreateCommandRequest(BaseModel):
    """Request body for creating a command."""

    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    content: Optional[str] = None
    arguments: Optional[str] = None
    enabled: bool = Field(default=True)
    project_id: Optional[str] = None
    source_path: Optional[str] = None


class UpdateCommandRequest(BaseModel):
    """Request body for updating a command."""

    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    arguments: Optional[str] = None
    enabled: Optional[bool] = None


class GenerateCommandRequest(BaseModel):
    """Request body for generating a command from a description."""

    description: str = Field(..., min_length=10)
