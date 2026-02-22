"""Pydantic models for rate limit monitoring config and status responses."""

from typing import Optional

from pydantic import BaseModel, field_validator


class MonitoringAccountConfig(BaseModel):
    """Per-account monitoring toggle."""

    enabled: bool = False


class MonitoringConfig(BaseModel):
    """Monitoring configuration stored in the settings table."""

    enabled: bool = False
    polling_minutes: int = 5
    accounts: dict[str, MonitoringAccountConfig] = {}

    @field_validator("polling_minutes")
    @classmethod
    def validate_polling_minutes(cls, v: int) -> int:
        allowed = {1, 5, 15, 30, 60}
        if v not in allowed:
            raise ValueError(f"polling_minutes must be one of {sorted(allowed)}")
        return v


class MonitoringConfigRequest(BaseModel):
    """Request body for POST /admin/monitoring/config."""

    enabled: bool = False
    polling_minutes: int = 5
    accounts: dict[str, MonitoringAccountConfig] = {}

    @field_validator("polling_minutes")
    @classmethod
    def validate_polling_minutes(cls, v: int) -> int:
        allowed = {1, 5, 15, 30, 60}
        if v not in allowed:
            raise ValueError(f"polling_minutes must be one of {sorted(allowed)}")
        return v


class ConsumptionRates(BaseModel):
    """Moving average consumption rates (tokens/hour) over different windows."""

    ten_min: Optional[float] = None
    thirty_min: Optional[float] = None
    sixty_min: Optional[float] = None
    one_eighty_min: Optional[float] = None


class EtaProjection(BaseModel):
    """Rate limit ETA projection result."""

    status: str  # "safe", "projected", "at_limit", "no_data"
    message: str
    eta: Optional[str] = None  # ISO datetime string
    minutes_remaining: Optional[float] = None
    resets_at: Optional[str] = None


class WindowSnapshot(BaseModel):
    """A single rate limit window snapshot with consumption rates and ETA."""

    account_id: int
    account_name: str = ""
    backend_type: str
    window_type: str
    tokens_used: int
    tokens_limit: int
    percentage: float
    threshold_level: str
    resets_at: Optional[str] = None
    recorded_at: str
    consumption_rates: ConsumptionRates
    eta: EtaProjection


class MonitoringStatusResponse(BaseModel):
    """Response for GET /admin/monitoring/status."""

    enabled: bool
    polling_minutes: int
    windows: list[WindowSnapshot]
    threshold_alerts: list[dict] = []


class SnapshotHistoryEntry(BaseModel):
    """A single entry in a snapshot history response."""

    tokens_used: int
    percentage: float
    recorded_at: str


class SnapshotHistoryResponse(BaseModel):
    """Response for GET /admin/monitoring/history."""

    account_id: int
    window_type: str
    history: list[SnapshotHistoryEntry]
