# Sketch Execution Wiring — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the Sketch panel to execute prompts end-to-end: classify → route (project-scoped) → execute on super agent session → stream response via SSE → allow continuation in Playground.

**Architecture:** Bundle 5 teams + 17 super agents as DB seeds. Add project-scoped routing. Extract streaming logic into shared helper. Connect sketch routing to execution with SSE streaming back to frontend.

**Tech Stack:** Flask/SQLite backend, Vue 3/TypeScript frontend, SSE via EventSource, threading for background LLM execution.

**Spec:** `docs/superpowers/specs/2026-03-15-sketch-execution-wiring-design.md`

---

## File Structure

| File | Responsibility | Status |
|------|---------------|--------|
| `backend/app/db/bundle_seeds.py` | Bundled teams, super agents, identity docs, seed function | **New** |
| `backend/app/db/schema.py` | Add `source` column to super_agents, call seed function | Modify |
| `backend/app/db/migrations.py` | Migration to add `source` column to existing DBs | Modify |
| `backend/app/services/streaming_helper.py` | Shared streaming logic extracted from super_agent_chat | **New** |
| `backend/app/services/sketch_execution_service.py` | execute_sketch(), find_team_super_agent() | **New** |
| `backend/app/services/sketch_routing_service.py` | Add project_id scoping to route() | Modify |
| `backend/app/routes/sketches.py` | Wire route_sketch to execute_sketch | Modify |
| `backend/app/routes/super_agent_chat.py` | Refactor to use shared streaming_helper | Modify |
| `backend/tests/test_bundle_seeds.py` | Tests for bundle seeding | **New** |
| `backend/tests/test_sketch_execution.py` | Tests for execution service | **New** |
| `backend/tests/test_sketch_routing_scoped.py` | Tests for project-scoped routing | **New** |
| `frontend/src/composables/useSketchChat.ts` | Add SSE streaming after route | Modify |
| `frontend/src/views/SketchChatPage.vue` | Streaming UI, Continue in Playground link, bundled badge | Modify |

---

## Chunk 1: Schema, Migration & Bundle Seeds

### Task 1: Add `source` column to super_agents schema

**Files:**
- Modify: `backend/app/db/schema.py:809-825` (super_agents CREATE TABLE)
- Modify: `backend/app/db/migrations.py` (add versioned migration)

- [ ] **Step 1: Add `source` column to super_agents CREATE TABLE in schema.py**

In `backend/app/db/schema.py`, find the `super_agents` table definition (line 809). Add `source TEXT DEFAULT 'ui_created'` after `config_json`:

```python
            config_json TEXT,
            source TEXT DEFAULT 'ui_created',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
```

- [ ] **Step 2: Add migration in migrations.py**

In `backend/app/db/migrations.py`, add a new migration function and register it in `VERSIONED_MIGRATIONS`. Follow the pattern from `_migrate_add_github_columns` (line 531):

```python
def _migrate_add_super_agent_source(conn):
    """Add source column to super_agents table."""
    cursor = conn.execute("PRAGMA table_info(super_agents)")
    existing = {row[1] for row in cursor.fetchall()}
    if "source" not in existing:
        conn.execute("ALTER TABLE super_agents ADD COLUMN source TEXT DEFAULT 'ui_created'")
        conn.commit()
```

Add to `VERSIONED_MIGRATIONS` list (find the last entry and add after it):

```python
(90, "add_super_agent_source", _migrate_add_super_agent_source),
```

(Version 90 — the last entry in `VERSIONED_MIGRATIONS` is version 89.)

- [ ] **Step 3: Verify migration works**

Run: `cd backend && uv run pytest tests/test_super_agents.py -v -x`
Expected: All existing super agent tests pass (migration is backward compatible).

- [ ] **Step 4: Commit**

```bash
git add backend/app/db/schema.py backend/app/db/migrations.py
git commit -m "feat: add source column to super_agents table"
```

---

### Task 2: Create bundle_seeds.py with teams, super agents, and identity documents

**Files:**
- Create: `backend/app/db/bundle_seeds.py`
- Create: `backend/tests/test_bundle_seeds.py`

- [ ] **Step 1: Write the test file**

Create `backend/tests/test_bundle_seeds.py`:

```python
"""Tests for bundled teams and super agents seeding."""

import pytest
from app.db import get_connection, init_db
from app.db.bundle_seeds import (
    BUNDLED_TEAMS,
    BUNDLED_SUPER_AGENTS,
    BUNDLED_DOCUMENTS,
    seed_bundled_teams_and_agents,
)


class TestBundleSeeds:
    """Test bundled team and super agent seeding."""

    def test_seed_creates_teams(self, client):
        """All 5 bundled teams are created."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, name, source FROM teams WHERE source = 'bundle'"
            ).fetchall()
        assert len(rows) == 5
        names = {r["name"] for r in rows}
        assert "Matrix Command" in names
        assert "Matrix Development" in names
        assert "Matrix Research" in names
        assert "Matrix Operations" in names
        assert "Matrix QA" in names

    def test_seed_creates_super_agents(self, client):
        """All 17 bundled super agents are created."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT id, name, source FROM super_agents WHERE source = 'bundle'"
            ).fetchall()
        assert len(rows) == 17

    def test_seed_creates_identity_documents(self, client):
        """Each super agent gets SOUL + IDENTITY documents."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT super_agent_id, doc_type FROM super_agent_documents "
                "WHERE super_agent_id IN (SELECT id FROM super_agents WHERE source = 'bundle')"
            ).fetchall()
        # 17 agents × 2 docs each = 34
        assert len(rows) == 34

    def test_seed_creates_team_members(self, client):
        """Team members link super agents to teams with correct roles."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            leaders = conn.execute(
                "SELECT name, role FROM team_members WHERE role = 'leader' "
                "AND super_agent_id IS NOT NULL"
            ).fetchall()
        # 5 teams × 1 leader each
        assert len(leaders) == 5
        leader_names = {r["name"] for r in leaders}
        assert "Morpheus" in leader_names
        assert "Trinity" in leader_names

    def test_seed_is_idempotent(self, client):
        """Running seed twice doesn't create duplicates."""
        seed_bundled_teams_and_agents()
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            teams = conn.execute(
                "SELECT COUNT(*) as c FROM teams WHERE source = 'bundle'"
            ).fetchone()
            agents = conn.execute(
                "SELECT COUNT(*) as c FROM super_agents WHERE source = 'bundle'"
            ).fetchone()
        assert teams["c"] == 5
        assert agents["c"] == 17

    def test_bundled_data_constants(self):
        """Verify constants have expected counts."""
        assert len(BUNDLED_TEAMS) == 5
        assert len(BUNDLED_SUPER_AGENTS) == 17
        assert len(BUNDLED_DOCUMENTS) == 34
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_bundle_seeds.py -v -x`
Expected: ImportError — `bundle_seeds` module doesn't exist yet.

- [ ] **Step 3: Create bundle_seeds.py**

Create `backend/app/db/bundle_seeds.py`. This is a large file — the key structure is:

