"""Pydantic models for prompt snippet API requests and responses."""

from typing import Optional

from pydantic import BaseModel, Field


class CreateSnippetRequest(BaseModel):
    """Request body for creating a prompt snippet."""

    name: str = Field(..., min_length=1, pattern=r"^[\w][\w-]*$")
    content: str = Field(..., min_length=1)
    description: str = Field(default="")


class UpdateSnippetRequest(BaseModel):
    """Request body for updating a prompt snippet."""

    name: Optional[str] = Field(default=None, min_length=1, pattern=r"^[\w][\w-]*$")
    content: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = Field(default=None)


class SnippetResponse(BaseModel):
    """Response model for a prompt snippet."""

    id: str
    name: str
    content: str
    description: str
    is_global: int
    created_at: str
    updated_at: str


class ResolveSnippetRequest(BaseModel):
    """Request body for resolving snippet references in text."""

    text: str = Field(..., min_length=1)
