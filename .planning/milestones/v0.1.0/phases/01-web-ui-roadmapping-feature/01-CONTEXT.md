---
phase: "01"
name: "Web UI Roadmapping Feature"
created: 2026-02-26
---

# Phase 1: Web UI Roadmapping Feature — Context

## Phase Boundary

Build full GRD project planning functionality into the web UI. Users can create roadmaps, milestones, requirements, and phases through AI-assisted interaction in the browser. This phase covers planning commands only — execution commands (execute-phase, autopilot, evolve, progress) belong on the existing Management page.

## Implementation Decisions

### AI Interaction Model

- **Reuse existing PTY session + InteractiveSetup pattern.** GRD commands are AI-powered (Claude Code with GRD plugin). The backend spins up a PTY session running Claude Code in the project's cloned repo directory, and the web UI reflects that session via SSE streaming.
- **InteractiveSetup.vue already implements the full pattern:** SSE log streaming (`log` events), structured question prompts (`question` events with options/multiselect), answer submission (`setupApi.respond()`), and completion handling.
- **The web UI must show:** AI conversation output, AskUserQuestion-style option selection widgets, and free-text input for detailed answers.
- **Existing infrastructure:** `setupApi` (frontend), PTY session services (backend), SSE streaming — all reusable.

### GRD Integration Approach

- **No reimplementation of GRD logic in Python.** GRD commands execute within an AI session (Claude Code + GRD plugin). The backend creates a PTY session that runs Claude Code in the project's cloned repo directory with the appropriate GRD skill invocation.
- **The AI session is the runtime.** `grd-tools.js` is called by the AI within the session, not by the backend directly. The backend only manages session lifecycle.
- **The web UI reflects the session** — conversation, tool calls, questions, and answers — through the existing SSE protocol.

### Scope / MVP

**Auto on project creation (background):**
- `grd:map-codebase` runs automatically after git clone
- `grd:new-project --auto @README.md` runs automatically after map-codebase
- Runs in background thread; user is notified on completion
- `GrdSyncService` does a one-time sync at this point to import any existing `.planning/` files from the repo into the DB

**Planning page (new dedicated page):**
- All planning-related GRD commands available: `new-milestone`, `complete-milestone`, `add-phase`, `remove-phase`, `insert-phase`, `discuss-phase`, `plan-phase`, `long-term-roadmap`, `survey`, `deep-dive`, `feasibility`, `assess-baseline`, `compare-methods`, `list-phase-assumptions`, `plan-milestone-gaps`, `requirement`, `map-codebase`
- Core visualization: `MilestoneOverview.vue` moved, reused, and extended
- Entry point: "Planning" button on project dashboard, placed left of the existing "Management" button

**Settings page:**
- GRD settings in a new tab on the existing Settings page

**Management page (existing):**
- Execution commands: `execute-phase`, `autopilot`, `evolve`, `progress`, `quick`, `verify-phase`, `verify-work`

### Data Model & Persistence

- **Source of truth:** `.planning/` files on disk in the project's cloned repo directory
- **DB sync:** One-time sync on project creation (import existing `.planning/` from repo). After that, all modifications go through web UI → AI session → writes files → backend syncs to DB on session completion.
- **No periodic GRD sync needed.** The 30-min scheduler job for GRD sync is unnecessary for projects managed through the web UI. Only needed for the initial import case.
- **Real-time UI updates:** PTY session completion fires an event via SSE. Backend syncs `.planning/` files to DB at that point. Frontend refreshes Planning page state on receiving the completion event. No polling.

### Navigation & Layout

- Planning page is project-scoped — accessed from within a project's context
- Every GRD planning project is tied 1:1 to an Agented project (GitHub repo based)
- Planning page is separate from the Project Management page (which handles agent task execution)

## Claude's Discretion

- Specific UI layout of the Planning page (command palette, sidebar actions, etc.)
- How to organize the planning commands in the UI (grouped by workflow stage, alphabetical, etc.)
- Whether to show a command palette or action buttons for GRD commands
- How to extend `MilestoneOverview.vue` for the new context

## Specific Ideas

- The Planning page could have a split layout: MilestoneOverview on the left, AI session panel on the right (similar to how SuperAgentPlayground works)
- GRD commands could be triggered via buttons/actions on the milestone/phase cards in MilestoneOverview
- The auto-initialization notification could link directly to the Planning page

## Deferred Ideas

- Execution commands on Planning page (deliberately excluded — belongs on Management page)
- Bidirectional file sync (not needed — web UI is the single writer after initial import)
- Custom visualization beyond MilestoneOverview (extend later based on usage)
