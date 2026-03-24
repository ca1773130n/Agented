"""Pydantic models for tracing API."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SpanType(str, Enum):
    AGENT_RUN = "AGENT_RUN"
    BOT_RUN = "BOT_RUN"
    TEAM_RUN = "TEAM_RUN"
    PROMPT_BUILD = "PROMPT_BUILD"
    EXECUTION = "EXECUTION"
    TOOL_CALL = "TOOL_CALL"
    MEMORY_RECALL = "MEMORY_RECALL"
    MEMORY_SAVE = "MEMORY_SAVE"
    BUDGET_CHECK = "BUDGET_CHECK"
    RETRY = "RETRY"
    GENERIC = "GENERIC"


class TraceStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class EntityType(str, Enum):
    AGENT = "agent"
    BOT = "bot"
    TRIGGER = "trigger"
    TEAM = "team"


# --- Path models ---


class TracePath(BaseModel):
    trace_id: str = Field(..., description="Trace ID")


class SpanPath(BaseModel):
    trace_id: str = Field(..., description="Trace ID")
    span_id: str = Field(..., description="Span ID")


# --- Query models ---


class TraceListQuery(BaseModel):
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    status: Optional[str] = None
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class TraceStatsQuery(BaseModel):
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None


# --- Request bodies ---


class CreateTraceBody(BaseModel):
    name: str = Field(..., description="Trace name")
    entity_type: str = Field(..., description="Entity type (agent, bot, trigger, team)")
    entity_id: str = Field(..., description="Entity ID")
    execution_id: Optional[str] = None
    input: Optional[dict] = None
    metadata: Optional[dict] = None


class EndTraceBody(BaseModel):
    status: str = Field("completed", description="Final status")
    output: Optional[dict] = None
    error_message: Optional[str] = None


class CreateSpanBody(BaseModel):
    name: str = Field(..., description="Span name")
    span_type: str = Field(..., description="Span type")
    parent_span_id: Optional[str] = None
    input: Optional[dict] = None
    attributes: Optional[dict] = None
    metadata: Optional[dict] = None


class EndSpanBody(BaseModel):
    status: str = Field("completed", description="Final status")
    output: Optional[dict] = None
    error_message: Optional[str] = None
    attributes: Optional[dict] = None
