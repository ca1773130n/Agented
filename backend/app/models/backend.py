"""Pydantic models for backend routes."""

from typing import Optional

from pydantic import BaseModel, Field


class AIBackend(BaseModel):
    """AI backend entity."""

    id: str
    name: str
    type: str
    description: Optional[str] = None
    icon: Optional[str] = None
    documentation_url: Optional[str] = None
    is_installed: int = 0
    version: Optional[str] = None
    models: Optional[list] = None
    created_at: Optional[str] = None


class BackendAccount(BaseModel):
    """Backend account entity."""

    id: int
    backend_id: str
    account_name: str
    email: Optional[str] = None
    config_path: Optional[str] = None
    api_key_env: Optional[str] = None
    is_default: int = 0
    plan: Optional[str] = None
    usage_data: Optional[dict] = None
    created_at: Optional[str] = None


class CreateAccountRequest(BaseModel):
    """Request body for creating an account."""

    account_name: str = Field(..., min_length=1)
    email: Optional[str] = None
    config_path: Optional[str] = None
    api_key_env: Optional[str] = None
    is_default: Optional[int] = 0
    plan: Optional[str] = None
    usage_data: Optional[dict] = None


class UpdateAccountRequest(BaseModel):
    """Request body for updating an account."""

    account_name: Optional[str] = None
    email: Optional[str] = None
    config_path: Optional[str] = None
    api_key_env: Optional[str] = None
    is_default: Optional[int] = None
    plan: Optional[str] = None
    usage_data: Optional[dict] = None


class BackendPath(BaseModel):
    """Path parameters for backend routes."""

    backend_id: str = Field(..., description="Backend ID")


class BackendAccountPath(BaseModel):
    """Path parameters for backend account routes."""

    backend_id: str = Field(..., description="Backend ID")
    account_id: int = Field(..., description="Account ID")
