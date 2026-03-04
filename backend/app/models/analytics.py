"""Analytics Pydantic v2 models for request/response validation."""

from typing import List, Literal, Optional

from pydantic import BaseModel


class AnalyticsQuery(BaseModel):
    """Query parameters for analytics endpoints."""

    group_by: Literal["day", "week", "month"] = "day"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    entity_type: Optional[str] = None
    trigger_id: Optional[str] = None
    team_id: Optional[str] = None


class CostDataPoint(BaseModel):
    """Single cost analytics data point."""

    entity_type: str
    entity_id: str
    period: str
    total_cost_usd: float
    total_tokens: int
    input_tokens: int = 0
    output_tokens: int = 0


class CostAnalyticsResponse(BaseModel):
    """Response for cost analytics endpoint."""

    data: List[dict]
    period_count: int
    total_cost: float


class ExecutionDataPoint(BaseModel):
    """Single execution analytics data point."""

    period: str
    backend_type: str
    total_executions: int
    success_count: int
    failed_count: int
    cancelled_count: int
    avg_duration_ms: Optional[float] = None


class ExecutionAnalyticsResponse(BaseModel):
    """Response for execution analytics endpoint."""

    data: List[dict]
    period_count: int
    total_executions: int


class EffectivenessResponse(BaseModel):
    """Response for effectiveness analytics endpoint."""

    total_reviews: int
    accepted: int
    ignored: int
    pending: int
    acceptance_rate: float
    over_time: List[dict]
