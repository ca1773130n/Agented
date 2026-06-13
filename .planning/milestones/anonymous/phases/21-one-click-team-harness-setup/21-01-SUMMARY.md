---
phase: 21-one-click-team-harness-setup
plan: 01
subsystem: backend-persistence
tags: [migration, projects, harness-setup, idempotency]
requires: []
provides:
  - "projects.harness_setup_status column (TEXT DEFAULT 'none')"
  - "harness_setup_steps table (PK project_id,step_key)"
  - "get/set_harness_setup_status helpers"
  - "upsert_harness_setup_step + get_harness_setup_steps helpers"
  - "GrdPlanningService.get_harness_setup_status classmethod"
affects:
  - "every downstream Phase 21 plan (service skeleton, step groups, route, dashboard)"
tech-stack:
  added: []
  patterns:
    - "PRAGMA-guarded idempotent migration (mirrors v05 grd_init_status)"
    - "ON CONFLICT upsert for per-step idempotency"
    - "NULL→'none' status coalescing (mirrors get_init_status)"
key-files:
  created:
    - backend/tests/test_harness_setup_status_migration.py
  modified:
    - backend/app/db/migrations/v07_features.py
    - backend/app/db/projects.py
    - backend/app/services/grd_planning_service.py
decisions:
  - "get/set_harness_setup_status + step helpers live module-level in projects.py (tests + downstream import there); a thin GrdPlanningService.get_harness_setup_status classmethod added for parity with get_init_status"
  - "upsert_harness_setup_step writes ISO-8601 UTC updated_at in Python (matches project_autonomy_config upsert convention)"
  - "Migration 159 used (highest existing = 158); copied PRAGMA-guard from v05_features.py:38, NOT v07:1181 per plan AVOID note"
metrics:
  tasks: 2
  files: 4
  completed: 2026-06-13
---

# Phase 21 Plan 01: Harness Setup Persistence Floor Summary

PRAGMA-guarded migration 159 adds `projects.harness_setup_status` (default
'none') and a `harness_setup_steps` table (PK project_id,step_key), plus the
status read/write + idempotent step-upsert helpers that every later Phase 21
plan depends on. All S1/S2 sanity tests green.

## What Was Built

- **Task 1 — Migration 159** (`v07_features.py`): `_migrate_159_harness_setup`
  mirrors the `_migrate_v54_project_grd_init_status` PRAGMA-guard. Adds the
  status column only if absent; creates `harness_setup_steps` via
  `CREATE TABLE IF NOT EXISTS`. Double-apply is a pure no-op. Registered in
  `V07_MIGRATIONS` as `(159, "harness_setup", ...)`.
- **Task 2 — Helpers + tests (TDD)** (`projects.py`, `grd_planning_service.py`,
  new test file): `update_project` gains a `harness_setup_status` kwarg;
  `get_harness_setup_status` coalesces NULL→'none'; `set_harness_setup_status`
  round-trips; `upsert_harness_setup_step` is idempotent via
  `ON CONFLICT(project_id, step_key) DO UPDATE`; `get_harness_setup_steps`
  reads the rows. A parity classmethod was added to `GrdPlanningService`.

## Deviations from Plan

None - plan executed exactly as written.

## Experiment Results

### Results

| Metric | Target | Achieved | Status |
|--------|--------|----------|--------|
| S1: migration schema + double-apply no-op | all green | 4/4 tests pass | PASS |
| S2: get_harness_setup_status defaults 'none' | PASS | PASS | PASS |
| S5 prereq: ruff check touched modules | clean | clean | PASS |

### Analysis

Migration schema, PK, and idempotency verified; status helper coerces NULL
correctly; step upsert produces exactly one row with latest-write-wins. Ruff
check + format clean on all touched modules.

### Artifacts

- Test file: `backend/tests/test_harness_setup_status_migration.py`

## Commits

- dd4faf9863: feat(21-01) migration 159 column + steps table
- 680aa084d3: test(21-01) failing S1/S2 tests (RED)
- c0132249a7: feat(21-01) status helpers + step upsert (GREEN)

## Self-Check: PASSED

All 4 files exist on disk; all 3 commit hashes present in git log.
