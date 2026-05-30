"""Pydantic models for the evolution-round eval gate (Phase C1)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    name: str = Field(min_length=1)
    passed: bool
    detail: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ReplaySample(BaseModel):
    incident_kind: str = Field(min_length=1)
    layer: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    trajectory_excerpt: str = ""


class EvalVerdict(BaseModel):
    passed: bool
    # Required: a verdict must carry an aggregate score (eval service always computes it).
    score: float = Field(ge=0.0, le=1.0)
    per_check: list[CheckResult] = Field(default_factory=list)
    notes: str = ""
