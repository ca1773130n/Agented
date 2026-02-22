"""PR review-related Pydantic models."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class PRStatus(str, Enum):
    """Pull request status values."""

    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


class ReviewStatus(str, Enum):
    """Code review status values."""

    PENDING = "pending"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    FIXED = "fixed"


class PrReview(BaseModel):
    """A PR review record."""

    id: int
    trigger_id: str = "bot-pr-review"
    project_name: str
    github_repo_url: Optional[str] = None
    pr_number: int
    pr_url: str
    pr_title: str
    pr_author: Optional[str] = None
    pr_status: PRStatus = PRStatus.OPEN
    review_status: ReviewStatus = ReviewStatus.PENDING
    review_comment: Optional[str] = None
    fixes_applied: int = 0
    fix_comment: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PrReviewListResponse(BaseModel):
    """Response for listing PR reviews."""

    reviews: List[PrReview]
    total: int = 0


class PrReviewStatsResponse(BaseModel):
    """Aggregate PR review statistics."""

    total_prs: int = 0
    open_prs: int = 0
    merged_prs: int = 0
    closed_prs: int = 0
    pending_reviews: int = 0
    approved_reviews: int = 0
    changes_requested: int = 0
    fixed_reviews: int = 0


class CreatePrReviewRequest(BaseModel):
    """Request body for creating a PR review."""

    project_name: str = Field(..., min_length=1)
    github_repo_url: Optional[str] = None
    pr_number: int
    pr_url: str = Field(..., min_length=1)
    pr_title: str = Field(..., min_length=1)
    pr_author: Optional[str] = None


class UpdatePrReviewRequest(BaseModel):
    """Request body for updating a PR review."""

    pr_status: Optional[PRStatus] = None
    review_status: Optional[ReviewStatus] = None
    review_comment: Optional[str] = None
    fixes_applied: Optional[int] = None
    fix_comment: Optional[str] = None