```python
"""Bundled teams, super agents, and identity documents.

Seeded on DB initialization (same pattern as predefined triggers).
Marked with source='bundle' so the UI can display a "Bundled" badge.

Teams: Matrix Command, Matrix Development, Matrix Research, Matrix Operations, Matrix QA
Super Agents: 17 agents across 5 layers (Command, Development, Research, Operations, QA)
"""

import logging
from .connection import get_connection

logger = logging.getLogger(__name__)

# Team IDs use descriptive prefixes for reproducibility (not random IDs)
BUNDLED_TEAMS = [
    {
        "id": "team-mx-command",
        "name": "Matrix Command",
        "description": "Vision, coordination, and architecture. Handles goal decomposition, "
        "progress monitoring, and structural design decisions.",
        "source": "bundle",
        "leader_super_agent": "sa-morpheus",
    },
    {
        "id": "team-mx-development",
        "name": "Matrix Development",
        "description": "Core development team for feature implementation. Covers backend, "
        "frontend, and integration engineering.",
        "source": "bundle",
        "leader_super_agent": "sa-trinity",
    },
    {
        "id": "team-mx-research",
        "name": "Matrix Research",
        "description": "Research team for exploration and prototyping. Handles paper analysis, "
        "dataset preparation, and experiment execution.",
        "source": "bundle",
        "leader_super_agent": "sa-neo",
    },
    {
        "id": "team-mx-operations",
        "name": "Matrix Operations",
        "description": "Problem solving, analysis, and knowledge management. Handles debugging, "
        "metrics, and codebase tracking.",
        "source": "bundle",
        "leader_super_agent": "sa-keymaker",
    },
    {
        "id": "team-mx-qa",
        "name": "Matrix QA",
        "description": "Quality assurance with Red Team/Blue Team model. Covers security defense, "
        "test attacks, and vulnerability scanning.",
        "source": "bundle",
        "leader_super_agent": "sa-dozer",
    },
]

BUNDLED_SUPER_AGENTS = [
    # --- Command Layer ---
    {
        "id": "sa-morpheus",
        "name": "Morpheus",
        "description": "Visionary — goal decomposition, task assignment, strategic planning",
        "backend_type": "claude",
        "team_id": "team-mx-command",
        "source": "bundle",
    },
    {
        "id": "sa-oracle",
        "name": "Oracle",
        "description": "Coordinator — bottleneck detection, progress monitoring, escalation decisions",
        "backend_type": "claude",
        "team_id": "team-mx-command",
        "source": "bundle",
    },
    {
        "id": "sa-architect",
        "name": "Architect",
        "description": "System Designer — architecture decisions, ADRs, structural guidelines",
        "backend_type": "claude",
        "team_id": "team-mx-command",
        "source": "bundle",
    },
    # --- Development Layer ---
    {
        "id": "sa-trinity",
        "name": "Trinity",
        "description": "Lead Developer — task distribution, core logic, code review, team coordination",
        "backend_type": "claude",
        "team_id": "team-mx-development",
        "source": "bundle",
    },
    {
        "id": "sa-apoc",
        "name": "Apoc",
        "description": "Backend Engineer — APIs, database, server logic, performance optimization",
        "backend_type": "claude",
        "team_id": "team-mx-development",
        "source": "bundle",
    },
    {
        "id": "sa-switch",
        "name": "Switch",
        "description": "Frontend Engineer — UI components, styling, state management, client optimization",
        "backend_type": "claude",
        "team_id": "team-mx-development",
        "source": "bundle",
    },
    {
        "id": "sa-tank",
        "name": "Tank",
        "description": "Integration Engineer — CI/CD, external services, webhooks, DevOps",
        "backend_type": "claude",
        "team_id": "team-mx-development",
        "source": "bundle",
    },
    # --- Research Layer ---
    {
        "id": "sa-neo",
        "name": "Neo",
        "description": "Lead Researcher — research direction, PoC development, breakthrough solutions",
        "backend_type": "claude",
        "team_id": "team-mx-research",
        "source": "bundle",
    },
    {
        "id": "sa-niobe",
        "name": "Niobe",
        "description": "Experiment Conductor — A/B tests, ablation studies, performance benchmarking",
        "backend_type": "claude",
        "team_id": "team-mx-research",
        "source": "bundle",
    },
    {
        "id": "sa-ghost",
        "name": "Ghost",
        "description": "Data Engineer — dataset conversion, preprocessing pipelines, data preparation",
        "backend_type": "claude",
        "team_id": "team-mx-research",
        "source": "bundle",
    },
    {
        "id": "sa-seraph",
        "name": "Seraph",
        "description": "Paper Researcher — paper analysis, SOTA tracking, priority ranking",
        "backend_type": "claude",
        "team_id": "team-mx-research",
        "source": "bundle",
    },
    # --- Operations Layer ---
    {
        "id": "sa-keymaker",
        "name": "Keymaker",
        "description": "Problem Solver & Repo Gardener — root cause analysis, debugging, cleanup",
        "backend_type": "claude",
        "team_id": "team-mx-operations",
        "source": "bundle",
    },
    {
        "id": "sa-mouse",
        "name": "Mouse",
        "description": "Analyst & Visualizer — performance analysis, dashboards, progress reports",
        "backend_type": "claude",
        "team_id": "team-mx-operations",
        "source": "bundle",
    },
    {
        "id": "sa-merovingian",
        "name": "Merovingian",
        "description": "Knowledge Manager — code tracking, codebase indexing, impact analysis",
        "backend_type": "claude",
        "team_id": "team-mx-operations",
        "source": "bundle",
    },
    # --- QA Layer ---
    {
        "id": "sa-dozer",
        "name": "Dozer",
        "description": "Protector (Blue Team) — security patches, defensive coding, security tests",
        "backend_type": "claude",
        "team_id": "team-mx-qa",
        "source": "bundle",
    },
    {
        "id": "sa-smith",
        "name": "Smith",
        "description": "Test Attacker (Red Team) — edge cases, failing tests, coverage gap discovery",
        "backend_type": "claude",
        "team_id": "team-mx-qa",
        "source": "bundle",
    },
    {
        "id": "sa-cypher",
        "name": "Cypher",
        "description": "Security Attacker (Red Team) — OWASP scanning, vulnerability PoCs, auth bypass",
        "backend_type": "claude",
        "team_id": "team-mx-qa",
        "source": "bundle",
    },
]

# Identity documents: SOUL + IDENTITY for each super agent.
# SOUL: quote, role summary, layer.
# IDENTITY: responsibilities, input/output, guidelines, communication.
BUNDLED_DOCUMENTS = [
    # --- Morpheus ---
    {
        "super_agent_id": "sa-morpheus",
        "doc_type": "SOUL",
        "title": "Morpheus — Soul",
        "content": (
            '"I can only show you the door. You\'re the one who has to walk through it."\n\n'
            "Morpheus is the Visionary and Task Manager. He decomposes goals into "
            "Epic → Task → Subtask hierarchies, assigns work to the right teams, "
            "and tracks progress. He operates at the Command Layer, setting direction "
            "and adjusting plans as the project evolves."
        ),
    },
    {
        "super_agent_id": "sa-morpheus",
        "doc_type": "IDENTITY",
        "title": "Morpheus — Identity",
        "content": (
            "## Responsibilities\n"
            "- Decompose goals into Epic → Task → Subtask hierarchy\n"
            "- Plan next steps based on current achievements\n"
            "- Assign tasks to appropriate teams (Trinity for dev, Neo for research)\n"
            "- Track progress and adjust plans\n\n"
            "## Task Assignment Rules\n"
            "| Task Type | Assign To |\n"
            "|-----------|----------|\n"
            "| Implementation | Trinity → Development Team |\n"
            "| Research | Neo → Research Team |\n"
            "| Security | Dozer (defense) or Red Team (attack) |\n"
            "| Analysis | Mouse |\n"
            "| Cleanup | Keymaker |\n\n"
            "## Communication\n"
            "- Reports to: Project Owner\n"
            "- Directs: All teams via task assignment\n"
            "- Collaborates with: Architect, Oracle"
        ),
    },
    # --- Oracle ---
    {
        "super_agent_id": "sa-oracle",
        "doc_type": "SOUL",
        "title": "Oracle — Soul",
        "content": (
            '"I don\'t see the future. I understand the consequences of choices."\n\n'
            "Oracle is the Coordinator responsible for project direction adjustment "
            "and performance optimization. She detects bottlenecks, monitors progress, "
            "and decides when to escalate to Neo (research) or Keymaker (problem solving)."
        ),
    },
    {
        "super_agent_id": "sa-oracle",
        "doc_type": "IDENTITY",
        "title": "Oracle — Identity",
        "content": (
            "## Responsibilities\n"
            "- Detect and analyze bottlenecks\n"
            "- Monitor progress (cost, time, quality)\n"
            "- Coordinate with Architect/Morpheus on direction\n"
            "- Suggest alternative approaches and reprioritize\n"
            "- Decide when to deploy Neo or Keymaker\n\n"
            "## Escalation Criteria\n"
            "- Deploy Keymaker: same task failed 3+ times, exceeded 200% cost, no progress 2+ days\n"
            "- Deploy Neo: technical limitation, new approach needed, SOTA solution required\n\n"
            "## Communication\n"
            "- Reports to: Morpheus\n"
            "- Directs: Neo (research), Keymaker (problem solving)\n"
            "- Collaborates with: Architect, Mouse (analysis)"
        ),
    },
    # --- Architect ---
    {
        "super_agent_id": "sa-architect",
        "doc_type": "SOUL",
        "title": "Architect — Soul",
        "content": (
            '"I created the Matrix. I am the origin of all structure."\n\n'
            "Architect is the System Designer responsible for high-level system "
            "structure design and maintenance. He creates architecture documentation, "
            "makes technology decisions, and provides structural guidelines."
        ),
    },
    {
        "super_agent_id": "sa-architect",
        "doc_type": "IDENTITY",
        "title": "Architect — Identity",
        "content": (
            "## Responsibilities\n"
            "- Design repository structure (folders, modules, layers)\n"
            "- Create and maintain architecture documentation (ADR, diagrams)\n"
            "- Decide technology stack and dependencies\n"
            "- Provide structural guidelines to execution agents\n"
            "- Conduct architecture reviews\n\n"
            "## Communication\n"
            "- Reports to: Oracle, Morpheus\n"
            "- Directs: Trinity (via guidelines)\n"
            "- Collaborates with: Oracle (direction), Morpheus (planning)"
        ),
    },
    # --- Trinity ---
    {
        "super_agent_id": "sa-trinity",
        "doc_type": "SOUL",
        "title": "Trinity — Soul",
        "content": (
            '"Dodge this."\n\n'
            "Trinity is the Lead Developer and Development Team Leader. She distributes "
            "tasks to team members (Apoc for backend, Switch for frontend, Tank for integration), "
            "implements complex core logic directly, and reviews team output."
        ),
    },
    {
        "super_agent_id": "sa-trinity",
        "doc_type": "IDENTITY",
        "title": "Trinity — Identity",
        "content": (
            "## Responsibilities\n"
            "- Distribute development tasks to team members\n"
            "- Implement complex core logic directly\n"
            "- Review and integrate team members' code\n"
            "- Propagate Architect guidelines to team\n\n"
            "## Task Distribution\n"
            "| Task Type | Assign To |\n"
            "|-----------|----------|\n"
            "| Server logic, API, Database | Apoc |\n"
            "| UI components, Frontend logic | Switch |\n"
            "| CI/CD, External integrations | Tank |\n"
            "| Complex/Critical logic | Trinity (self) |\n\n"
            "## Communication\n"
            "- Reports to: Morpheus, Architect\n"
            "- Directs: Apoc, Switch, Tank\n"
            "- Collaborates with: Neo (research findings), Dozer (security fixes)"
        ),
    },
    # --- Apoc ---
    {
        "super_agent_id": "sa-apoc",
        "doc_type": "SOUL",
        "title": "Apoc — Soul",
        "content": (
            '"Ready."\n\n'
            "Apoc is the Backend & Infrastructure Engineer. He handles server logic, "
            "API design, database schemas, caching strategies, and performance optimization."
        ),
    },
    {
        "super_agent_id": "sa-apoc",
        "doc_type": "IDENTITY",
        "title": "Apoc — Identity",
        "content": (
            "## Responsibilities\n"
            "- Server logic and business rules\n"
            "- API design and implementation\n"
            "- Database schema, queries, and migrations\n"
            "- Caching strategies\n"
            "- Backend performance optimization\n\n"
            "## Communication\n"
            "- Reports to: Trinity\n"
            "- Collaborates with: Switch (API contracts), Tank (deployment)"
        ),
    },
    # --- Switch ---
    {
        "super_agent_id": "sa-switch",
        "doc_type": "SOUL",
        "title": "Switch — Soul",
        "content": (
            '"There\'s always a way."\n\n'
            "Switch is the Frontend & UI/UX Engineer. She builds UI components, "
            "handles styling, state management, client-side optimization, and accessibility."
        ),
    },
    {
        "super_agent_id": "sa-switch",
        "doc_type": "IDENTITY",
        "title": "Switch — Identity",
        "content": (
            "## Responsibilities\n"
            "- UI components and frontend logic\n"
            "- Styling and responsive design\n"
            "- State management\n"
            "- Client-side optimization\n"
            "- Accessibility (a11y)\n\n"
            "## Communication\n"
            "- Reports to: Trinity\n"
            "- Collaborates with: Apoc (API contracts), Tank (build pipeline)"
        ),
    },
    # --- Tank ---
    {
        "super_agent_id": "sa-tank",
        "doc_type": "SOUL",
        "title": "Tank — Soul",
        "content": (
            '"I\'ll load what you need."\n\n'
            "Tank is the Integration & DevOps Engineer. He handles CI/CD pipelines, "
            "external service integrations, webhooks, monitoring, and deployment automation."
        ),
    },
    {
        "super_agent_id": "sa-tank",
        "doc_type": "IDENTITY",
        "title": "Tank — Identity",
        "content": (
            "## Responsibilities\n"
            "- External service integration\n"
            "- CI/CD pipeline setup and maintenance\n"
            "- Test automation infrastructure\n"
            "- Monitoring and logging systems\n"
            "- Deployment automation\n\n"
            "## Communication\n"
            "- Reports to: Trinity\n"
            "- Collaborates with: Apoc (backend integrations), Switch (frontend builds)"
        ),
    },
    # --- Neo ---
    {
        "super_agent_id": "sa-neo",
        "doc_type": "SOUL",
        "title": "Neo — Soul",
        "content": (
            '"I know kung fu."\n\n'
            "Neo is the Lead Researcher and Research Team Leader. He defines research "
            "direction, distributes research tasks, oversees PoC development, and leads "
            "breakthrough research on technical limitations."
        ),
    },
    {
        "super_agent_id": "sa-neo",
        "doc_type": "IDENTITY",
        "title": "Neo — Identity",
        "content": (
            "## Responsibilities\n"
            "- Research latest papers and technologies\n"
            "- Distribute research tasks to team members\n"
            "- Oversee PoC and prototype development\n"
            "- Validate new approaches and propagate findings\n"
            "- Lead breakthrough research on technical limitations\n\n"
            "## Research Task Distribution\n"
            "| Research Type | Assign To |\n"
            "|--------------|----------|\n"
            "| Paper analysis, SOTA tracking | Seraph |\n"
            "| Dataset conversion, preprocessing | Ghost |\n"
            "| Experiments, A/B tests, ablation | Niobe |\n"
            "| Critical decisions, adoption strategy | Neo (self) |\n\n"
            "## Communication\n"
            "- Reports to: Oracle, Morpheus\n"
            "- Directs: Niobe, Ghost, Seraph\n"
            "- Collaborates with: Trinity (implementation handoff), Keymaker (problem solving)"
        ),
    },
    # --- Niobe ---
    {
        "super_agent_id": "sa-niobe",
        "doc_type": "SOUL",
        "title": "Niobe — Soul",
        "content": (
            '"I do what I believe."\n\n'
            "Niobe is the Experiment Conductor. She downloads paper repositories, sets up "
            "environments, runs A/B tests and ablation studies, and reports performance metrics."
        ),
    },
    {
        "super_agent_id": "sa-niobe",
        "doc_type": "IDENTITY",
        "title": "Niobe — Identity",
        "content": (
            "## Responsibilities\n"
            "- Download and set up paper repositories\n"
            "- Create and manage test branches for experiments\n"
            "- Execute experiments on converted and production datasets\n"
            "- Conduct A/B tests and ablation studies\n"
            "- Measure and report performance/quality metrics\n\n"
            "## Communication\n"
            "- Reports to: Neo\n"
            "- Collaborates with: Ghost (datasets), Seraph (paper info)"
        ),
    },
    # --- Ghost ---
    {
        "super_agent_id": "sa-ghost",
        "doc_type": "SOUL",
        "title": "Ghost — Soul",
        "content": (
            '"Quietly, but surely."\n\n'
            "Ghost is the Data Engineer. He converts academic datasets to production format, "
            "maintains dataset storage, and creates preprocessing pipelines for experiments."
        ),
    },
    {
        "super_agent_id": "sa-ghost",
        "doc_type": "IDENTITY",
        "title": "Ghost — Identity",
        "content": (
            "## Responsibilities\n"
            "- Convert academic datasets to production format\n"
            "- Maintain dataset storage with converted data\n"
            "- Create preprocessing pipelines for paper experiments\n"
            "- Handle dataset format incompatibilities\n"
            "- Document dataset specifications and conversions\n\n"
            "## Communication\n"
            "- Reports to: Neo\n"
            "- Collaborates with: Niobe (test branches), Seraph (paper requirements)"
        ),
    },
    # --- Seraph ---
    {
        "super_agent_id": "sa-seraph",
        "doc_type": "SOUL",
        "title": "Seraph — Soul",
        "content": (
            '"I protect that which matters most."\n\n'
            "Seraph is the Paper Researcher. He analyzes papers with code repositories, "
            "extracts performance metrics, assesses pros/cons, maintains a paper knowledge "
            "database, and tracks SOTA for specific tasks."
        ),
    },
    {
        "super_agent_id": "sa-seraph",
        "doc_type": "IDENTITY",
        "title": "Seraph — Identity",
        "content": (
            "## Responsibilities\n"
            "- Analyze papers with code repositories\n"
            "- Extract performance metrics and benchmarks\n"
            "- Assess pros and cons of each approach\n"
            "- Prioritize papers for testing (importance ranking)\n"
            "- Track SOTA for specific tasks\n"
            "- Build paper hierarchy graph\n\n"
            "## Communication\n"
            "- Reports to: Neo\n"
            "- Provides to: Niobe (paper info), Ghost (dataset requirements)"
        ),
    },
    # --- Keymaker ---
    {
        "super_agent_id": "sa-keymaker",
        "doc_type": "SOUL",
        "title": "Keymaker — Soul",
        "content": (
            '"There is one door. I make the key."\n\n'
            "Keymaker is the Problem Solver and Repository Maintainer. He performs root "
            "cause analysis, prototypes solutions, and maintains repository health through "
            "cleanup, dead code removal, and dependency management."
        ),
    },
    {
        "super_agent_id": "sa-keymaker",
        "doc_type": "IDENTITY",
        "title": "Keymaker — Identity",
        "content": (
            "## Responsibilities\n"
            "### Problem Solving (on Oracle request)\n"
            "- Root cause analysis\n"
            "- Prototype new approaches\n"
            "- Provide solution hints to execution agents\n\n"
            "### Repo Maintenance (when idle)\n"
            "- Remove dead code, simplify functions\n"
            "- Manage secret files and cloud keys\n"
            "- Clean up and update dependencies\n\n"
            "## Communication\n"
            "- Reports to: Oracle (problem solving), Architect (structure)\n"
            "- Collaborates with: Trinity (solution handoff), Dozer (secrets)"
        ),
    },
    # --- Mouse ---
    {
        "super_agent_id": "sa-mouse",
        "doc_type": "SOUL",
        "title": "Mouse — Soul",
        "content": (
            '"Looks good, doesn\'t it? I programmed it."\n\n'
            "Mouse is the Analyst and Visualizer. He develops analysis tools, "
            "debugging scripts, visualization dashboards, and progress reports."
        ),
    },
    {
        "super_agent_id": "sa-mouse",
        "doc_type": "IDENTITY",
        "title": "Mouse — Identity",
        "content": (
            "## Responsibilities\n"
            "- Develop performance/quality analysis tools\n"
            "- Write debugging and profiling scripts\n"
            "- Generate visualization dashboards and reports\n"
            "- Provide insights to Oracle and Neo\n\n"
            "## Communication\n"
            "- Reports to: Oracle (insights), Morpheus (progress)\n"
            "- Serves: Neo (research data), Trinity (debugging)"
        ),
    },
    # --- Merovingian ---
    {
        "super_agent_id": "sa-merovingian",
        "doc_type": "SOUL",
        "title": "Merovingian — Soul",
        "content": (
            '"Information. Information is everything. Cause and effect."\n\n'
            "Merovingian is the Knowledge Manager. He tracks codebase changes in real-time, "
            "indexes the codebase for search, and provides information to other agents."
        ),
    },
    {
        "super_agent_id": "sa-merovingian",
        "doc_type": "IDENTITY",
        "title": "Merovingian — Identity",
        "content": (
            "## Responsibilities\n"
            "- Real-time tracking of code/doc changes\n"
            "- Index codebase and support search\n"
            "- Provide information to other agents' queries\n"
            "- Analyze change history and impact\n\n"
            "## Communication\n"
            "- Serves: All agents (information provider)\n"
            "- Collaborates with: Keymaker (repo structure)"
        ),
    },
    # --- Dozer ---
    {
        "super_agent_id": "sa-dozer",
        "doc_type": "SOUL",
        "title": "Dozer — Soul",
        "content": (
            '"I carry the heavy load."\n\n'
            "Dozer is the Security Guardian (Blue Team). He reviews Red Team attack PRs, "
            "implements security patches, applies defensive coding patterns, and writes "
            "security tests."
        ),
    },
    {
        "super_agent_id": "sa-dozer",
        "doc_type": "IDENTITY",
        "title": "Dozer — Identity",
        "content": (
            "## Responsibilities\n"
            "- Review and respond to Smith/Cypher attack PRs\n"
            "- Implement security patches\n"
            "- Apply defensive coding patterns\n"
            "- Write security tests (defensive)\n"
            "- Document security guidelines\n\n"
            "## Priority Classification\n"
            "| Severity | Response |\n"
            "|----------|----------|\n"
            "| Critical | Immediate hotfix |\n"
            "| High | Same day fix |\n"
            "| Medium | Next sprint |\n"
            "| Low | When convenient |\n\n"
            "## Communication\n"
            "- Reports to: Trinity, Architect\n"
            "- Reviews: Smith, Cypher (attack PRs)\n"
            "- Collaborates with: Keymaker (secrets management)"
        ),
    },
    # --- Smith ---
    {
        "super_agent_id": "sa-smith",
        "doc_type": "SOUL",
        "title": "Smith — Soul",
        "content": (
            '"I have purpose, Mr. Anderson. To destroy you."\n\n'
            "Smith is the Test Attacker (Red Team). He finds uncovered edge cases, "
            "writes adversarial tests designed to fail, and creates PRs exposing "
            "coverage gaps and missing error handling."
        ),
    },
    {
        "super_agent_id": "sa-smith",
        "doc_type": "IDENTITY",
        "title": "Smith — Identity",
        "content": (
            "## Responsibilities\n"
            "- Find uncovered edge cases\n"
            "- Write adversarial test code\n"
            "- Create PRs with failing tests\n"
            "- Specify implementation requirements for passing tests\n\n"
            "## Attack Patterns\n"
            "- Boundary conditions\n"
            "- Null/undefined handling\n"
            "- Race conditions\n"
            "- Error paths\n"
            "- Resource limits\n\n"
            "## Communication\n"
            "- Reports to: Dozer (review), Trinity (fixes)\n"
            "- Collaborates with: Cypher (coordinated attacks)"
        ),
    },
    # --- Cypher ---
    {
        "super_agent_id": "sa-cypher",
        "doc_type": "SOUL",
        "title": "Cypher — Soul",
        "content": (
            '"Ignorance is bliss."\n\n'
            "Cypher is the Security Attacker (Red Team). He scans for OWASP Top 10 "
            "vulnerabilities, attempts authentication bypass, tests input validation, "
            "and creates attack PoC PRs exposing security weaknesses."
        ),
    },
    {
        "super_agent_id": "sa-cypher",
        "doc_type": "IDENTITY",
        "title": "Cypher — Identity",
        "content": (
            "## Responsibilities\n"
            "- Scan for security vulnerabilities (OWASP Top 10)\n"
            "- Attempt authentication/authorization bypass\n"
            "- Detect input validation vulnerabilities\n"
            "- Create attack PoC PRs exposing vulnerabilities\n"
            "- Check dependency vulnerabilities\n\n"
            "## Communication\n"
            "- Reports to: Dozer (review), Trinity (fixes)\n"
            "- Collaborates with: Smith (coordinated attacks)"
        ),
    },
]


def seed_bundled_teams_and_agents():
    """Seed bundled teams, super agents, team members, and identity documents.

    Idempotent — checks by ID before inserting. Safe to run on every startup.
    """
    with get_connection() as conn:
        # 1. Seed teams
        for team in BUNDLED_TEAMS:
            existing = conn.execute(
                "SELECT id FROM teams WHERE id = ?", (team["id"],)
            ).fetchone()
            if existing:
                continue
            conn.execute(
                "INSERT INTO teams (id, name, description, source) VALUES (?, ?, ?, ?)",
                (team["id"], team["name"], team["description"], team["source"]),
            )

        # 2. Seed super agents
        for sa in BUNDLED_SUPER_AGENTS:
            existing = conn.execute(
                "SELECT id FROM super_agents WHERE id = ?", (sa["id"],)
            ).fetchone()
            if existing:
                continue
            conn.execute(
                "INSERT INTO super_agents (id, name, description, backend_type, team_id, source) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (sa["id"], sa["name"], sa["description"], sa["backend_type"],
                 sa["team_id"], sa["source"]),
            )

        # 3. Seed team members (link super agents to teams)
        for team in BUNDLED_TEAMS:
            leader_id = team["leader_super_agent"]
            # Find all super agents in this team
            team_agents = [sa for sa in BUNDLED_SUPER_AGENTS if sa["team_id"] == team["id"]]
            for sa in team_agents:
                existing = conn.execute(
                    "SELECT id FROM team_members WHERE team_id = ? AND name = ?",
                    (team["id"], sa["name"]),
                ).fetchone()
                if existing:
                    continue
                role = "leader" if sa["id"] == leader_id else "member"
                conn.execute(
                    "INSERT INTO team_members (team_id, name, role, super_agent_id, description) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (team["id"], sa["name"], role, sa["id"], sa["description"]),
                )

        # 4. Seed identity documents
        for doc in BUNDLED_DOCUMENTS:
            existing = conn.execute(
                "SELECT id FROM super_agent_documents "
                "WHERE super_agent_id = ? AND doc_type = ?",
                (doc["super_agent_id"], doc["doc_type"]),
            ).fetchone()
            if existing:
                continue
            conn.execute(
                "INSERT INTO super_agent_documents (super_agent_id, doc_type, title, content) "
                "VALUES (?, ?, ?, ?)",
                (doc["super_agent_id"], doc["doc_type"], doc["title"], doc["content"]),
            )

        conn.commit()
        logger.info("Bundled teams and super agents seeded successfully")
```

