"""Sketch-related Pydantic models."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class SketchStatus(str, Enum):
    """Sketch status values."""

    DRAFT = "draft"
    CLASSIFIED = "classified"
    ROUTED = "routed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class Sketch(BaseModel):
    """Sketch entity - a work item that gets classified and routed."""

    id: str = Field(..., pattern=r"^sketch-[a-z0-9]+$", examples=["sketch-abc123"])
    title: str = Field(..., examples=["Add user auth"])
    content: str = ""
    project_id: Optional[str] = None
    status: SketchStatus = SketchStatus.DRAFT
    classification_json: Optional[str] = None
    routing_json: Optional[str] = None
    parent_sketch_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# --- List responses ---


class SketchListResponse(BaseModel):
    """Response for listing all sketches."""

    sketches: List[Sketch]


# --- Create requests ---


class CreateSketchRequest(BaseModel):
    """Request body for creating a sketch."""

    title: str = Field(..., min_length=1)
    content: Optional[str] = None
    project_id: Optional[str] = None


class CreateSketchResponse(BaseModel):
    """Response after creating a sketch."""

    message: str
    sketch_id: str


# --- Update requests ---


class UpdateSketchRequest(BaseModel):
    """Request body for updating a sketch."""

    title: Optional[str] = None
    content: Optional[str] = None
    project_id: Optional[str] = None
    status: Optional[SketchStatus] = None
    classification_json: Optional[str] = None
    routing_json: Optional[str] = None
    parent_sketch_id: Optional[str] = None
