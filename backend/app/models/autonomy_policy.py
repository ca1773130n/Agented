"""Phase D autonomy policy + decision models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AutonomyPolicy(BaseModel):
    enabled: bool = False  # review-mode is the default
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    max_ops_per_round: int = Field(default=5, ge=1)
    allowed_kinds: list[str] = Field(default_factory=lambda: ["rule", "memory"])
    block_deletes: bool = True
    cooldown_seconds: int = Field(default=3600, ge=0)
    rate_limit_per_day: int = Field(default=10, ge=0)


class GateResult(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class AutonomyDecision(BaseModel):
    eligible: bool
    gates: list[GateResult] = Field(default_factory=list)
    reason: str = ""