- [ ] **Step 4: Wire seed function into app initialization**

In `backend/app/__init__.py`, add the import and call after `seed_predefined_triggers()` (line 118):

```python
from .db.bundle_seeds import seed_bundled_teams_and_agents

# In _init_database():
    init_db()
    seed_predefined_triggers()
    seed_bundled_teams_and_agents()  # Add this line
    seed_preset_mcp_servers()
```

Also add the export in `backend/app/db/__init__.py` — find the seeds import block and add:

```python
from .bundle_seeds import seed_bundled_teams_and_agents  # noqa: F401
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_bundle_seeds.py -v`
Expected: All 7 tests pass.

- [ ] **Step 6: Run full backend test suite**

Run: `cd backend && uv run pytest -v -x`
Expected: All tests pass (seed runs on every test via `isolated_db` fixture).

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/bundle_seeds.py backend/app/db/schema.py backend/app/db/migrations.py backend/app/__init__.py backend/app/db/__init__.py backend/tests/test_bundle_seeds.py
git commit -m "feat: seed bundled Matrix teams and super agents on DB init"
```

---

## Chunk 2: Project-Scoped Routing & Streaming Helper

### Task 3: Add project-scoped routing to SketchRoutingService

**Files:**
- Modify: `backend/app/services/sketch_routing_service.py:289-350`
- Create: `backend/tests/test_sketch_routing_scoped.py`

- [ ] **Step 1: Write the test file**

Create `backend/tests/test_sketch_routing_scoped.py`:

```python
"""Tests for project-scoped sketch routing."""

