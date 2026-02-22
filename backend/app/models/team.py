"""Team-related Pydantic models."""

from typing import List, Optional

from pydantic import BaseModel, Field

# Valid topology types for team execution patterns
VALID_TOPOLOGIES = (
    "sequential",
    "parallel",
    "coordinator",
    "generator_critic",
    "hierarchical",
    "human_in_loop",
    "composite",
)

# Valid entity types for team agent assignments
VALID_ENTITY_TYPES = ("skill", "command", "hook", "rule")

# Valid edge types for directed graph relationships
VALID_EDGE_TYPES = ("delegation", "reporting", "messaging", "approval_gate")


class TeamMember(BaseModel):
    """Team member entity - references an agent or super_agent."""

    id: int
    team_id: str
    agent_id: Optional[str] = None
    super_agent_id: Optional[str] = None
    name: str
    email: Optional[str] = None
    role: str = Field(default="member")
    layer: str = Field(default="backend")
    member_type: Optional[str] = None
    tier: Optional[str] = None
    created_at: Optional[str] = None


class TeamEdge(BaseModel):
    """Directed edge between two team members."""

    id: int
    team_id: str
    source_member_id: int
    target_member_id: int
    edge_type: str = Field(default="delegation")
    label: Optional[str] = None
    weight: int = Field(default=1)
    created_at: Optional[str] = None


class TeamConnection(BaseModel):
    """Inter-team connection entity."""

    id: int
    source_team_id: str
    target_team_id: str
    connection_type: str = Field(default="dependency")
    description: Optional[str] = None
    created_at: Optional[str] = None


class CreateTeamEdgeRequest(BaseModel):
    """Request body for creating a team edge."""

    source_member_id: int = Field(..., description="Source team member ID")
    target_member_id: int = Field(..., description="Target team member ID")
    edge_type: str = Field(default="delegation", description="Edge type")
    label: Optional[str] = Field(default=None, description="Edge label")
    weight: int = Field(default=1, description="Edge weight")


class TeamAgentAssignment(BaseModel):
    """Assignment of an entity (skill/command/hook/rule) to an agent within a team."""

    id: int
    team_id: str
    agent_id: str
    entity_type: str
    entity_id: str
    entity_name: Optional[str] = None
    created_at: Optional[str] = None


class AddAssignmentRequest(BaseModel):
    """Request body for adding an agent assignment."""

    entity_type: str = Field(..., description="Type: skill, command, hook, or rule")
    entity_id: str = Field(..., description="ID of the entity to assign")
    entity_name: Optional[str] = Field(default=None, description="Display name of the entity")


class AddAssignmentResponse(BaseModel):
    """Response for add assignment endpoint."""

    message: str
    assignment: TeamAgentAssignment


class AssignmentListResponse(BaseModel):
    """Response for list assignments endpoint."""

    assignments: List[TeamAgentAssignment]


class Team(BaseModel):
    """Team entity."""

    id: str = Field(..., pattern=r"^team-[a-z0-9]+$", examples=["team-abc123"])
    name: str = Field(..., examples=["Platform Team"])
    description: Optional[str] = None
    color: str = Field(default="#00d4ff")
    leader_id: Optional[str] = Field(default=None, description="Agent ID of the team leader")
    leader_name: Optional[str] = Field(default=None, description="Name of the leader agent")
    member_count: int = Field(default=0)
    topology: Optional[str] = Field(default=None, description="Execution topology pattern")
    topology_config: Optional[str] = Field(default=None, description="JSON config for the topology")
    trigger_source: Optional[str] = Field(
        default=None, description="Trigger type: webhook, github, manual, scheduled"
    )
    trigger_config: Optional[str] = Field(
        default=None, description="JSON config for trigger matching"
    )
    enabled: int = Field(default=1, description="Whether the team is enabled")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TeamDetail(Team):
    """Team with full member list."""

    members: List[TeamMember] = Field(default_factory=list)


class TeamListResponse(BaseModel):
    """Response for list teams endpoint."""

    teams: List[Team]


class CreateTeamRequest(BaseModel):
    """Request body for creating a team."""

    name: str = Field(..., min_length=1, examples=["Platform Team"])
    description: Optional[str] = None
    color: Optional[str] = Field(default="#00d4ff")
    leader_id: Optional[str] = Field(default=None, description="Agent ID to assign as team leader")
    topology: Optional[str] = Field(default=None, description="Execution topology pattern")
    topology_config: Optional[str] = Field(default=None, description="JSON config for the topology")
    trigger_source: Optional[str] = Field(default=None, description="Trigger type")
    trigger_config: Optional[str] = Field(default=None, description="Trigger matching config")


class CreateTeamResponse(BaseModel):
    """Response for create team endpoint."""

    message: str
    team: Team


class UpdateTeamRequest(BaseModel):
    """Request body for updating a team."""

    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    leader_id: Optional[str] = Field(default=None, description="Agent ID to assign as team leader")
    topology: Optional[str] = Field(default=None, description="Execution topology pattern")
    topology_config: Optional[str] = Field(default=None, description="JSON config for the topology")
    trigger_source: Optional[str] = Field(default=None, description="Trigger type")
    trigger_config: Optional[str] = Field(default=None, description="Trigger matching config")
    enabled: Optional[int] = Field(default=None, description="Whether the team is enabled")


class TeamRunRequest(BaseModel):
    """Request body for manual team run."""

    message: Optional[str] = Field(default=None, description="Optional message for the run")


class TeamRunResponse(BaseModel):
    """Response for team run endpoint."""

    message: str
    execution_ids: List[str] = Field(default_factory=list)


class CreateTeamMemberRequest(BaseModel):
    """Request body for adding a team member."""

    agent_id: Optional[str] = Field(default=None, description="Agent ID to add as member")
    super_agent_id: Optional[str] = Field(
        default=None, description="SuperAgent ID to add as member"
    )
    name: Optional[str] = Field(default=None, min_length=1)
    email: Optional[str] = None
    role: Optional[str] = Field(default="member")
    layer: Optional[str] = Field(default="backend")
    tier: Optional[str] = Field(default=None, description="Agent tier: leader, senior, or member")


class AddTeamMemberResponse(BaseModel):
    """Response for add team member endpoint."""

    message: str
    member: TeamMember


class UpdateTeamMemberRequest(BaseModel):
    """Request body for updating a team member."""

    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    layer: Optional[str] = None
    tier: Optional[str] = Field(default=None, description="Agent tier: leader, senior, or member")


class GenerateTeamRequest(BaseModel):
    """Request body for AI-powered team configuration generation."""

    description: str = Field(
        ..., min_length=10, description="Natural language description of desired team"
    )


class GenerateTeamResponse(BaseModel):
    """Response for team generation endpoint."""

    config: dict
    warnings: List[str] = Field(default_factory=list)
