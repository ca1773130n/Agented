"""System error logging and autofix Pydantic models."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from .common import PaginationQuery


class ErrorSource(str, Enum):
    BACKEND = "backend"
    FRONTEND = "frontend"


class ErrorCategory(str, Enum):
    CLI_ERROR = "cli_error"
    PROXY_ERROR = "proxy_error"
    STREAMING_ERROR = "streaming_error"
    RUNTIME_ERROR = "runtime_error"
    FRONTEND_ERROR = "frontend_error"
    DB_ERROR = "db_error"


class ErrorStatus(str, Enum):
    NEW = "new"
    INVESTIGATING = "investigating"
    FIXED = "fixed"
    IGNORED = "ignored"


class FixTier(int, Enum):
    TIER_1 = 1
    TIER_2 = 2


class FixStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class SystemError(BaseModel):
    """System error entity."""

    id: str = Field(..., pattern=r"^err-[a-z0-9]+$", examples=["err-abc123"])
    timestamp: str
    source: ErrorSource
    category: str
    message: str
    stack_trace: Optional[str] = None
    request_id: Optional[str] = None
    context_json: Optional[str] = None
    error_hash: str
    status: ErrorStatus = ErrorStatus.NEW
    fix_attempt_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class FixAttempt(BaseModel):
    """Fix attempt entity."""

    id: str = Field(..., pattern=r"^fix-[a-z0-9]+$", examples=["fix-abc123"])
    error_id: str
    tier: FixTier
    status: FixStatus = FixStatus.PENDING
    action_taken: Optional[str] = None
    agent_session_id: Optional[str] = None
    started_at: str
    completed_at: Optional[str] = None
    created_at: Optional[str] = None


class SystemErrorWithFixes(SystemError):
    """System error with its fix attempts."""

    fix_attempts: List[FixAttempt] = []


class ReportErrorRequest(BaseModel):
    """Request body for frontend error reporting."""

    source: ErrorSource = Field(default=ErrorSource.FRONTEND)
    category: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    stack_trace: Optional[str] = None
    context_json: Optional[str] = None


class UpdateErrorStatusRequest(BaseModel):
    """Request body for updating error status."""

    status: ErrorStatus


class SystemErrorListQuery(PaginationQuery):
    """Query parameters for listing system errors."""

    status: Optional[str] = None
    category: Optional[str] = None
    source: Optional[str] = None
    since: Optional[str] = None
    search: Optional[str] = None


class SystemErrorListResponse(BaseModel):
    """Response for listing system errors."""

    errors: List[SystemError]
    total_count: int


class ReportErrorResponse(BaseModel):
    """Response for reporting an error."""

    error_id: str


class LogsQuery(BaseModel):
    """Query parameters for log tail."""

    lines: Optional[int] = Field(default=100, ge=1, le=1000)


class LogsResponse(BaseModel):
    """Response for log tail."""

    lines: List[str]


class ErrorCountResponse(BaseModel):
    """Response for error count by status."""

    counts: dict
