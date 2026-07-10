"""Pydantic models for the evolution-round eval gate (Phase C1)."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    name: str = Field(min_length=1)
    passed: bool
    detail: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    # Replay-judge only: the patch plausibly introduces a NEW failure mode. A
    # regression fails the eval CLOSED regardless of whether it also fixed the
    # sampled incident (``passed`` = prevents AND not introduces_new).
    introduces_new: bool = False


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


class ApplyJournalEntry(BaseModel):
    kind: str
    op: Literal["create", "update", "delete"]
    asset_id: str
    # before-image of the asset (for update/delete reversal); None for create.
    before: Optional[dict] = None
    # binding row info captured at apply time, if any (for rebind on delete-reverse).
    binding: Optional[dict] = None


class RevertResult(BaseModel):
    status: Literal["reverted", "conflict", "failed"]
    reversed_count: int = 0
    git_reverted: bool = False
    error: str = ""
    conflicts: list[dict] = Field(default_factory=list)


class KGSignalItem(BaseModel):
    """A Tesserae-KG-derived evolution signal (Phase E2)."""

    signal_id: str
    project_id: str
    round_id: Optional[str] = None
    question: str
    content: str
    weight: float = Field(ge=0.3, le=0.7)
    already_forged: bool = False
    first_seen_at: str
    captured_at: str
