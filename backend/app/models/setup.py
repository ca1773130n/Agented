"""Pydantic models for interactive plugin setup."""

from typing import Optional

from pydantic import BaseModel, Field


class StartSetupRequest(BaseModel):
    project_id: str = Field(..., description="Project to run setup in")
    command: str = Field(..., description="Setup command to execute")


class StartSetupResponse(BaseModel):
    execution_id: str
    status: str


class SetupResponseRequest(BaseModel):
    interaction_id: str = Field(..., description="ID of the interaction being responded to")
    response: dict = Field(..., description="User's response (e.g., {answer: 'value'})")


class SetupStatusResponse(BaseModel):
    execution_id: str
    project_id: str
    status: str
    command: str
    started_at: str
    finished_at: Optional[str] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    current_question: Optional[dict] = None


class SetupExecutionPath(BaseModel):
    execution_id: str = Field(..., description="Setup execution ID")
