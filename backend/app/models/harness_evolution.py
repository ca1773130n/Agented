"""Pydantic models for the evolution-round eval gate (Phase C1)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    name: str
    passed: bool
    detail: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ReplaySample(BaseModel):
    incident_kind: str
    layer: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    trajectory_excerpt: str = ""


class EvalVerdict(BaseModel):
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    per_check: list[CheckResult] = Field(default_factory=list)
    notes: str = ""
