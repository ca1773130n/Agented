"""Skill-related Pydantic models."""

from typing import List, Optional

from pydantic import BaseModel, Field


class SkillInfo(BaseModel):
    """Discovered skill information."""

    name: str
    description: Optional[str] = None
    source_path: Optional[str] = None


class SkillListResponse(BaseModel):
    """Response for listing all discovered skills."""

    skills: List[SkillInfo]


class UserSkill(BaseModel):
    """User's configured skill."""

    id: int
    skill_name: str
    skill_path: str
    description: Optional[str] = None
    enabled: int = Field(default=1)
    selected_for_harness: int = Field(default=0)
    metadata: Optional[str] = None  # JSON
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UserSkillListResponse(BaseModel):
    """Response for listing user skills."""

    skills: List[UserSkill]


class AddUserSkillRequest(BaseModel):
    """Request to add a user skill."""

    skill_name: str = Field(..., min_length=1)
    skill_path: str = Field(..., min_length=1)
    description: Optional[str] = None
    enabled: int = Field(default=1, ge=0, le=1)
    selected_for_harness: int = Field(default=0, ge=0, le=1)
    metadata: Optional[str] = None


class AddUserSkillResponse(BaseModel):
    """Response after adding a user skill."""

    message: str
    id: int
    skill_name: str


class UpdateUserSkillRequest(BaseModel):
    """Request to update a user skill."""

    skill_name: Optional[str] = None
    skill_path: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[int] = Field(None, ge=0, le=1)
    selected_for_harness: Optional[int] = Field(None, ge=0, le=1)
    metadata: Optional[str] = None


class ToggleHarnessRequest(BaseModel):
    """Request to toggle a skill's harness selection."""

    skill_id: int
    selected: bool


class TestSkillRequest(BaseModel):
    """Request to test a skill in the playground."""

    skill_name: str = Field(..., min_length=1)
    input: str = Field(default="")


class TestSkillResponse(BaseModel):
    """Response after starting a skill test."""

    test_id: str
    message: str
    status: str = "running"


class HarnessConfig(BaseModel):
    """Harness configuration for one-harness integration."""

    skills: List[UserSkill]
    config_json: str  # Generated config for claude-plugin-marketplace


class HarnessSkillsResponse(BaseModel):
    """Response for harness skills."""

    skills: List[UserSkill]


class SkillsShResult(BaseModel):
    """A skill from skills.sh."""

    name: str
    description: Optional[str] = None
    source: Optional[str] = None
    install_cmd: Optional[str] = None
    installed: bool = False


class SkillsShSearchResponse(BaseModel):
    """Response for skills.sh search."""

    results: List[SkillsShResult]
    source: str = "skills.sh"
    npx_available: Optional[bool] = None


class SkillsShInstallRequest(BaseModel):
    """Request to install a skills.sh skill."""

    source: str = Field(
        ...,
        min_length=1,
        description="Skills.sh source identifier (e.g., vercel-labs/agent-skills@react-best-practices)",
    )


class SkillsShInstallResponse(BaseModel):
    """Response after installing a skills.sh skill."""

    message: str
    output: Optional[str] = None
