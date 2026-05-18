"""GRD (Goal-Roadmap-Delivery) Pydantic models for milestones, phases, plans, sessions."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class MilestoneStatus(str, Enum):
    """Milestone status values."""

    PLANNING = "planning"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class PhaseStatus(str, Enum):
    """Project phase status values."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class PlanStatus(str, Enum):
    """Project plan status values."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ProjectSessionStatus(str, Enum):
    """Project session status values."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutionMode(str, Enum):
    """Execution mode for project sessions."""

    AUTONOMOUS = "autonomous"
    INTERACTIVE = "interactive"


class ExecutionType(str, Enum):
    """Execution type for project sessions."""

    DIRECT = "direct"
    RALPH_LOOP = "ralph_loop"
    TEAM_SPAWN = "team_spawn"


# --- Entity models ---


class Milestone(BaseModel):
    """Milestone entity -- a versioned delivery target for a project."""

    id: str = Field(..., pattern=r"^ms-[a-z0-9]+$", examples=["ms-abc123"])
    project_id: str
    version: str
    title: str
    description: Optional[str] = None
    status: MilestoneStatus = MilestoneStatus.PLANNING
    requirements_json: Optional[str] = None
    roadmap_json: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProjectPhase(BaseModel):
    """Project phase entity -- a numbered stage within a milestone."""

    id: str = Field(..., pattern=r"^phase-[a-z0-9]+$", examples=["phase-abc123"])
    milestone_id: str
    phase_number: int
    name: str
    description: Optional[str] = None
    goal: Optional[str] = None
    status: PhaseStatus = PhaseStatus.PENDING
    dependencies: Optional[str] = None
    verification_level: str = "sanity"
    success_criteria: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProjectPlan(BaseModel):
    """Project plan entity -- a concrete execution plan within a phase."""

    id: str = Field(..., pattern=r"^plan-[a-z0-9]+$", examples=["plan-abc123"])
    phase_id: str
    plan_number: int
    title: str
    description: Optional[str] = None
    status: PlanStatus = PlanStatus.PENDING
    tasks_json: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProjectSession(BaseModel):
    """Project session entity -- tracks an agent's work session on a project."""

    id: str = Field(..., pattern=r"^psess-[a-z0-9]+$", examples=["psess-abc123"])
    project_id: str
    phase_id: Optional[str] = None
    plan_id: Optional[str] = None
    agent_id: Optional[str] = None
    status: ProjectSessionStatus = ProjectSessionStatus.ACTIVE
    summary: Optional[str] = None
    log_json: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    pid: Optional[int] = None
    pgid: Optional[int] = None
    worktree_path: Optional[str] = None
    execution_type: str = "direct"
    execution_mode: str = "autonomous"
    idle_timeout_seconds: int = 3600
    max_lifetime_seconds: int = 14400
    last_activity_at: Optional[str] = None


class ProjectSyncState(BaseModel):
    """Tracks file sync state between .planning/ files and the database."""

    id: int
    project_id: str
    file_path: str
    content_hash: Optional[str] = None
    entity_type: str
    entity_id: Optional[str] = None
    last_synced_at: Optional[str] = None


# --- List response models ---


class MilestoneListResponse(BaseModel):
    """Response for listing milestones."""

    milestones: List[Milestone]


class ProjectPhaseListResponse(BaseModel):
    """Response for listing project phases."""

    phases: List[ProjectPhase]


class ProjectPlanListResponse(BaseModel):
    """Response for listing project plans."""

    plans: List[ProjectPlan]


class ProjectSessionListResponse(BaseModel):
    """Response for listing project sessions."""

    sessions: List[ProjectSession]


# --- Create request models ---


class CreateMilestoneRequest(BaseModel):
    """Request body for creating a milestone."""

    project_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1, examples=["v0.4.0"])
    title: str = Field(..., min_length=1)
    description: Optional[str] = None


