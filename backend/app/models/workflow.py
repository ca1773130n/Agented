"""Workflow-related Pydantic models."""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    """Workflow status values."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class WorkflowNodeType(str, Enum):
    """Workflow node type values."""

    TRIGGER = "trigger"
    SKILL = "skill"
    COMMAND = "command"
    AGENT = "agent"
    SCRIPT = "script"
    CONDITIONAL = "conditional"
    TRANSFORM = "transform"


class NodeErrorMode(str, Enum):
    """Error handling mode for workflow nodes."""

    STOP = "stop"
    CONTINUE = "continue"
    CONTINUE_WITH_ERROR = "continue_with_error"


class WorkflowExecutionStatus(str, Enum):
    """Workflow execution status values."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeExecutionStatus(str, Enum):
    """Workflow node execution status values."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Workflow(BaseModel):
    """Workflow entity - orchestrates multi-step automation pipelines."""

    id: str = Field(..., pattern=r"^wf-[a-z0-9]+$", examples=["wf-abc123"])
    name: str = Field(..., examples=["Deploy Pipeline"])
    description: Optional[str] = None
    trigger_type: str = Field(default="manual")
    trigger_config: Optional[str] = None
    enabled: int = Field(default=1)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WorkflowVersion(BaseModel):
    """A version of a workflow graph."""

    id: int
    workflow_id: str
    version: int
    graph_json: str
    created_at: Optional[str] = None


class WorkflowExecution(BaseModel):
    """A single execution of a workflow."""

    id: str = Field(..., pattern=r"^wfx-[a-z0-9]+$", examples=["wfx-abc12345"])
    workflow_id: str
    version: int
    status: WorkflowExecutionStatus = WorkflowExecutionStatus.PENDING
    input_json: Optional[str] = None
    output_json: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


class WorkflowNodeExecution(BaseModel):
    """Execution record for a single node within a workflow execution."""

    id: int
    execution_id: str
    node_id: str
    node_type: WorkflowNodeType
    status: NodeExecutionStatus = NodeExecutionStatus.PENDING
    input_json: Optional[str] = None
    output_json: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


# --- Graph / Node / Edge models ---


class WorkflowMessage(BaseModel):
    """Inter-node I/O message for workflow data routing."""

    content_type: str = Field(default="text")
    text: Optional[str] = None
    data: Optional[dict] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None


class WorkflowNode(BaseModel):
    """A node in a workflow graph."""

    id: str
    type: WorkflowNodeType
    label: str
    config: dict = Field(default_factory=dict)
    error_mode: NodeErrorMode = NodeErrorMode.STOP
    retry_max: int = Field(default=0, ge=0)
    retry_backoff_seconds: int = Field(default=1, ge=0)


class WorkflowEdge(BaseModel):
    """An edge in a workflow graph."""

    source: str
    target: str


class WorkflowGraph(BaseModel):
    """A workflow graph with nodes, edges, and optional settings."""

    nodes: List[WorkflowNode]
    edges: List[WorkflowEdge] = Field(default_factory=list)
    settings: Optional[dict] = None


class RunWorkflowResponse(BaseModel):
    """Response after starting a workflow execution."""

    message: str
    execution_id: str


class WorkflowExecutionDetailResponse(BaseModel):
    """Detailed response for a single workflow execution including node executions."""

    execution: WorkflowExecution
    node_executions: List[WorkflowNodeExecution]


# --- List responses ---


class WorkflowListResponse(BaseModel):
    """Response for listing all workflows."""

    workflows: List[Workflow]


class WorkflowVersionListResponse(BaseModel):
    """Response for listing workflow versions."""

    versions: List[WorkflowVersion]


class WorkflowExecutionListResponse(BaseModel):
    """Response for listing workflow executions."""

    executions: List[WorkflowExecution]


class WorkflowNodeExecutionListResponse(BaseModel):
    """Response for listing workflow node executions."""

    node_executions: List[WorkflowNodeExecution]


# --- Create requests ---


class CreateWorkflowRequest(BaseModel):
    """Request body for creating a workflow."""

    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    trigger_type: str = Field(default="manual")
    trigger_config: Optional[str] = None


class CreateWorkflowResponse(BaseModel):
    """Response after creating a workflow."""

    message: str
    workflow_id: str


class CreateWorkflowVersionRequest(BaseModel):
    """Request body for creating a workflow version."""

    graph_json: str = Field(..., min_length=1)


class RunWorkflowRequest(BaseModel):
    """Request body for running a workflow."""

    input_json: Optional[str] = None


# --- Update requests ---


class UpdateWorkflowRequest(BaseModel):
    """Request body for updating a workflow."""

    name: Optional[str] = None
    description: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[str] = None
    enabled: Optional[int] = Field(None, ge=0, le=1)
