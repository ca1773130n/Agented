"""Pydantic v2 models for execution replay and diff comparison."""

from typing import Optional

from pydantic import BaseModel, Field


class ReplayRequest(BaseModel):
    """Request body for replaying an execution."""

    execution_id: str = Field(..., description="ID of the execution to replay")
    notes: Optional[str] = Field(None, description="Optional notes about this replay")


class ReplayResponse(BaseModel):
    """Response after creating a replay."""

    comparison_id: str = Field(..., description="ID of the replay comparison record")
    original_execution_id: str = Field(..., description="Original execution ID")
    replay_execution_id: str = Field(..., description="New replay execution ID")


class DiffLine(BaseModel):
    """A single line in a diff output."""

    line_number: int = Field(..., description="Line number in the diff output")
    type: str = Field(..., description="Line type: 'unchanged', 'added', or 'removed'")
    content: str = Field(..., description="Line content")


class OutputDiff(BaseModel):
    """Structured diff between two execution outputs."""

    original_execution_id: str = Field(..., description="First execution ID")
    replay_execution_id: str = Field(..., description="Second execution ID")
    diff_lines: list[DiffLine] = Field(default_factory=list, description="Line-level diff output")
    original_line_count: int = Field(0, description="Total lines in original output")
    replay_line_count: int = Field(0, description="Total lines in replay output")
    change_summary: dict = Field(
        default_factory=dict,
        description="Summary: {added: int, removed: int, unchanged: int}",
    )


class DiffContextPreviewRequest(BaseModel):
    """Request body for previewing diff-aware context extraction."""

    diff_text: str = Field(..., description="Unified diff text to extract context from")
    context_lines: Optional[int] = Field(
        None, description="Number of context lines around changes (default 10)"
    )
