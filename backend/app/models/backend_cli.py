"""Pydantic models for backend CLI routes."""

from typing import Optional

from pydantic import BaseModel, Field


class BackendConnectSessionPath(BaseModel):
    """Path parameters for backend connect session routes."""

    backend_id: str = Field(..., description="Backend ID")
    session_id: str = Field(..., description="CLI session ID")


class SessionResponseRequest(BaseModel):
    """Request body for submitting a response to an interactive CLI session."""

    interaction_id: str = Field(..., description="ID of the interaction being responded to")
    response: dict = Field(..., description="User's response (e.g., {answer: 'value'})")


class TestPromptRequest(BaseModel):
    """Request body for starting a one-shot backend prompt test."""

    backend_type: str = Field(..., description="Backend CLI type (claude, opencode, gemini, codex)")
    prompt: str = Field(..., description="The prompt to send to the backend")
    account_id: Optional[str] = Field(None, description="Optional account email for config lookup")
    model: Optional[str] = Field(None, description="Optional model name override")


class TestStreamPath(BaseModel):
    """Path parameters for backend test stream routes."""

    test_id: str = Field(..., description="Test session ID")
