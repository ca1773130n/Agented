"""Rotation, product decision, product milestone, and team connection Pydantic models."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RotationUrgency(str, Enum):
    """Rotation urgency levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class RotationStatus(str, Enum):
    """Rotation event status values."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# --- Entity models ---


class RotationEvent(BaseModel):
    """Rotation event entity -- tracks account rotation during execution."""

    id: str = Field(..., pattern=r"^rot-[a-z0-9]+$", examples=["rot-abc12345"])
    execution_id: str
    from_account_id: Optional[int] = None
    to_account_id: Optional[int] = None
    reason: Optional[str] = None
    urgency: RotationUrgency = RotationUrgency.NORMAL
    utilization_at_rotation: Optional[float] = None
    rotation_status: RotationStatus = RotationStatus.PENDING
    continuation_execution_id: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class ProductDecision(BaseModel):
    """Product decision entity -- records architectural/technical decisions."""

    id: str = Field(..., pattern=r"^pdec-[a-z0-9]+$", examples=["pdec-abc123"])
    product_id: str
    title: str
    description: Optional[str] = None
    rationale: Optional[str] = None
    tags_json: Optional[str] = None
    decision_type: str = "technical"
    status: str = "proposed"
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    context_json: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProductMilestone(BaseModel):
    """Product milestone entity -- product-level versioned delivery target."""

    id: str = Field(..., pattern=r"^pms-[a-z0-9]+$", examples=["pms-abc123"])
    product_id: str
    version: str
    title: str
    description: Optional[str] = None
    status: str = "planning"
    target_date: Optional[str] = None
    sort_order: int = 0
    progress_pct: int = 0
    completed_date: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TeamConnection(BaseModel):
    """Team connection entity -- directed relationship between teams."""

    id: int
    source_team_id: str
    target_team_id: str
    connection_type: str = "dependency"
    description: Optional[str] = None
    created_at: Optional[str] = None


# --- List response models ---


class RotationEventListResponse(BaseModel):
    """Response for listing rotation events."""

    events: List[RotationEvent]


class ProductDecisionListResponse(BaseModel):
    """Response for listing product decisions."""

    decisions: List[ProductDecision]


class ProductMilestoneListResponse(BaseModel):
    """Response for listing product milestones."""

    milestones: List[ProductMilestone]


class TeamConnectionListResponse(BaseModel):
    """Response for listing team connections."""

    connections: List[TeamConnection]


# --- Create request models ---


class CreateRotationEventRequest(BaseModel):
    """Request body for creating a rotation event."""

    execution_id: str = Field(..., min_length=1)
    from_account_id: Optional[int] = None
    to_account_id: Optional[int] = None
    reason: Optional[str] = None
    urgency: Optional[str] = "normal"


class CreateProductDecisionRequest(BaseModel):
    """Request body for creating a product decision."""

    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    rationale: Optional[str] = None
    tags: Optional[list] = None
    decision_type: Optional[str] = "technical"


class CreateProductMilestoneRequest(BaseModel):
    """Request body for creating a product milestone."""

    version: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    target_date: Optional[str] = None
    sort_order: Optional[int] = 0
    progress_pct: Optional[int] = 0


class CreateTeamConnectionRequest(BaseModel):
    """Request body for creating a team connection."""

    source_team_id: str = Field(..., min_length=1)
    target_team_id: str = Field(..., min_length=1)
    connection_type: Optional[str] = "dependency"
    description: Optional[str] = None


# --- Update request models ---


class UpdateRotationEventRequest(BaseModel):
    """Request body for updating a rotation event."""

    rotation_status: Optional[str] = None
    continuation_execution_id: Optional[str] = None


class UpdateProductDecisionRequest(BaseModel):
    """Request body for updating a product decision."""

    title: Optional[str] = None
    description: Optional[str] = None
    rationale: Optional[str] = None
    tags_json: Optional[str] = None
    status: Optional[str] = None
    decided_by: Optional[str] = None
    context_json: Optional[str] = None


class UpdateProductMilestoneRequest(BaseModel):
    """Request body for updating a product milestone."""

    version: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    target_date: Optional[str] = None
    sort_order: Optional[int] = None
    progress_pct: Optional[int] = None
    completed_date: Optional[str] = None
