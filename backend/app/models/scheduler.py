"""Pydantic v2 models for agent execution scheduler status and session responses."""

from typing import List, Optional

from pydantic import BaseModel


class SchedulerSessionResponse(BaseModel):
    """Single scheduler session state for an account."""

    account_id: int
    state: str  # "queued", "running", "stopped"
    stop_reason: Optional[str] = None
    stop_window_type: Optional[str] = None
    stop_eta_minutes: Optional[float] = None
    resume_estimate: Optional[str] = None
    consecutive_safe_polls: int = 0
    updated_at: Optional[str] = None


class SchedulerGlobalSummary(BaseModel):
    """Aggregate counts of session states."""

    total: int
    queued: int
    running: int
    stopped: int


class SchedulerStatusResponse(BaseModel):
    """Full scheduler status response."""

    enabled: bool
    safety_margin_minutes: int = 5
    resume_hysteresis_polls: int = 2
    sessions: List[SchedulerSessionResponse] = []
    global_summary: SchedulerGlobalSummary


class EligibilityResponse(BaseModel):
    """Eligibility check result for an account."""

    eligible: bool
    reason: str
    message: Optional[str] = None
    resume_estimate: Optional[str] = None
