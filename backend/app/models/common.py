"""Common response models used across the API."""

from typing import Optional

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: str = Field(..., description="Error message", examples=["Bot not found"])


class MessageResponse(BaseModel):
    """Standard success message response."""

    message: str = Field(..., description="Success message", examples=["Bot updated"])


class PaginationQuery(BaseModel):
    """Shared pagination query parameters for list endpoints."""

    limit: Optional[int] = Field(None, ge=1, le=500, description="Max records to return")
    offset: Optional[int] = Field(None, ge=0, description="Number of records to skip")
