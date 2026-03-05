"""Pydantic models for execution log search."""

from typing import List, Optional

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    """Query parameters for execution log search."""

    q: str = Field(..., description="Search query string")
    limit: int = Field(default=50, le=200, description="Maximum results to return")
    trigger_id: Optional[str] = Field(default=None, description="Filter by trigger ID")


class SearchResult(BaseModel):
    """A single search result from execution log full-text search."""

    execution_id: str = Field(..., description="Execution ID")
    trigger_id: str = Field(..., description="Trigger ID")
    trigger_name: Optional[str] = Field(default=None, description="Trigger name")
    started_at: str = Field(..., description="Execution start timestamp")
    status: str = Field(..., description="Execution status")
    prompt: Optional[str] = Field(default=None, description="Execution prompt")
    stdout_match: Optional[str] = Field(default=None, description="Highlighted stdout snippet")
    stderr_match: Optional[str] = Field(default=None, description="Highlighted stderr snippet")


class SearchResponse(BaseModel):
    """Response for execution log search."""

    results: List[SearchResult] = Field(default_factory=list, description="Search results")
    total: int = Field(..., description="Total number of results")
    query: str = Field(..., description="Original search query")


class SearchStats(BaseModel):
    """Statistics about the search index."""

    indexed_documents: int = Field(..., description="Number of indexed execution logs")
