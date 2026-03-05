"""Pydantic v2 models for analytics request/response validation."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class AnalyticsQuery(BaseModel):
    """Query parameters for analytics endpoints."""

    group_by: Literal["day", "week", "month"] = Field(
        default="day", description="Time period grouping"
    )
    start_date: Optional[str] = Field(default=None, description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(default=None, description="End date (YYYY-MM-DD)")
    entity_type: Optional[str] = Field(
        default=None, description="Entity type filter (trigger/team/project)"
    )
    trigger_id: Optional[str] = Field(default=None, description="Filter by trigger ID")
    team_id: Optional[str] = Field(default=None, description="Filter by team ID")


class CostAnalyticsResponse(BaseModel):
    """Response model for cost analytics."""

    data: List[dict] = Field(default_factory=list, description="Cost data grouped by period")
    period_count: int = Field(default=0, description="Number of distinct periods")
    total_cost: float = Field(default=0.0, description="Total cost across all periods")


class ExecutionAnalyticsResponse(BaseModel):
    """Response model for execution analytics."""

    data: List[dict] = Field(default_factory=list, description="Execution data grouped by period")
    period_count: int = Field(default=0, description="Number of distinct periods")
    total_executions: int = Field(default=0, description="Total executions across all periods")


class EffectivenessResponse(BaseModel):
    """Response model for effectiveness analytics."""

    total_reviews: int = Field(default=0, description="Total PR reviews")
    accepted: int = Field(default=0, description="Accepted reviews (approved + fixed)")
    ignored: int = Field(
        default=0, description="Ignored reviews (changes_requested, fixes_applied=0)"
    )
    pending: int = Field(default=0, description="Pending reviews")
    acceptance_rate: float = Field(default=0.0, description="Acceptance rate percentage")
    over_time: List[dict] = Field(
        default_factory=list, description="Effectiveness over time periods"
    )
