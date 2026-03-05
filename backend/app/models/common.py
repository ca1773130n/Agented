"""Common response models used across the API."""

from http import HTTPStatus
from typing import Optional

from flask import g
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response format.

    New unified shape: code (machine-readable), message (human-readable),
    details (optional structured info), request_id (trace correlation).
    The legacy ``error`` field is kept for backward compatibility.
    """

    code: str = Field(..., description="Machine-readable error code", examples=["NOT_FOUND"])
    message: str = Field(
        ..., description="Human-readable error message", examples=["Bot not found"]
    )
    error: Optional[str] = Field(
        None, description="Legacy error message (same as message, for backward compat)"
    )
    details: Optional[dict] = Field(None, description="Additional error details")
    request_id: Optional[str] = Field(None, description="Request trace ID")


def error_response(
    code: str,
    message: str,
    status: HTTPStatus,
    details: dict = None,
) -> tuple[dict, int]:
    """Build a unified error response tuple for Flask handlers.

    Returns ``(body_dict, http_status_int)`` ready for Flask to serialize.
    Includes the ``error`` field set to *message* for backward compatibility.
    """
    rid = getattr(g, "request_id", None) if g else None
    body = {
        "code": code,
        "message": message,
        "error": message,  # backward compat
        "details": details,
        "request_id": rid,
    }
    return body, status.value if isinstance(status, HTTPStatus) else int(status)


class MessageResponse(BaseModel):
    """Standard success message response."""

    message: str = Field(..., description="Success message", examples=["Bot updated"])


class PaginationQuery(BaseModel):
    """Shared pagination query parameters for list endpoints."""

    limit: Optional[int] = Field(None, ge=1, le=500, description="Max records to return")
    offset: Optional[int] = Field(None, ge=0, description="Number of records to skip")


class ExecutionFilterQuery(PaginationQuery):
    """Query parameters for filtering execution history (API-04)."""

    status: Optional[str] = Field(
        None, description="Filter by status (running, completed, failed, cancelled)"
    )
    trigger_id: Optional[str] = Field(None, description="Filter by trigger ID")
    date_from: Optional[str] = Field(None, description="Start date (ISO 8601, e.g. 2026-03-01)")
    date_to: Optional[str] = Field(None, description="End date (ISO 8601, e.g. 2026-03-31)")
    q: Optional[str] = Field(None, description="Text search over execution output/logs")