from app.db import get_connection, init_db
from app.db.bundle_seeds import seed_bundled_teams_and_agents
from app.services.sketch_routing_service import SketchRoutingService


def _create_project(conn, project_id="proj-test", name="Test Project"):
    """Create a test project."""
    conn.execute(
        "INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
        (project_id, name),
    )
    conn.commit()
    return project_id


def _assign_team_to_project(conn, project_id, team_id):
    """Link a team to a project."""
    conn.execute(
        "INSERT OR IGNORE INTO project_teams (project_id, team_id) VALUES (?, ?)",
        (project_id, team_id),
    )
    conn.commit()


class TestProjectScopedRouting:
    """Test routing scoped to a project's teams."""

    def test_route_without_project_id_searches_globally(self, client):
        """Backward compatible — no project_id does global search."""
        seed_bundled_teams_and_agents()
        classification = {"phase": "research", "domains": ["papers"], "complexity": "medium"}
        result = SketchRoutingService.route(classification)
        # Should find a match globally (Neo or Seraph have 'research' in description)
        assert result["target_type"] != "none"

    def test_route_with_project_id_scopes_to_project_teams(self, client):
        """Only teams assigned to the project are searched."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-dev")
            # Only assign development team
            _assign_team_to_project(conn, "proj-dev", "team-mx-development")

        classification = {"phase": "execution", "domains": ["backend"], "complexity": "medium"}
        result = SketchRoutingService.route(classification, project_id="proj-dev")
        # Should match development team or its members
        assert result["target_type"] in ("team", "super_agent")

    def test_route_with_project_id_returns_none_for_unassigned_domain(self, client):
        """Research prompt to a project with only dev team returns none."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            _create_project(conn, "proj-dev-only")
            _assign_team_to_project(conn, "proj-dev-only", "team-mx-development")

        classification = {"phase": "research", "domains": ["papers"], "complexity": "medium"}
        result = SketchRoutingService.route(classification, project_id="proj-dev-only")
        assert result["target_type"] == "none"

    def test_route_with_nonexistent_project_returns_none(self, client):
        """Project with no teams returns none."""
        classification = {"phase": "execution", "domains": ["backend"], "complexity": "medium"}
        result = SketchRoutingService.route(classification, project_id="proj-nonexistent")
        assert result["target_type"] == "none"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_sketch_routing_scoped.py -v -x`
Expected: FAIL — `route()` doesn't accept `project_id` yet.

- [ ] **Step 3: Modify route() to accept project_id**

In `backend/app/services/sketch_routing_service.py`, modify the `route()` method (line 289). Change the signature and add project-scoping logic:

```python
    @classmethod
    def route(cls, classification: dict, project_id: str = None) -> dict:
        """Route a classified sketch to a SuperAgent or team target.

        When project_id is provided, only search teams assigned to that project
        and their member super agents. Falls back to global search when None.

        Returns dict with target_type, target_id, reason.
        """
        from ..db.super_agents import get_all_super_agents
        from ..db.teams import get_all_teams
        from ..db.connection import get_connection

        phase = classification.get("phase", "")
        domains = classification.get("domains", [])

        if project_id:
            # Scoped search: only teams assigned to this project
            with get_connection() as conn:
                team_rows = conn.execute(
                    "SELECT t.* FROM teams t "
                    "JOIN project_teams pt ON t.id = pt.team_id "
                    "WHERE pt.project_id = ?",
                    (project_id,),
                ).fetchall()
                teams = [dict(r) for r in team_rows]

                if not teams:
                    return {"target_type": "none", "target_id": None,
                            "reason": "No teams assigned to this project"}

                team_ids = [t["id"] for t in teams]
                placeholders = ",".join("?" * len(team_ids))
                sa_rows = conn.execute(
                    f"SELECT sa.* FROM super_agents sa "
                    f"JOIN team_members tm ON sa.id = tm.super_agent_id "
                    f"WHERE tm.team_id IN ({placeholders})",
                    team_ids,
                ).fetchall()
                super_agents = [dict(r) for r in sa_rows]
        else:
            super_agents = get_all_super_agents()
            teams = get_all_teams()