class CreateProjectPhaseRequest(BaseModel):
    """Request body for creating a project phase."""

    milestone_id: str = Field(..., min_length=1)
    phase_number: int
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    goal: Optional[str] = None
    verification_level: Optional[str] = "sanity"
    success_criteria: Optional[str] = None
    dependencies: Optional[str] = None


class CreateProjectPlanRequest(BaseModel):
    """Request body for creating a project plan."""

    phase_id: str = Field(..., min_length=1)
    plan_number: int
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    tasks_json: Optional[str] = None


class CreateProjectSessionRequest(BaseModel):
    """Request body for creating a project session."""

    project_id: str = Field(..., min_length=1)
    phase_id: Optional[str] = None
    plan_id: Optional[str] = None
    agent_id: Optional[str] = None
    execution_type: Optional[str] = "direct"
    execution_mode: Optional[str] = "autonomous"


# --- Update request models ---


class UpdateMilestoneRequest(BaseModel):
    """Request body for updating a milestone."""

    version: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    requirements_json: Optional[str] = None
    roadmap_json: Optional[str] = None


class UpdateProjectPhaseRequest(BaseModel):
    """Request body for updating a project phase."""

    name: Optional[str] = None
    description: Optional[str] = None
    goal: Optional[str] = None
    status: Optional[str] = None
    verification_level: Optional[str] = None
    success_criteria: Optional[str] = None
    dependencies: Optional[str] = None


class UpdateProjectPlanRequest(BaseModel):
    """Request body for updating a project plan."""

    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    tasks_json: Optional[str] = None


class UpdateProjectSessionRequest(BaseModel):
    """Request body for updating a project session."""

    status: Optional[str] = None
    summary: Optional[str] = None
    log_json: Optional[str] = None
    pid: Optional[int] = None
    worktree_path: Optional[str] = None
    execution_type: Optional[str] = None
    execution_mode: Optional[str] = None
    last_activity_at: Optional[str] = None


# --- Ralph / Team configuration models ---


class RalphConfig(BaseModel):
    """Configuration for Ralph loop execution."""

    max_iterations: int = Field(50, ge=1, le=500)
    completion_promise: str = Field("COMPLETE", min_length=1)
    task_description: str = Field("", description="Task for Ralph to complete")
    no_progress_threshold: int = Field(
        3, ge=1, le=20, description="Consecutive no-progress checks before circuit break"
    )


class TeamConfig(BaseModel):
    """Configuration for team spawn execution."""

    team_size: int = Field(3, ge=2, le=10)
    task_description: str = Field("", description="Task for the team to complete")
    roles: List[str] = Field(default_factory=list, description="Specific roles for team members")


class CreateRalphSessionRequest(BaseModel):
    """Request body for creating a Ralph loop session."""

    cwd: Optional[str] = None
    phase_id: Optional[str] = None
    plan_id: Optional[str] = None
    agent_id: Optional[str] = None
    ralph_config: RalphConfig = Field(default_factory=RalphConfig)


class CreateTeamSessionRequest(BaseModel):
    """Request body for creating a team spawn session."""

    cwd: Optional[str] = None
    phase_id: Optional[str] = None
    plan_id: Optional[str] = None
    agent_id: Optional[str] = None
    team_config: TeamConfig = Field(default_factory=TeamConfig)


class RalphMonitorResponse(BaseModel):
    """Response for Ralph loop monitoring."""

    session_id: str
    iteration: int = 0
    max_iterations: int = 0
    circuit_breaker_triggered: bool = False
    alive: bool = True
    status: str = "active"


class TeamMonitorResponse(BaseModel):
    """Response for team spawn monitoring."""

    session_id: str
    team_name: Optional[str] = None
    members: List[dict] = Field(default_factory=list)
    tasks: List[dict] = Field(default_factory=list)
    alive: bool = True
    status: str = "active"


# ---------------------------------------------------------------------
# v0.7.84 — Ouroboros surface (GRD v0.3.24)
# ---------------------------------------------------------------------


