---
phase: 17-forge-creation-surface
plan: 06
subsystem: backend/forge
tags: [forge, forge-creator, seed, session-import, provenance, security-gate, house-gates]
requires:
  - "17-02 create_subagent + VALID_FORGE_BINDING_KINDS"
  - "17-03 forge_bundles + add_bundle_item (migration 156)"
  - "17-04 subagent materialize write branch + forge manifest"
  - "17-05 create_and_bind_and_materialize atomic API"
provides:
  - "forge-creator default bundle: 5 global-scope creator skills, idempotent startup seed"
  - "forge_origin provenance table (migration 157): sha256 + source session id"
  - "on_session_complete_import: 4th session-bus handler, session_kind-gated auto-import"
affects:
  - backend/app/forge_seeds/forge-creator/*/SKILL.md
  - backend/app/services/forge_creator_seed.py
  - backend/app/services/forge_session_import.py
  - backend/app/db/forge_origin.py
  - backend/app/db/migrations/v07_features.py
  - backend/app_litestar/lifecycle.py
tech-stack:
  added: []
  patterns:
    - "Idempotent seed mirrors predefined-bot pattern: every step guarded on existence (skill name, bundle name, bundle item) so re-run is a pure no-op"
    - "Global scope expressed via forge_bundles.scope='global'; user_skills is inherently global (no project_id column) so no sentinel needed (Open Q2)"
    - "Security gate fails CLOSED and runs FIRST: only an allowlisted session_kind set auto-imports; unknown/foreign kinds import nothing"
    - "Provenance keyed on stable subagent NAME (not the per-create db id) so the sha256 idempotence check and the recorded origin row agree"
    - "Materialized import becomes manifest-tracked, so a second pass skips it as forge-owned — natural idempotence on re-run"
key-files:
  created:
    - backend/app/forge_seeds/forge-creator/skill-creator/SKILL.md
    - backend/app/forge_seeds/forge-creator/rule-creator/SKILL.md
    - backend/app/forge_seeds/forge-creator/hook-creator/SKILL.md
    - backend/app/forge_seeds/forge-creator/command-creator/SKILL.md
    - backend/app/forge_seeds/forge-creator/subagent-creator/SKILL.md
    - backend/app/services/forge_creator_seed.py
    - backend/app/services/forge_session_import.py
    - backend/app/db/forge_origin.py
    - backend/tests/test_forge_creator_seed.py
    - backend/tests/test_forge_session_import.py
  modified:
    - backend/app/db/migrations/v07_features.py
    - backend/app/db/__init__.py
    - backend/app_litestar/lifecycle.py
decisions:
  - "Open Q2 (global scope): user_skills has no project_id, so creator skills are inherently global; the bundle carries scope='global'. No schema change, no sentinel project_id."
  - "Open Q1 (Agented-driven set): {project_session, super_agent, team_session, goal_loop}. Every other / unknown kind (notably external clone-import) is FOREIGN and imports nothing."
  - "Phase-17 import scope = subagents only (.claude/agents/*.md) — the kind the 17-05 atomic API supports create+bind+materialize end-to-end. Rule/command/hook session-import deferred; diff helper is kind-agnostic."
  - "Provenance keyed on subagent name (stable) rather than db id (changes each create) so idempotence lookup matches the recorded row."
metrics:
  duration: ~13m
  completed: 2026-06-13
  tasks: 4
  files: 13
---

# Phase 17 Plan 06: forge-creator Bundle + Gated Session Auto-Import Summary

Shipped the two halves of phase success criterion #5 plus the phase house-gate
closer. (a) A `forge-creator` default bundle: five agentskills.io-compatible
creator skills (skill/rule/hook/command/subagent-creator), seeded idempotently
at startup at global scope. (b) A fourth session-completion handler on the
`execution_events` bus that diffs `.claude/` against the forge manifest and
auto-imports session-scaffolded subagents via the 17-05 atomic API, recording
sha256 + source-session-id provenance in a new `forge_origin` table — gated so
only Agented-driven sessions auto-bind (fail-closed on foreign/unknown kinds,
the Phase 17 prompt-injection mitigation).

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | 5 SKILL.md seeds + idempotent forge-creator bundle | b687cf7308 | forge_seeds/forge-creator/*, forge_creator_seed.py |
| 2 | forge_origin (mig 157) + gated import handler + lifecycle wiring | 3f291b7f86 | v07_features.py, forge_origin.py, db/__init__.py, forge_session_import.py, lifecycle.py |
| 3 | seed idempotence + gated session-import provenance tests | 91b9483ac4 | tests/test_forge_creator_seed.py, tests/test_forge_session_import.py |
| 4 | verify phase 17 house gates | e105c756ca | (empty marker) |

## Key Decisions Recorded (Open Questions)

- **Open Q2 — global scope:** `user_skills` has no `project_id` column, so a
  user skill is inherently global. "Global" is therefore expressed with NO
  sentinel project_id on the skill side, and the bundle itself is tagged
  `scope='global'` (the enum `forge_bundles.scope` already supports it alongside
  `'project'`). No schema change.
- **Open Q1 — Agented-driven session_kind set:**
  `{project_session, super_agent, team_session, goal_loop}`. These auto-bind.
  ANY other value — explicitly including external clone-import, plus any
  unknown/unrecognized kind — is FOREIGN and imports nothing.

## Security Gate (House Rule)

`on_session_complete_import` checks `session_kind` FIRST, before touching the
filesystem, and returns immediately for anything outside
`AGENTED_DRIVEN_SESSION_KINDS`. This is the Phase 17 mitigation for the
prompt-injection surface that auto-imported `.claude/` content represents across
four harnesses. Verified fail-closed by `test_foreign_session_does_not_import`
(external clone-import) and `test_unknown_kind_fails_closed` (unrecognized kind):
both import zero subagents and write zero `forge_origin` rows. The whole handler
is additionally wrapped in its own try/except so an import error can never break
session completion or the other three session handlers.

## Deviations from Plan

None functional — plan executed as written. Minor in-flight notes:
- Touched-suite filenames in the Task 4 command were approximate; resolved to
  the actual files (`test_forge_bundles_db.py`, `test_subagents_db.py`, etc.).
- Reverted two incidental working-tree changes that `uv run`/ruff produced
  outside this plan's scope (a cosmetic decorator reflow in the 17-05
  `project_forge_bindings.py` and a `uv.lock` touch) to keep commits scoped.

## Experiment Results

### Results

| Metric | Baseline | Target | Achieved | Status |
|--------|----------|--------|----------|--------|
| seed produces 5 skills + 1 global bundle + 5 items | no bundle | exactly 5/1/5 | 5/1/5 | PASS |
| seed idempotent (2nd call no-op) | n/a | no duplicates | same state, created=False | PASS |
| Agented session imports subagent + records sha256/session-id | no handler | imported + origin row | foo-reviewer bound, hash+sess-abc123 recorded | PASS |
| operator file (settings.json) NOT imported | n/a | ignored | only 1 subagent | PASS |
| foreign session imports nothing (gate fail-closed) | n/a | 0 imports | 0 subagents, 0 origin | PASS |
| unknown kind fails closed | n/a | 0 imports | 0 subagents | PASS |
| import idempotent (2nd identical call) | n/a | no new rows | 1 subagent, origin still sess-1 | PASS |

### Analysis

The idempotence-on-reimport behavior is subtle and correct: the first import
materializes the subagent to `.claude/agents/<name>.md` WITH manifest markers,
adding it to the forge manifest. On a second pass the file is now
manifest-tracked, so the diff classifies it as forge-owned and skips it — the
origin row keeps its original session id (`sess-1`). The content-hash check is
the belt; the manifest-membership check is the suspenders.

### Artifacts

- Seeds: `backend/app/forge_seeds/forge-creator/*/SKILL.md` (5 files)
- Seed service: `backend/app/services/forge_creator_seed.py`
- Import handler: `backend/app/services/forge_session_import.py`
- Provenance: `backend/app/db/forge_origin.py` (migration 157)
- Tests: `backend/tests/test_forge_creator_seed.py`,
  `backend/tests/test_forge_session_import.py`

## House Gates (Phase 17 success criterion #6)

- **Backend touched suites:** `test_forge_bundles_db.py test_subagents_db.py
  test_forge_materialization.py test_prompt_renderer.py
  test_forge_replace_for_project.py test_forge_round_wiring.py
  test_forge_skill_dispatch.py test_forge_git_commit.py
  routes/test_forge_bindings_routes.py test_forge_creator_seed.py
  test_forge_session_import.py` → **84 passed**. Substitution disclosure: the
  full serial suite was NOT run (the known ~40-48% hang); instead the
  comprehensive targeted set above (all forge/subagent/prompt suites touched by
  the phase) plus execution/streaming/events regressions
  (`test_execution_events.py test_execution_service.py
  test_litestar_executions.py test_litestar_streams.py
  test_conversation_streaming_tool_use.py` → **90 passed**) was run. Combined:
  **174 passed, 0 failed**.
- **Frontend (`cd frontend && npm run test:run`):** **1480 passed, 7 failed** —
  the 7 are exactly the known pre-existing baseline (MarkdownContent x4,
  RateLimitGauge, WorkingMemoryView, useTourMachine). **0 NEW failures** → gate
  PASS.
- **`just build` (vue-tsc + vite):** FAILS on a single pre-existing TS error in
  `frontend/src/views/dashboards/cards/AnswerGroundednessCard.vue` (`EmptyState`
  invoked with `message`/`hint` but the component requires `title`). Confirmed
  present on `main` and introduced by the unrelated agentic-RAG PR #212. Phase
  17 (all six plans) touched ZERO frontend files (`git diff --stat HEAD~4 --
  frontend/` is empty), so this is NOT a regression from this plan. Flagging it
  for a follow-up frontend fix; backend changes type-check and run clean.

## Verification

- Level 1 (Sanity): 5 SKILL.md present with parseable frontmatter; `forge_origin`
  table created at init; all modules import; `lifecycle.py` imports clean; ruff
  clean on all new/modified backend files.
- Level 2 (Proxy): `pytest tests/test_forge_creator_seed.py
  tests/test_forge_session_import.py` → **6 passed**.
- Level 3 (Deferred — DEFER-17-02): dogfood ≥3 real Agented-driven sessions that
  scaffold `.claude/` primitives through the handler before declaring fully done;
  confirm the gate fires on real `session_kind` values.

## Self-Check: PASSED