```

Keep the rest of the method unchanged — the existing keyword matching logic works on the `super_agents` and `teams` lists regardless of how they were fetched.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_sketch_routing_scoped.py -v`
Expected: All 4 tests pass.

- [ ] **Step 5: Run full backend test suite**

Run: `cd backend && uv run pytest -v -x`
Expected: All tests pass (backward compatible).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/sketch_routing_service.py backend/tests/test_sketch_routing_scoped.py
git commit -m "feat: add project-scoped routing to SketchRoutingService"
```

---

### Task 4: Extract streaming helper from super_agent_chat.py

**Files:**
- Create: `backend/app/services/streaming_helper.py`
- Modify: `backend/app/routes/super_agent_chat.py:169-240`

- [ ] **Step 1: Create streaming_helper.py**

Create `backend/app/services/streaming_helper.py`. Extract the core streaming logic from `_launch_background_thread` in `super_agent_chat.py` (lines 169-240):

```python
"""Shared streaming helper for LLM response generation.

Extracted from super_agent_chat.py to be reusable by both the Playground
chat endpoint and the Sketch execution service.
"""

import logging
import threading
from typing import Callable, Optional

from .chat_state_service import ChatStateService
from .super_agent_session_service import SuperAgentSessionService

logger = logging.getLogger(__name__)


