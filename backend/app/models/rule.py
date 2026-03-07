"""Rule-related Pydantic models."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

RuleType = Literal["pre_check", "post_check", "validation"]


class CreateRuleRequest(BaseModel):
    """Request body for creating a rule."""

    name: str = Field(..., min_length=1)
    rule_type: RuleType = Field(default="validation")
    description: Optional[str] = None
    condition: Optional[str] = None
    action: Optional[str] = None
    enabled: bool = Field(default=True)
    project_id: Optional[str] = None
    source_path: Optional[str] = None


class UpdateRuleRequest(BaseModel):
    """Request body for updating a rule."""

    name: Optional[str] = None
    rule_type: Optional[RuleType] = None
    description: Optional[str] = None
    condition: Optional[str] = None
    action: Optional[str] = None
    enabled: Optional[bool] = None


class GenerateRuleRequest(BaseModel):
    """Request body for generating a rule from a description."""

    description: str = Field(..., min_length=10)
