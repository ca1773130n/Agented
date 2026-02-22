"""Trigger-related Pydantic models (renamed from Bot)."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class BackendType(str, Enum):
    """Valid CLI backend types."""

    CLAUDE = "claude"
    OPENCODE = "opencode"


# Available models per backend
CLAUDE_MODELS = ["opus", "sonnet", "haiku"]
OPENCODE_MODELS = ["codex", "zen"]  # Add more as needed


class PathType(str, Enum):
    """Project path source types."""

    LOCAL = "local"
    GITHUB = "github"


class TriggerSource(str, Enum):
    """Trigger source types."""

    WEBHOOK = "webhook"
    GITHUB = "github"
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class ScheduleType(str, Enum):
    """Schedule frequency types for scheduled triggers."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ExecutionMode(str, Enum):
    """Trigger execution mode."""

    DIRECT = "direct"
    TEAM = "team"


class ExecutionStatusEnum(str, Enum):
    """Trigger execution status values."""

    IDLE = "idle"
    RUNNING = "running"
    RESOLVING = "resolving"
    SUCCESS = "success"
    FAILED = "failed"


class ExecutionStatus(BaseModel):
    """Trigger execution status for dashboard display."""

    status: ExecutionStatusEnum = Field(default=ExecutionStatusEnum.IDLE)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    pr_url: Optional[str] = None


class ProjectPath(BaseModel):
    """A project path linked to a trigger."""

    id: int
    local_project_path: str
    symlink_name: Optional[str] = None
    path_type: PathType = PathType.LOCAL
    github_repo_url: Optional[str] = None
    created_at: Optional[str] = None


class Trigger(BaseModel):
    """Trigger entity (renamed from Bot)."""

    id: str = Field(..., pattern=r"^(bot|trig)-[a-z0-9-]+$", examples=["trig-abc123"])
    name: str = Field(..., examples=["Weekly Security Audit"])
    prompt_template: str = Field(..., examples=["/weekly-security-audit {paths}"])
    backend_type: str = Field(default="claude")
    trigger_source: TriggerSource = Field(default=TriggerSource.WEBHOOK)

    # Webhook matching configuration
    match_field_path: Optional[str] = Field(
        None, examples=["event.type", "action"], description="JSON path to check in webhook payload"
    )
    match_field_value: Optional[str] = Field(
        None, examples=["security_alert", "build_complete"], description="Value that must match"
    )
    text_field_path: Optional[str] = Field(
        default="text",
        examples=["event.text", "message.content"],
        description="JSON path for text extraction",
    )
    detection_keyword: str = Field(default="", examples=["주간 보안 취약점 알림"])

    # Deprecated field for backward compatibility
    group_id: int = Field(
        default=0, deprecated=True, description="Deprecated: use match_field_path/match_field_value"
    )

    is_predefined: int = Field(default=0)
    enabled: int = Field(default=1)
    auto_resolve: int = Field(default=0)
    schedule_type: Optional[ScheduleType] = None
    schedule_time: Optional[str] = None  # HH:MM format
    schedule_day: Optional[int] = None  # 0-6 for weekly, 1-31 for monthly
    schedule_timezone: str = Field(default="Asia/Seoul")
    next_run_at: Optional[str] = None
    last_run_at: Optional[str] = None
    skill_command: Optional[str] = None
    model: Optional[str] = None
    execution_mode: str = Field(default="direct")
    team_id: Optional[str] = None
    created_at: Optional[str] = None
    path_count: Optional[int] = None
    execution_status: Optional[ExecutionStatus] = None


class TriggerListResponse(BaseModel):
    """Response for listing all triggers."""

    triggers: List[Trigger]


class TriggerDetailResponse(Trigger):
    """Trigger details including paths."""

    paths: List[ProjectPath] = []


class CreateTriggerRequest(BaseModel):
    """Request body for creating a trigger."""

    name: str = Field(..., min_length=1)
    prompt_template: str = Field(..., min_length=1)
    backend_type: BackendType = BackendType.CLAUDE
    trigger_source: TriggerSource = TriggerSource.WEBHOOK

    # Webhook matching configuration
    match_field_path: Optional[str] = None
    match_field_value: Optional[str] = None
    text_field_path: Optional[str] = Field(default="text")
    detection_keyword: str = Field(default="")

    # Deprecated
    group_id: int = Field(default=0)

    schedule_type: Optional[ScheduleType] = None
    schedule_time: Optional[str] = None
    schedule_day: Optional[int] = None
    schedule_timezone: str = Field(default="Asia/Seoul")
    skill_command: Optional[str] = None
    model: Optional[str] = None
    execution_mode: Optional[str] = Field(default="direct")
    team_id: Optional[str] = None


class CreateTriggerResponse(BaseModel):
    """Response after creating a trigger."""

    message: str
    trigger_id: str
    name: str


class UpdateTriggerRequest(BaseModel):
    """Request body for updating a trigger."""

    name: Optional[str] = None
    prompt_template: Optional[str] = None
    backend_type: Optional[BackendType] = None
    trigger_source: Optional[TriggerSource] = None

    # Webhook matching configuration
    match_field_path: Optional[str] = None
    match_field_value: Optional[str] = None
    text_field_path: Optional[str] = None
    detection_keyword: Optional[str] = None

    # Deprecated
    group_id: Optional[int] = None

    enabled: Optional[int] = Field(None, ge=0, le=1)
    auto_resolve: Optional[int] = Field(None, ge=0, le=1)
    schedule_type: Optional[ScheduleType] = None
    schedule_time: Optional[str] = None
    schedule_day: Optional[int] = None
    schedule_timezone: Optional[str] = None
    skill_command: Optional[str] = None
    model: Optional[str] = None
    execution_mode: Optional[str] = None
    team_id: Optional[str] = None


class PathListResponse(BaseModel):
    """Response for listing trigger paths."""

    paths: List[ProjectPath]


class AddPathRequest(BaseModel):
    """Request body for adding a project path or GitHub repo."""

    local_project_path: Optional[str] = Field(None, min_length=1)
    github_repo_url: Optional[str] = Field(None, min_length=1)


class AddPathResponse(BaseModel):
    """Response after adding a path."""

    message: str
    local_project_path: Optional[str] = None
    github_repo_url: Optional[str] = None
    path_type: PathType = PathType.LOCAL


class RemovePathRequest(BaseModel):
    """Request body for removing a project path."""

    local_project_path: Optional[str] = Field(None, min_length=1)
    github_repo_url: Optional[str] = Field(None, min_length=1)


class RunTriggerRequest(BaseModel):
    """Request body for manually running a trigger."""

    message: str = ""


class RunTriggerResponse(BaseModel):
    """Response after triggering execution."""

    message: str
    trigger_id: str
    status: str = "running"
