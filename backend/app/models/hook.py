"""Hook-related Pydantic models."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

VALID_EVENTS = [
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "SubagentStop",
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "PreCompact",
    "Notification",
]

HookEventType = Literal[
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "SubagentStop",
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "PreCompact",
    "Notification",
]


class CreateHookRequest(BaseModel):
    """Request body for creating a hook."""

    name: str = Field(..., min_length=1)
    event: HookEventType = Field(..., description="Hook event type")
    description: Optional[str] = None
    content: Optional[str] = None
    enabled: bool = Field(default=True)
    project_id: Optional[str] = None
    source_path: Optional[str] = None


class UpdateHookRequest(BaseModel):
    """Request body for updating a hook."""

    name: Optional[str] = None
    event: Optional[HookEventType] = None
    description: Optional[str] = None
    content: Optional[str] = None
    enabled: Optional[bool] = None


class GenerateHookRequest(BaseModel):
    """Request body for generating a hook from a description."""

    description: str = Field(..., min_length=10)
