"""Pydantic models for execution bookmarks."""

from typing import Optional

from pydantic import BaseModel, Field


class BookmarkCreate(BaseModel):
    """Request model for creating a bookmark."""

    execution_id: str = Field(..., description="Execution ID to bookmark")
    trigger_id: str = Field(..., description="Trigger ID associated with the execution")
    title: str = Field(..., description="Bookmark title")
    notes: str = Field("", description="Optional notes")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    line_number: Optional[int] = Field(None, description="Line number for deep-link anchor")


class BookmarkUpdate(BaseModel):
    """Request model for updating a bookmark."""

    title: Optional[str] = Field(None, description="Updated title")
    notes: Optional[str] = Field(None, description="Updated notes")
    tags: Optional[list[str]] = Field(None, description="Updated tags")


class BookmarkResponse(BaseModel):
    """Response model for a bookmark."""

    id: str
    execution_id: str
    trigger_id: str
    title: str
    notes: str
    tags: list[str]
    line_number: Optional[int]
    deep_link: str
    created_by: str
    created_at: str


class BookmarkPath(BaseModel):
    """Path parameter for bookmark ID."""

    bookmark_id: str = Field(..., description="Bookmark ID")


class TriggerBookmarkPath(BaseModel):
    """Path parameter for trigger ID in bookmark context."""

    trigger_id: str = Field(..., description="Trigger ID")
