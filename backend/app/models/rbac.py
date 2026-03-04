"""RBAC Pydantic models for request/response validation."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

ALLOWED_ROLES = ("viewer", "operator", "editor", "admin")


class UserRoleCreate(BaseModel):
    """Request body for creating a user role."""

    api_key: str = Field(..., description="API key to associate with the role")
    label: str = Field(..., description="Human-readable label for this role assignment")
    role: str = Field("viewer", description="Role: viewer, operator, editor, or admin")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ALLOWED_ROLES:
            raise ValueError(f"role must be one of {ALLOWED_ROLES}")
        return v


class UserRoleUpdate(BaseModel):
    """Request body for updating a user role."""

    label: Optional[str] = Field(None, description="New label")
    role: Optional[str] = Field(None, description="New role")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ALLOWED_ROLES:
            raise ValueError(f"role must be one of {ALLOWED_ROLES}")
        return v


class UserRoleResponse(BaseModel):
    """Response model for a user role record."""

    id: str
    api_key: str
    label: str
    role: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RolePath(BaseModel):
    """Path parameter for role endpoints."""

    role_id: str = Field(..., description="Role record ID")
