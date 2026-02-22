"""Pydantic models for chat state snapshots and streaming deltas.

Used by CLIProxyChatService to yield typed streaming events and by the SSE
transport to deliver structured state to the frontend.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ChatDeltaType(str, Enum):
    """Types of streaming delta events."""

    CONTENT_DELTA = "content_delta"
    TOOL_CALL = "tool_call"
    FINISH = "finish"
    ERROR = "error"


class ChatDelta(BaseModel):
    """A single streaming delta event from an LLM completion.

    Yielded by CLIProxyChatService.stream_chat() as the response streams in.
    """

    type: ChatDeltaType
    text: Optional[str] = None
    tool_call_id: Optional[str] = None
    function_name: Optional[str] = None
    arguments_json: Optional[str] = None
    finish_reason: Optional[str] = None
    error_message: Optional[str] = None


class ChatMessage(BaseModel):
    """A single message in a chat conversation."""

    role: str
    content: str
    timestamp: str
    tool_calls: Optional[List[dict]] = None


class ChatStateSnapshot(BaseModel):
    """A point-in-time snapshot of a chat session's state.

    Delivered over SSE for frontend synchronization. The seq field is a
    monotonically increasing sequence number for cursor-based delta delivery.
    """

    seq: int = Field(..., description="Monotonic sequence number")
    messages: List[dict] = Field(default_factory=list)
    streaming_delta: str = ""
    process_groups: List[dict] = Field(default_factory=list)
    status: str = "idle"
    timestamp: str = ""


# =============================================================================
# All / Compound mode models
# =============================================================================


class AllModeRequest(BaseModel):
    """Request for All mode: fan out to multiple backends."""

    backends: List[str] = Field(..., min_length=1, description="List of backend names to send to")
    timeout: int = Field(30, ge=5, le=120, description="Per-backend timeout in seconds")


class AllModeResponse(BaseModel):
    """Response from All mode fan-out."""

    execution_map: Dict[str, str] = Field(
        default_factory=dict, description="Map of backend -> status"
    )
    session_id: str


class CompoundModeRequest(BaseModel):
    """Request for Compound mode: fan out + synthesize."""

    backends: List[str] = Field(..., min_length=1)
    timeout: int = Field(30, ge=5, le=120)
    synthesis_max_tokens: int = Field(1000, ge=100, le=4000)


class CompoundResponse(BaseModel):
    """Response from Compound mode."""

    execution_map: Dict[str, str] = Field(default_factory=dict)
    session_id: str
    synthesis_pending: bool = True
