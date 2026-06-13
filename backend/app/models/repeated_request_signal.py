"""Pydantic v2 model for a repeated-request signal row (Phase 22, REQ-22).

A read model over the ``repeated_request_signals`` table. Nothing here decays:
``occurrence_count`` and ``verified_success_count`` only ever grow, and
``first_seen_at`` is fixed at the first sighting.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RepeatedRequestSignal(BaseModel):
    request_hash: str
    project_id: str | None = None
    session_kind: str
    representative_text: str
    embedding: list[float] | None = None
    occurrence_count: int = 1
    verified_success_count: int = 0
    example_session_ids: list[str] = Field(default_factory=list)
    skill_created: bool = False
    first_seen_at: str
    last_seen_at: str
