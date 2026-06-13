---
phase: 21-one-click-team-harness-setup
plan: 03
subsystem: backend/services
tags: [harness-setup, grd, team-topology, driver, idempotency]
requires: ["21-02"]
provides: ["_step_grd_init", "_step_team_topology"]
affects: ["backend/app/services/team_harness_setup_service.py"]
tech-stack:
  patterns: ["existence-check-before-create", "post-create-driver-reconcile", "mtime-fingerprint-skip"]
key-files:
  modified:
    - backend/app/services/team_harness_setup_service.py
    - backend/tests/test_team_harness_setup_service.py
decisions:
  - "Post-create update(driver='grd') per SA instance (Open Question 2: change kept local to phase 21; create_team_instances takes no driver kwarg)"
  - "Driver reconciled on BOTH create and skip paths so re-runs converge to driver=grd"
  - "grd_init triggers auto_init_project (fire-and-forget); real completion deferred to D1 dogfood"
metrics:
  tasks: 2
  duration: ~15m
  completed: 2026-06-13
---

# Phase 21 Plan 03: GRD-init reconcile + team topology (driver=grd) Summary

Implemented the first two `TeamHarnessSetupService` step bodies — idempotent GRD-init reconcile and team-topology SA-instance creation tagged `driver='grd'` for Phase-19 routing — replacing the wave-1 placeholders.

## Tasks Completed

- **Task 1 — `_step_grd_init`** (`97236aa5d7`): Resolves `local_path` from `get_project`; if `<local_path>/.planning/` exists returns `skipped` with an mtime fingerprint (never re-inits — SC4); else lazily imports and calls `GrdPlanningService.auto_init_project` (background) and returns `ok` ("init triggered"). Raises on missing project/local_path (hard failure per contract).
- **Task 2 — `_step_team_topology` + tests** (`92018ca08a`): Resolves `owner_team_id`; EXISTENCE-CHECKS `get_project_sa_instances_for_project` first (pitfall 1 — SA creation is the one non-constraint-deduped step); only calls `InstanceService.create_team_instances` when none exist. For every instance (create or skip path) post-updates `driver='grd'` via `update_project_sa_instance` (pitfall 2 + Open Question 2) and converges re-runs. Returns `ok`/`skipped` with instance count.

## Deviations from Plan

**1. [Rule 1 - Test] Pinned `test_placeholder_dispatch_runs_ready` to no-op dispatch**
- **Found during:** Task 1
- **Issue:** The 21-02 skeleton test ran the full `setup()` over the *placeholder* bodies, which were side-effect-free. The new real `_step_grd_init` requires `local_path` and `_step_team_topology` requires `owner_team_id`, so the bare `create_project(name=...)` made grd_init raise → `failed`.
- **Fix:** `monkeypatch.setattr(_STEP_FUNCS, _all_ok_funcs())` in that test — its intent is orchestration shape, not the real bodies (which now have dedicated tests). No production behavior changed.
- **Files modified:** backend/tests/test_team_harness_setup_service.py
- **Commit:** 92018ca08a

## Experiment Results

### Results

| Check | Target | Achieved | Status |
|-------|--------|----------|--------|
| S4 (driver=grd) | `get_instance_driver(id)=='grd'` for all SA instances | 2/2 instances == 'grd' | PASS |
| P1 (idempotency) | re-run produces zero duplicate rows | count 2 → 2 (skipped) | PASS |
| grd_init reconcile | skip when .planning/ exists, no re-init | skipped, 0 triggers | PASS |

`tests/test_team_harness_setup_service.py`: 11 passed. `tests/test_instance_service.py`: 37 passed (regression clean).

## Self-Check: PASSED

- FOUND: backend/app/services/team_harness_setup_service.py (`_step_grd_init`, `_step_team_topology`)
- FOUND: backend/tests/test_team_harness_setup_service.py (driver + idempotent tests)
- FOUND commit: 97236aa5d7
- FOUND commit: 92018ca08a
