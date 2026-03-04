"""Pydantic models for the secrets vault API."""

from typing import Optional

from pydantic import BaseModel, Field


class SecretCreate(BaseModel):
    """Request body for creating a secret."""

    name: str = Field(..., min_length=1, max_length=255, description="Unique secret name")
    value: str = Field(..., min_length=1, description="Plaintext value (will be encrypted)")
    description: str = Field(default="", max_length=1000, description="Optional description")
    scope: str = Field(default="global", max_length=100, description="Secret scope")


class SecretUpdate(BaseModel):
    """Request body for updating a secret."""

    value: Optional[str] = Field(default=None, description="New plaintext value (will be encrypted)")
    description: Optional[str] = Field(default=None, max_length=1000, description="New description")


class SecretResponse(BaseModel):
    """Secret metadata response -- NEVER includes the encrypted or plaintext value."""

    id: str
    name: str
    description: str = ""
    scope: str = "global"
    created_by: str = "system"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_accessed_at: Optional[str] = None


class SecretRevealResponse(BaseModel):
    """Response for the reveal endpoint -- contains the decrypted value."""

    id: str
    name: str
    value: str


class SecretPath(BaseModel):
    """Path parameter model for secret endpoints."""

    secret_id: str = Field(..., description="Secret ID")


class VaultStatusResponse(BaseModel):
    """Response for vault status endpoint."""

    configured: bool
    secret_count: int = 0
