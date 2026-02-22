"""Agent-related Pydantic models."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class AgentCreationStatus(str, Enum):
    """Agent creation status values."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class EffortLevel(str, Enum):
    """Agent effort level values."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"


class ConversationStatus(str, Enum):
    """Agent conversation status values."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class AgentDocument(BaseModel):
    """A document attached to an agent."""

    name: str
    path: Optional[str] = None
    type: str = "file"  # file, url, inline
    content: Optional[str] = None


class Agent(BaseModel):
    """Agent entity - autonomous AI agent with richer context."""

    id: str = Field(..., pattern=r"^agent-[a-z0-9-]+$", examples=["agent-abc123"])
    name: str = Field(..., examples=["Code Review Agent"])
    description: Optional[str] = None
    role: Optional[str] = Field(None, examples=["You are a senior code reviewer..."])
    goals: Optional[str] = None  # JSON array of goals
    context: Optional[str] = None
    backend_type: str = Field(default="claude")
    enabled: int = Field(default=1)
    skills: Optional[str] = None  # JSON array of skill names
    documents: Optional[str] = None  # JSON array of document refs
    system_prompt: Optional[str] = None
    preferred_model: Optional[str] = None  # e.g., "opus", "sonnet", "haiku"
    effort_level: EffortLevel = EffortLevel.MEDIUM
    creation_conversation_id: Optional[str] = None
    creation_status: AgentCreationStatus = AgentCreationStatus.COMPLETED
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AgentListResponse(BaseModel):
    """Response for listing all agents."""

    agents: List[Agent]


class CreateAgentRequest(BaseModel):
    """Request body for creating an agent."""

    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    role: Optional[str] = None
    goals: Optional[str] = None  # JSON array
    context: Optional[str] = None
    backend_type: str = Field(default="claude")
    skills: Optional[str] = None  # JSON array
    documents: Optional[str] = None  # JSON array
    system_prompt: Optional[str] = None
    preferred_model: Optional[str] = None
    effort_level: Optional[EffortLevel] = EffortLevel.MEDIUM
    creation_conversation_id: Optional[str] = None


class CreateAgentResponse(BaseModel):
    """Response after creating an agent."""

    message: str
    agent_id: str
    name: str


class UpdateAgentRequest(BaseModel):
    """Request body for updating an agent."""

    name: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
    goals: Optional[str] = None
    context: Optional[str] = None
    backend_type: Optional[str] = None
    enabled: Optional[int] = Field(None, ge=0, le=1)
    skills: Optional[str] = None
    documents: Optional[str] = None
    system_prompt: Optional[str] = None
    preferred_model: Optional[str] = None
    effort_level: Optional[EffortLevel] = None


class RunAgentRequest(BaseModel):
    """Request body for running an agent."""

    message: str = ""


class RunAgentResponse(BaseModel):
    """Response after triggering agent execution."""

    message: str
    agent_id: str
    execution_id: str
    status: str = "running"


# Agent conversation models


class ConversationMessage(BaseModel):
    """A message in an agent creation conversation."""

    role: str  # user, assistant, system
    content: str
    timestamp: str


class AgentConversation(BaseModel):
    """Agent creation conversation."""

    id: str = Field(..., pattern=r"^conv-[a-z0-9-]+$")
    agent_id: Optional[str] = None
    status: ConversationStatus = ConversationStatus.ACTIVE
    messages: Optional[str] = None  # JSON array of ConversationMessage
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class StartConversationResponse(BaseModel):
    """Response after starting a new conversation."""

    conversation_id: str
    message: str


class SendMessageRequest(BaseModel):
    """Request to send a message to a conversation."""

    message: str = Field(..., min_length=1)


class SendMessageResponse(BaseModel):
    """Response after sending a message."""

    message_id: str
    status: str = "processing"


class FinalizeAgentResponse(BaseModel):
    """Response after finalizing agent creation from a conversation."""

    message: str
    agent_id: str
    agent: Agent
