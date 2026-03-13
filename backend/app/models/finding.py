"""Pydantic models for findings triage."""

from typing import Optional

from pydantic import BaseModel, Field


class FindingCreate(BaseModel):
    """Request model for creating a finding."""

    title: str = Field(..., description="Finding title")
    description: Optional[str] = Field(None, description="Detailed description")
    severity: str = Field(..., description="Severity level: critical, high, medium, low")
    bot_id: Optional[str] = Field(None, description="Bot that surfaced the finding")
    file_ref: Optional[str] = Field(None, description="File reference (path:line)")
    owner: Optional[str] = Field(None, description="Assigned owner username")
    execution_id: Optional[str] = Field(None, description="Originating execution ID")


class FindingUpdate(BaseModel):
    """Request model for partially updating a finding."""

    status: Optional[str] = Field(None, description="New status: open, in_progress, resolved, wont_fix")
    owner: Optional[str] = Field(None, description="Assigned owner username")


class FindingPath(BaseModel):
    """Path parameter for finding ID."""

    finding_id: str = Field(..., description="Finding ID")
