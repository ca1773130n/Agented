"""Pydantic models for agent memory API."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MemoryRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class MemoryMessageType(str, Enum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


class MemoryResourceType(str, Enum):
    AGENT = "agent"
    BOT = "bot"
    USER = "user"


class MemoryEntityType(str, Enum):
    AGENT = "agent"
    THREAD = "thread"


class SearchMode(str, Enum):
    HYBRID = "hybrid"
    FTS = "fts"
    VECTOR = "vector"


# --- Path models ---


class AgentMemoryPath(BaseModel):
    agent_id: str = Field(..., description="Agent ID")


class ThreadPath(BaseModel):
    agent_id: str = Field(..., description="Agent ID")
    thread_id: str = Field(..., description="Memory thread ID")


# --- Request bodies ---


class CreateThreadBody(BaseModel):
    title: Optional[str] = Field(None, description="Thread title")
    metadata: Optional[dict] = Field(None, description="Arbitrary metadata")


class MemoryMessageInput(BaseModel):
    role: MemoryRole = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    type: MemoryMessageType = Field(MemoryMessageType.TEXT, description="Message type")
    metadata: Optional[dict] = Field(None, description="Optional metadata")


class SaveMessagesBody(BaseModel):
    messages: list[MemoryMessageInput] = Field(
        ...,
        description="List of messages to save",
        min_length=1,
    )


class UpdateWorkingMemoryBody(BaseModel):
    content: str = Field(..., description="Working memory content (Markdown or JSON)")
    template: Optional[str] = Field(None, description="Optional template definition")


class UpdateMemoryConfigBody(BaseModel):
    enabled: Optional[bool] = None
    last_messages: Optional[int] = Field(None, ge=1, le=100)
    semantic_recall: Optional[dict] = None
    working_memory: Optional[dict] = None
    vector_search: Optional[dict] = None
    knowledge_graph: Optional[dict] = None
    crag_evaluation: Optional[dict] = None
    cross_thread: Optional[dict] = None


class RecallQuery(BaseModel):
    q: str = Field(..., description="Search query")
    thread_id: Optional[str] = Field(None, description="Limit to specific thread")
    top_k: int = Field(5, ge=1, le=50, description="Number of results")
    message_range: int = Field(1, ge=0, le=5, description="Context messages around each match")
    search_mode: SearchMode = Field(SearchMode.HYBRID, description="Search mode")
    alpha: float = Field(0.4, ge=0.0, le=1.0, description="FTS vs vector weight for hybrid search")
    include_cross_thread: bool = Field(False, description="Search across all agent threads")
    use_crag: bool = Field(False, description="Enable CRAG self-correcting retrieval")
    graph_hops: int = Field(1, ge=1, le=3, description="KG traversal depth for augmentation")