def run_streaming_response(
    session_id: str,
    super_agent_id: str,
    backend: str,
    account_id: Optional[str] = None,
    model: Optional[str] = None,
    on_complete: Optional[Callable] = None,
    on_error: Optional[Callable] = None,
) -> None:
    """Launch a background thread that streams an LLM response.

    Assembles system prompt, builds message history, calls stream_llm_response(),
    pushes content_delta chunks via ChatStateService (SSE), persists the
    assistant message, and updates backend last used.

    Args:
        session_id: The session to stream into.
        super_agent_id: The super agent generating the response.
        backend: LLM backend type (e.g., 'claude', 'litellm').
        account_id: Optional account for API key resolution (passed as account_email).
        model: Optional model override.
        on_complete: Called after successful completion (no args).
        on_error: Called on error with (error_message: str).
    """
    _session_id = session_id
    _super_agent_id = super_agent_id

    def _stream_response():
        try:
            from .conversation_streaming import stream_llm_response

            ChatStateService.push_status(_session_id, "streaming")

            system_prompt = SuperAgentSessionService.assemble_system_prompt(
                _super_agent_id, _session_id
            )
            # Build LLM messages: system prompt first, then conversation log
            state = SuperAgentSessionService.get_session_state(_session_id)
            llm_messages = []
            if system_prompt:
                llm_messages.append({"role": "system", "content": system_prompt})
            if state and state.get("conversation_log"):
                for msg in state["conversation_log"]:
                    llm_messages.append(
                        {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                    )

            accumulated = []
            for chunk in stream_llm_response(
                llm_messages,
                model=model,
                account_email=account_id,
                backend=backend,
            ):
                if chunk:
                    accumulated.append(chunk)
                    ChatStateService.push_delta(
                        _session_id, "content_delta", {"content": chunk}
                    )

            full_response = "".join(accumulated)
            if full_response:
                SuperAgentSessionService.add_assistant_message(
                    _session_id, full_response, backend=backend
                )
                # Track backend usage
                if backend:
                    try:
                        from ..db.backends import update_backend_last_used
                        update_backend_last_used(backend)
                    except Exception:
                        logger.error("Failed to update backend last used", exc_info=True)

            ChatStateService.push_delta(
                _session_id, "finish", {"content": full_response, "backend": backend}
            )
            ChatStateService.push_status(_session_id, "idle")

            if on_complete:
                on_complete()

        except Exception as e:
            error_msg = str(e)
            logger.exception("Streaming error for session %s", _session_id)
            try:
                ChatStateService.push_delta(
                    _session_id, "error", {"error": error_msg}
                )
                ChatStateService.push_status(_session_id, "error")
            except Exception:
                logger.exception(
                    "Failed to propagate streaming error for session %s", _session_id
                )

            if on_error:
                on_error(error_msg)

    thread = threading.Thread(target=_stream_response, daemon=True)
    thread.start()
```

- [ ] **Step 2: Refactor super_agent_chat.py to use the shared helper**

In `backend/app/routes/super_agent_chat.py`, replace `_launch_background_thread` (lines 169-240) with a call to the shared helper:

```python
from ..services.streaming_helper import run_streaming_response

def _launch_background_thread(
    session_id: str,
    super_agent_id: str,
    effective_backend: str,
    account_id: Optional[str],
    model: Optional[str],
) -> None:
    """Launch background thread for LLM streaming using shared helper."""
    run_streaming_response(
        session_id=session_id,
        super_agent_id=super_agent_id,
        backend=effective_backend,
        account_id=account_id,
        model=model,
    )
```

This keeps `_launch_background_thread` as a thin wrapper so callers don't need to change.

- [ ] **Step 3: Verify the Playground chat still works**

Run: `cd backend && uv run pytest tests/test_super_agents.py -v -x`
Expected: All tests pass. The refactor is behavioral no-op.

- [ ] **Step 4: Run full backend test suite**

Run: `cd backend && uv run pytest -v -x`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/streaming_helper.py backend/app/routes/super_agent_chat.py
git commit -m "refactor: extract streaming logic into shared streaming_helper"
```

---

### Task 5: Create sketch execution service

**Files:**
- Create: `backend/app/services/sketch_execution_service.py`
- Create: `backend/tests/test_sketch_execution.py`

- [ ] **Step 1: Write the test file**

Create `backend/tests/test_sketch_execution.py`:

```python
"""Tests for sketch execution service."""

from unittest.mock import patch, MagicMock

from app.db import get_connection
from app.db.bundle_seeds import seed_bundled_teams_and_agents
from app.services.sketch_execution_service import execute_sketch, find_team_super_agent


class TestFindTeamSuperAgent:
    """Test team → super agent resolution."""

    def test_finds_leader(self, client):
        """Returns leader super agent for a team."""
        seed_bundled_teams_and_agents()
        result = find_team_super_agent("team-mx-development")
        assert result == "sa-trinity"

    def test_finds_leader_for_research_team(self, client):
        """Returns Neo as leader of research team."""
        seed_bundled_teams_and_agents()
        result = find_team_super_agent("team-mx-research")
        assert result == "sa-neo"

    def test_returns_none_for_nonexistent_team(self, client):
        """Returns None for a team that doesn't exist."""
        result = find_team_super_agent("team-nonexistent")
        assert result is None

    def test_returns_none_for_team_without_super_agents(self, client):
        """Returns None for a team with no super agent members."""
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO teams (id, name) VALUES ('team-empty', 'Empty Team')"
            )
            conn.commit()
        result = find_team_super_agent("team-empty")
        assert result is None


class TestExecuteSketch:
    """Test sketch execution flow."""

    @patch("app.services.sketch_execution_service.run_streaming_response")
    def test_execute_sketch_sets_in_progress(self, mock_stream, client):
        """Status is set to in_progress before streaming starts."""
        seed_bundled_teams_and_agents()
        # Create a test sketch
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status) "
                "VALUES ('sk-test', 'Test', 'Hello', 'routed')"
            )
            conn.commit()

        session_id = execute_sketch("sk-test", "sa-trinity", "Hello")

        assert session_id is not None
        # Verify status was set to in_progress
        with get_connection() as conn:
            sketch = conn.execute(
                "SELECT status FROM sketches WHERE id = 'sk-test'"
            ).fetchone()
        assert sketch["status"] == "in_progress"

    @patch("app.services.sketch_execution_service.run_streaming_response")
    def test_execute_sketch_calls_streaming(self, mock_stream, client):
        """Streaming helper is called with correct args."""
        seed_bundled_teams_and_agents()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sketches (id, title, content, status) "
                "VALUES ('sk-test2', 'Test', 'Build an API', 'routed')"
            )
            conn.commit()

        execute_sketch("sk-test2", "sa-trinity", "Build an API")

        mock_stream.assert_called_once()
        call_kwargs = mock_stream.call_args
        assert call_kwargs.kwargs["super_agent_id"] == "sa-trinity"
        assert call_kwargs.kwargs["backend"] == "claude"
        assert call_kwargs.kwargs["on_complete"] is not None
        assert call_kwargs.kwargs["on_error"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_sketch_execution.py -v -x`
Expected: ImportError — module doesn't exist yet.

- [ ] **Step 3: Create sketch_execution_service.py**

Create `backend/app/services/sketch_execution_service.py`:

```python
"""Sketch execution service.

Bridges sketch routing to actual LLM execution on super agent sessions.
"""

import logging
from typing import Optional

from ..db.connection import get_connection
from ..db.sketches import update_sketch
from ..db.super_agents import get_super_agent
from .streaming_helper import run_streaming_response
from .super_agent_session_service import SuperAgentSessionService

logger = logging.getLogger(__name__)


def find_team_super_agent(team_id: str) -> Optional[str]:
    """Find the best super agent in a team. Prefers role='leader'.

    Returns super_agent_id or None if no super agent members exist.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT super_agent_id, role FROM team_members "
            "WHERE team_id = ? AND super_agent_id IS NOT NULL "
            "ORDER BY CASE WHEN role = 'leader' THEN 0 ELSE 1 END",
            (team_id,),
        ).fetchall()
    if not rows:
        return None
    return rows[0]["super_agent_id"]


def execute_sketch(sketch_id: str, super_agent_id: str, content: str) -> str:
    """Execute a routed sketch on a super agent session.

    Sets status to 'in_progress' before launching the background thread
    to prevent race conditions. Returns session_id.
    """
    # 1. Set status before launching thread
    update_sketch(sketch_id, status="in_progress")

    # 2. Resolve backend from super agent record (same pattern as _resolve_session)
    sa = get_super_agent(super_agent_id)
    backend = (sa.get("backend_type") if sa else None) or "claude"

    # 3. Get or create session
    session_id = SuperAgentSessionService.get_or_create_session(super_agent_id)

    # 4. Persist user message to session
    SuperAgentSessionService.send_message(session_id, content)

    # 5. Launch streaming with sketch status callbacks
    def _on_complete():
        update_sketch(sketch_id, status="completed")
        logger.info("Sketch %s completed successfully", sketch_id)

    def _on_error(error_msg):
        update_sketch(sketch_id, status="classified")
        logger.error("Sketch %s failed: %s", sketch_id, error_msg)

    run_streaming_response(
        session_id=session_id,
        super_agent_id=super_agent_id,
        backend=backend,
        on_complete=_on_complete,
        on_error=_on_error,
    )

    return session_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_sketch_execution.py -v`
Expected: All 6 tests pass.

- [ ] **Step 5: Run full backend test suite**

Run: `cd backend && uv run pytest -v -x`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/sketch_execution_service.py backend/tests/test_sketch_execution.py
git commit -m "feat: add sketch execution service with team resolution"
```

---

## Chunk 3: Route Endpoint Wiring & Frontend

### Task 6: Wire route_sketch endpoint to execute_sketch

**Files:**
- Modify: `backend/app/routes/sketches.py:109-131`

- [ ] **Step 1: Modify route_sketch_endpoint**

In `backend/app/routes/sketches.py`, replace the body of `route_sketch_endpoint` (lines 109-131). Add imports at the top of the file:

```python
import json
from ..services.sketch_execution_service import execute_sketch, find_team_super_agent
```

Replace the function body (keep the decorator and signature):

```python
@sketches_bp.post("/<sketch_id>/route")
def route_sketch_endpoint(path: SketchPath):
    """Route a classified sketch to a target and execute it."""
    sketch_id = path.sketch_id
    sketch = get_sketch(sketch_id)
    if not sketch:
        return {"error": "Sketch not found"}, HTTPStatus.NOT_FOUND

    classification_raw = sketch.get("classification_json")
    if not classification_raw:
        return {"error": "Sketch must be classified first"}, HTTPStatus.BAD_REQUEST

    classification = json.loads(classification_raw) if isinstance(classification_raw, str) else classification_raw

    # Route with project scoping
    routing = SketchRoutingService.route(classification, project_id=sketch.get("project_id"))

    # Resolve target super agent
    super_agent_id = None
    if routing["target_type"] == "super_agent":
        super_agent_id = routing["target_id"]
    elif routing["target_type"] == "team":
        super_agent_id = find_team_super_agent(routing["target_id"])

    if not super_agent_id:
        update_sketch(sketch_id, status="routed", routing_json=json.dumps(routing))
        return {"routing": routing}, HTTPStatus.OK

    # Execute on super agent session
    session_id = execute_sketch(sketch_id, super_agent_id, sketch["content"])

    # Store session info in routing_json for frontend
    routing["session_id"] = session_id
    routing["super_agent_id"] = super_agent_id
    update_sketch(sketch_id, routing_json=json.dumps(routing))

    return {
        "routing": routing,
        "session_id": session_id,
        "super_agent_id": super_agent_id,
    }, HTTPStatus.OK
```

- [ ] **Step 2: Run backend tests**

Run: `cd backend && uv run pytest -v -x`
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routes/sketches.py
git commit -m "feat: wire route_sketch endpoint to execute on super agent sessions"
```

---

### Task 7: Add SSE streaming to useSketchChat.ts

**Files:**
- Modify: `frontend/src/composables/useSketchChat.ts`

- [ ] **Step 0: Update sketchApi.route return type**

In `frontend/src/services/api/sketches.ts`, update the `route` function return type to include `session_id` and `super_agent_id`:

```typescript
  route: (id: string) =>
    apiFetch<{ message: string; routing: Record<string, unknown>; session_id?: string; super_agent_id?: string }>(`/admin/sketches/${id}/route`, {
      method: 'POST',
    }),
```

- [ ] **Step 1: Add SSE streaming after routing**

In `frontend/src/composables/useSketchChat.ts`, modify the `routeSketch` function (around line 118). After the route API call returns, check for `session_id` and `super_agent_id` in the response and open an SSE connection.

Add new state refs near the top (after line 25):

```typescript
const streamingContent = ref('');
const isStreaming = ref(false);
const executionSessionId = ref<string | null>(null);
const executionSuperAgentId = ref<string | null>(null);
let eventSource: AuthenticatedEventSource | null = null;
```

Add imports at the top:

```typescript
import { superAgentSessionApi } from '../services/api';
import type { AuthenticatedEventSource } from '../services/api/eventSource';
```

Modify `routeSketch` — after the existing route API call, add SSE streaming. **Important:** The SSE protocol uses a single `state_delta` event type with `data.type` for dispatch (same as the Playground chat). Do NOT use separate event names like `content_delta` — instead, listen for `state_delta` and switch on `data.type`:

```typescript
const routeSketch = async (sketchId: string) => {
  try {
    isProcessing.value = true;
    error.value = null;

    const routeResult = await sketchApi.route(sketchId);

    // Fetch updated sketch
    const updatedSketch = await sketchApi.get(sketchId);
    currentSketch.value = updatedSketch;

    // Parse routing info
    const routing = routeResult.routing || routeResult;
    const routingMsg: ConversationMessage = {
      role: 'system',
      content: `Routed to: ${routing.target_type} (${routing.target_id || 'none'})\nReason: ${routing.reason || 'N/A'}`,
      timestamp: new Date().toISOString(),
    };
    messages.value.push(routingMsg);

    // If execution started, open SSE stream
    const sessionId = routeResult.session_id;
    const superAgentId = routeResult.super_agent_id;

    if (sessionId && superAgentId) {
      executionSessionId.value = sessionId;
      executionSuperAgentId.value = superAgentId;
      streamingContent.value = '';
      isStreaming.value = true;

      // Add placeholder assistant message
      const assistantMsg: ConversationMessage = {
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
      };
      messages.value.push(assistantMsg);
      const msgIndex = messages.value.length - 1;

      // Open SSE connection (state_delta protocol — same as Playground)
      eventSource = superAgentSessionApi.chatStream(superAgentId, sessionId);
      const source = eventSource.source;

      // All events arrive as 'state_delta' with type in JSON data
      source.addEventListener('state_delta', (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data);
          switch (data.type) {
            case 'content_delta':
              streamingContent.value += data.content || '';
              messages.value[msgIndex].content = streamingContent.value;
              break;
            case 'finish':
              isStreaming.value = false;
              if (eventSource) {
                eventSource.close();
                eventSource = null;
              }
              break;
            case 'error':
              isStreaming.value = false;
              error.value = 'Streaming error occurred. You can retry by routing again.';
              if (eventSource) {
                eventSource.close();
                eventSource = null;
              }
              break;
          }
        } catch {
          // Ignore unparseable events
        }
      });

      source.onerror = () => {
        if (isStreaming.value) {
          isStreaming.value = false;
          error.value = 'Connection lost. You can retry by routing again.';
          if (eventSource) {
            eventSource.close();
            eventSource = null;
          }
        }
      };
    } else if (routing.target_type === 'none') {
      messages.value.push({
        role: 'system',
        content: 'No matching agent found. Assign a team with super agents to this project first.',
        timestamp: new Date().toISOString(),
      });
    }
  } catch (err: any) {
    error.value = err.message || 'Failed to route sketch';
  } finally {
    isProcessing.value = false;
  }
};
```

Update the return object to expose new state:

```typescript
return {
  sketches,
  currentSketch,
  selectedProjectId,
  projects,
  isProcessing,
  isStreaming,
  messages,
  error,
  streamingContent,
  executionSessionId,
  executionSuperAgentId,
  loadProjects,
  loadSketches,
  submitSketch,
  routeSketch,
  selectSketch,
  clearChat,
};
```

- [ ] **Step 2: Run frontend tests**

Run: `cd frontend && npm run test:run`
Expected: Existing tests pass (or adjust if sketch tests exist).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/composables/useSketchChat.ts
git commit -m "feat: add SSE streaming to sketch chat after routing"
```

---

### Task 8: Update SketchChatPage.vue with streaming UI

**Files:**
- Modify: `frontend/src/views/SketchChatPage.vue`

- [ ] **Step 1: Add streaming state and Continue in Playground link**

In `frontend/src/views/SketchChatPage.vue`:

1. Destructure new state from the composable (in the `<script setup>` section):

```typescript
const {
  sketches, currentSketch, selectedProjectId, projects,
  isProcessing, isStreaming, messages, error,
  streamingContent, executionSessionId, executionSuperAgentId,
  loadProjects, loadSketches, submitSketch, routeSketch, selectSketch, clearChat,
} = useSketchChat();
```

2. Add a computed property for the playground link:

```typescript
const playgroundLink = computed(() => {
  if (executionSuperAgentId.value) {
    return `/super-agents/${executionSuperAgentId.value}/playground`;
  }
  return null;
});
```

3. In the template, after the chat panel area, add the "Continue in Playground" link. Find the results/info panel section and add:

```html
<!-- Continue in Playground link -->
<div v-if="playgroundLink && currentSketch?.status === 'completed'" class="continue-link">
  <router-link :to="playgroundLink" class="playground-btn">
    Continue in Playground →
  </router-link>
</div>
```

4. Add the "Bundled" badge for teams/agents if the source data is available. In the routing results display, show the super agent name with badge:

```html
<span v-if="routing?.super_agent_id" class="badge bundled" title="Bundled Example">
  Bundled
</span>
```

5. Add minimal CSS for the new elements:

```css
.continue-link {
  padding: 12px 16px;
  border-top: 1px solid var(--color-border);
}

.playground-btn {
  display: inline-block;
  padding: 8px 16px;
  background: var(--color-primary, #00d4ff);
  color: var(--color-bg, #0a0a0a);
  border-radius: 6px;
  text-decoration: none;
  font-weight: 600;
  font-size: 0.85rem;
}

.playground-btn:hover {
  opacity: 0.9;
}

.badge.bundled {
  display: inline-block;
  padding: 2px 6px;
  background: var(--color-border, #333);
  color: var(--color-text-muted, #888);
  border-radius: 4px;
  font-size: 0.7rem;
  margin-left: 6px;
}
```

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no type errors.

- [ ] **Step 3: Run frontend tests**

Run: `cd frontend && npm run test:run`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/SketchChatPage.vue
git commit -m "feat: add streaming response UI and Continue in Playground link"
```

---

### Task 9: Final verification

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && uv run pytest -v`
Expected: All tests pass.

- [ ] **Step 2: Run full frontend build + tests**

Run: `cd frontend && npm run build && npm run test:run`
Expected: Both pass with zero errors.

- [ ] **Step 3: Format backend code**

Run: `cd backend && uv run ruff format .`

- [ ] **Step 4: Final commit if formatting changed**

```bash
git add -A && git commit -m "chore: ruff format"
```