class GrdVerdict(str, Enum):
    """v0.7.84 — phase reflection verdict per Ouroboros pattern.

    Mirrors the four-state verdict the GRD verifier writes into
    ``REFLECTION.md`` after comparing a plan's ``predicted_outcome``
    against actual results.
    """

    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    FALSIFIED = "falsified"
    UNKNOWN = "unknown"


class GrdHealthReport(BaseModel):
    """v0.7.84 — parsed payload from ``gd health --json``.

    The CLI returns a free-form JSON object; we keep the model
    permissive (extra fields allowed) so adopting future GRD
    additions doesn't require an Agented release.
    """

    drift_weighted: Optional[float] = None
    drift_exceeded: Optional[bool] = None
    blocker_count: Optional[int] = None
    blockers: List[dict] = Field(default_factory=list)
    deferred_validations: List[dict] = Field(default_factory=list)
    raw: Optional[dict] = None  # full JSON for fields we don't model yet


class GrdThinkResponse(BaseModel):
    """v0.7.84 — response from ``gd think``.

    ``output_path`` points at the markdown briefing written under
    ``.planning/thoughts/``; the snapshot + counts are the briefing's
    front-of-document JSON header.
    """

    generated_at: Optional[str] = None
    output_path: Optional[str] = None
    snapshot: dict = Field(default_factory=dict)
    verdict_counts: dict = Field(default_factory=dict)
    recent_dead_ends: List[dict] = Field(default_factory=list)
    open_questions: List[dict] = Field(default_factory=list)
    product_idea_collisions: List[dict] = Field(default_factory=list)


class GrdDeadEndEntry(BaseModel):
    """v0.7.84 — single entry in ``.planning/DEAD-ENDS.md``."""

    approach: str
    reason: str
    phase: Optional[str] = None
    recorded_at: Optional[str] = None


class CreateDeadEndRequest(BaseModel):
    """v0.7.84 — request body for ``POST /api/projects/{id}/grd/dead-ends``."""

    approach: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    phase: Optional[str] = None


class GrdGenomeSnapshot(BaseModel):
    """v0.7.84 — response from ``gd-tools genome show``."""

    exists: bool = False
    content: Optional[str] = None
    raw: Optional[dict] = None  # full JSON for forward compat


class GrdMechanicalVerifyResponse(BaseModel):
    """v0.7.84 — bundled output from ``gd-tools verify mechanical``."""

    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    phase: str


# ---------------------------------------------------------------------
# v0.7.88 — GRD evolve session runs
# ---------------------------------------------------------------------


class GrdEvolveStatus(str, Enum):
    """Terminal-state vocabulary for ``grd_evolve_runs.status``."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class StartEvolveRequest(BaseModel):
    """Request body for ``POST /api/projects/{id}/grd/evolve/start``.

    All fields optional — sensible defaults at handler/DB so the
    operator can fire-and-forget with ``{}``.
    """

    iterations: Optional[int] = Field(
        default=1,
        ge=0,
        description="Iteration cap (0 = unlimited, runs until all groups done)",
    )
    pick_pct: Optional[int] = Field(
        default=50, ge=1, le=100, description="Percentage of groups to pick per iteration"
    )
    dry_run: Optional[bool] = False
    no_worktree: Optional[bool] = False
    max_turns: Optional[int] = Field(default=None, ge=1)
    timeout_minutes: Optional[int] = Field(default=None, ge=1)


class GrdEvolveRun(BaseModel):
    """Mirror of a ``grd_evolve_runs`` row for API responses."""

    id: str
    project_id: str
    session_id: str
    status: GrdEvolveStatus
    iteration: int = 0
    total_iterations: Optional[int] = None
    pick_pct: Optional[int] = None
    last_state: Optional[dict] = None
    last_state_synced_at: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    error_message: Optional[str] = None
    config: Optional[dict] = None
