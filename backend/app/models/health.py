"""Pydantic models for health monitoring and team impact reports."""

from typing import List, Optional

from pydantic import BaseModel, Field


class HealthAlert(BaseModel):
    """A single health alert record."""

    id: int
    alert_type: str
    trigger_id: str
    message: str
    details: Optional[str] = None
    severity: str = "warning"
    acknowledged: int = 0
    created_at: Optional[str] = None


class HealthStatusResponse(BaseModel):
    """Health monitor status summary."""

    total_alerts: int = 0
    critical_count: int = 0
    warning_count: int = 0
    last_check_time: Optional[str] = None
    alerts: List[HealthAlert] = Field(default_factory=list)


class TopBot(BaseModel):
    """A trigger ranked by execution count."""

    trigger_id: str
    trigger_name: Optional[str] = None
    execution_count: int = 0


class BotNeedingAttention(BaseModel):
    """A trigger that needs attention due to high failure rate or active alerts."""

    trigger_id: str
    trigger_name: Optional[str] = None
    reason: str = ""
    failure_rate: Optional[float] = None
    active_alerts: int = 0


class WeeklyReport(BaseModel):
    """Weekly team impact report."""

    prs_reviewed: int = 0
    issues_found: int = 0
    estimated_time_saved_minutes: int = 0
    top_bots: List[TopBot] = Field(default_factory=list)
    bots_needing_attention: List[BotNeedingAttention] = Field(default_factory=list)
    period_start: str = ""
    period_end: str = ""
