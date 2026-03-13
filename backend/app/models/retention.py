"""Pydantic models for retention policy API."""

from typing import Optional

from pydantic import BaseModel, Field


class RetentionPolicyCreate(BaseModel):
    category: str = Field(..., description="Data category (e.g. execution_logs)")
    scope: str = Field("global", description="Scope: global, team, or bot")
    scope_name: str = Field("All Teams", description="Human-readable scope name")
    retention_days: int = Field(90, ge=1, description="Number of days to retain data")
    delete_on_expiry: bool = Field(True, description="Delete data on expiry")
    archive_on_expiry: bool = Field(False, description="Archive data on expiry")
    estimated_size_gb: float = Field(0.0, ge=0.0, description="Estimated data size in GB")


class RetentionPolicyToggle(BaseModel):
    enabled: bool = Field(..., description="Enable or disable the policy")


class RetentionPolicyResponse(BaseModel):
    id: str
    category: str
    scope: str
    scope_name: str
    retention_days: int
    delete_on_expiry: int
    archive_on_expiry: int
    estimated_size_gb: float
    enabled: int
    created_at: Optional[str] = None


class PolicyIdPath(BaseModel):
    policy_id: str = Field(..., description="Retention policy ID")
