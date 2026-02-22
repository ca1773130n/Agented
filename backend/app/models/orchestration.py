"""Pydantic models for orchestration API requests and responses."""

from typing import List, Optional

from pydantic import BaseModel


class FallbackChainEntry(BaseModel):
    """A single entry in a fallback chain."""

    backend_type: str
    account_id: Optional[int] = None


class SetFallbackChainRequest(BaseModel):
    """Request body for setting a trigger's fallback chain."""

    entries: List[FallbackChainEntry]


class FallbackChainResponse(BaseModel):
    """Response for a fallback chain query."""

    entity_type: str
    entity_id: str
    entries: list


class AccountHealthResponse(BaseModel):
    """Health status for a single account."""

    account_id: int
    account_name: str
    backend_type: str
    is_rate_limited: bool
    rate_limited_until: Optional[str] = None
    cooldown_remaining_seconds: Optional[int] = None
    total_executions: int = 0
    last_used_at: Optional[str] = None
    is_default: bool = False
