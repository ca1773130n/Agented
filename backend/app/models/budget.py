"""Budget and token usage Pydantic models."""

from typing import Literal, Optional

from pydantic import BaseModel, model_validator


class BudgetLimitRequest(BaseModel):
    """Request model for setting/updating a budget limit."""

    entity_type: Literal["agent", "team"]
    entity_id: str
    period: Literal["daily", "weekly", "monthly"] = "monthly"
    soft_limit_usd: Optional[float] = None
    hard_limit_usd: Optional[float] = None

    @model_validator(mode="after")
    def validate_limits(self):
        if self.soft_limit_usd is None and self.hard_limit_usd is None:
            raise ValueError("At least one of soft_limit_usd or hard_limit_usd must be set")
        if (
            self.soft_limit_usd is not None
            and self.hard_limit_usd is not None
            and self.hard_limit_usd < self.soft_limit_usd
        ):
            raise ValueError("hard_limit_usd must be >= soft_limit_usd")
        return self


class BudgetLimitResponse(BaseModel):
    """Response model for a budget limit."""

    id: int
    entity_type: str
    entity_id: str
    period: str
    soft_limit_usd: Optional[float] = None
    hard_limit_usd: Optional[float] = None
    current_spend_usd: float = 0.0
    created_at: str
    updated_at: str


class TokenUsageResponse(BaseModel):
    """Response model for a token usage record."""

    execution_id: str
    entity_type: str
    entity_id: str
    backend_type: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    total_cost_usd: float = 0.0
    num_turns: int = 0
    recorded_at: str


class CostEstimateRequest(BaseModel):
    """Request model for cost estimation."""

    prompt: str
    model: Optional[str] = "claude-sonnet-4"
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None


class CostEstimateResponse(BaseModel):
    """Response model for cost estimation."""

    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: float
    model: str
    confidence: str


class BudgetCheckResponse(BaseModel):
    """Response model for budget check."""

    allowed: bool
    reason: str
    remaining_usd: Optional[float] = None
    current_spend: Optional[float] = None
