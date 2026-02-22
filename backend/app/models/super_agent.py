"""SuperAgent-related Pydantic models."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class SuperAgentStatus(str, Enum):
    """SuperAgent status values."""

    ACTIVE = "active"
    IDLE = "idle"
    TERMINATED = "terminated"


class SessionStatus(str, Enum):
    """SuperAgent session status values."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    TERMINATED = "terminated"


class DocumentType(str, Enum):
    """SuperAgent document type values."""

    SOUL = "SOUL"
    IDENTITY = "IDENTITY"
    MEMORY = "MEMORY"
    ROLE = "ROLE"


class MessageType(str, Enum):
    """Agent message type values."""

    MESSAGE = "message"
    BROADCAST = "broadcast"
    REQUEST = "request"
    RESPONSE = "response"
    ARTIFACT = "artifact"
    SHUTDOWN = "shutdown"


class MessagePriority(str, Enum):
    """Agent message priority values."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class MessageStatus(str, Enum):
    """Agent message status values."""

    PENDING = "pending"
    DELIVERED = "delivered"
    READ = "read"
    EXPIRED = "expired"


class SuperAgent(BaseModel):
    """SuperAgent entity - autonomous agent with sessions and messaging."""

    id: str = Field(..., pattern=r"^super-[a-z0-9]+$", examples=["super-abc123"])
    name: str = Field(..., examples=["DevOps Lead"])
    description: Optional[str] = None
    backend_type: str = Field(default="claude")
    preferred_model: Optional[str] = None
    team_id: Optional[str] = None
    parent_super_agent_id: Optional[str] = None
    max_concurrent_sessions: int = Field(default=10)
    enabled: int = Field(default=1)
    config_json: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SuperAgentDocument(BaseModel):
    """A document attached to a super agent."""

    id: int
    super_agent_id: str
    doc_type: DocumentType
    title: str
    content: str = ""
    version: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SuperAgentSession(BaseModel):
    """A session for a super agent."""

    id: str = Field(..., pattern=r"^sess-[a-z0-9]+$", examples=["sess-abc12345"])
    super_agent_id: str
    status: SessionStatus = SessionStatus.ACTIVE
    conversation_log: Optional[str] = None
    summary: Optional[str] = None
    token_count: int = 0
    last_compacted_at: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


class AgentMessage(BaseModel):
    """A message between agents."""

    id: str = Field(..., pattern=r"^msg-[a-z0-9]+$", examples=["msg-abc12345"])
    from_agent_id: str
    to_agent_id: Optional[str] = None
    message_type: MessageType = MessageType.MESSAGE
    priority: MessagePriority = MessagePriority.NORMAL
    subject: Optional[str] = None
    content: str = ""
    status: MessageStatus = MessageStatus.PENDING
    ttl_seconds: Optional[int] = None
    expires_at: Optional[str] = None
    created_at: Optional[str] = None
    delivered_at: Optional[str] = None
    read_at: Optional[str] = None


# --- List responses ---


class SuperAgentListResponse(BaseModel):
    """Response for listing all super agents."""

    super_agents: List[SuperAgent]


class SuperAgentDocumentListResponse(BaseModel):
    """Response for listing super agent documents."""

    documents: List[SuperAgentDocument]


class SuperAgentSessionListResponse(BaseModel):
    """Response for listing super agent sessions."""

    sessions: List[SuperAgentSession]


class AgentMessageListResponse(BaseModel):
    """Response for listing agent messages."""

    messages: List[AgentMessage]


# --- Create requests ---


class CreateSuperAgentRequest(BaseModel):
    """Request body for creating a super agent."""

    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    backend_type: str = Field(default="claude")
    preferred_model: Optional[str] = None
    team_id: Optional[str] = None
    parent_super_agent_id: Optional[str] = None
    max_concurrent_sessions: int = Field(default=10, ge=1, le=50)
    config_json: Optional[str] = None


class CreateSuperAgentResponse(BaseModel):
    """Response after creating a super agent."""

    message: str
    super_agent_id: str


class CreateDocumentRequest(BaseModel):
    """Request body for creating a super agent document."""

    doc_type: DocumentType
    title: str = Field(..., min_length=1)
    content: str = ""


class UpdateDocumentRequest(BaseModel):
    """Request body for updating a super agent document."""

    title: Optional[str] = None
    content: Optional[str] = None


class CreateSessionRequest(BaseModel):
    """Request body for creating a super agent session."""

    pass  # No required fields - session created with defaults


class SendAgentMessageRequest(BaseModel):
    """Request body for sending a message between agents."""

    to_agent_id: Optional[str] = None
    message_type: MessageType = MessageType.MESSAGE
    priority: MessagePriority = MessagePriority.NORMAL
    subject: Optional[str] = None
    content: str = Field(..., min_length=1)
    ttl_seconds: Optional[int] = Field(None, ge=1)


# --- Update requests ---


class UpdateSuperAgentRequest(BaseModel):
    """Request body for updating a super agent."""

    name: Optional[str] = None
    description: Optional[str] = None
    backend_type: Optional[str] = None
    preferred_model: Optional[str] = None
    team_id: Optional[str] = None
    parent_super_agent_id: Optional[str] = None
    max_concurrent_sessions: Optional[int] = Field(None, ge=1, le=50)
    enabled: Optional[int] = Field(None, ge=0, le=1)
    config_json: Optional[str] = None
