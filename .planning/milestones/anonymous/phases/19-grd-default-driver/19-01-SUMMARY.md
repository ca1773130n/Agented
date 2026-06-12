---
phase: 19-grd-default-driver
plan: 01
subsystem: backend/execution-routing
tags: [driver-resolution, migration, precedence, degrade-safe]
requires: []
provides:
  - "backend/app/services/cli_agent_runner_service.py:resolve_execution_driver"
  - "backend/app/db/migrations/v07_features.py:_migrate_158_driver_columns"
  - "projects.default_driver"
  - "project_sa_instances.driver"
  - "backend/app/db/projects.py:get_project_default_driver"
  - "backend/app/db/project_sa_instances.py:get_instance_driver"
affects:
  - "backend/app/services/cli_agent_runner_service.py:should_route_via_cli_agent (sibling; untouched)"
tech-stack:
  added: []
  patterns:
    - "PRAGMA-guarded idempotent ALTER (mirrors _migrate_141_projects_tesserae)"
    - "precedence resolver with injectable degrade callables for unit-testability"
    - "defensive try/except per DB read → degrade toward legacy choice, never raise"
key-files:
  created: []
  modified:
    - backend/app/db/migrations/v07_features.py
    - backend/app/db/projects.py
    - backend/app/db/project_sa_instances.py
    - backend/app/services/cli_agent_runner_service.py
    - backend/tests/test_cli_agent_runner.py
decisions:
  - "resolve_execution_driver is additive beside should_route_via_cli_agent; callers migrate in 19-04"
  - "NULL driver columns = inherit next precedence level (ultimately global 'grd')"
  - "degrade requires BOTH grd binary available AND workspace resolvable; either failing → cli_agent"
  - "GrdCliService.available is a classmethod, resolve_working_directory a staticmethod — passed as bound callables"
metrics:
  duration: "~16min"
  completed: 2026-06-13
  tasks: 3
  files: 5
---

# Phase 19 Plan 01: Driver Spine Foundation Summary

Pure precedence-driven `resolve_execution_driver()` plus migration 158 and DB
accessors — the unit-testable heart of Phase 19's default-GRD routing, with a
degrade-safe path that silently falls back to `cli_agent` when GRD is
unavailable and never crashes the turn on a read failure.

## What Was Built

- **Migration 158** (`_migrate_158_driver_columns`): PRAGMA-guarded, idempotent
  ALTERs adding `projects.default_driver` and `project_sa_instances.driver`
  (nullable TEXT, NULL = inherit). Registered as
  `(158, "driver_columns", _migrate_158_driver_columns)` in `V07_MIGRATIONS`.
- **DB accessors**: `get_project_default_driver(project_id)` and
  `get_instance_driver(instance_id)` (raw SQLite, return stored value or None).
  `driver` threaded through `create_project_sa_instance` /
  `update_project_sa_instance` so the value round-trips.
- **`resolve_execution_driver()`**: precedence turn → SuperAgent
  `config_json.driver` → instance → project default → global `"grd"`, normalized
  to `{cliproxy, cli_agent, grd}`. Non-CLI backends → `cliproxy`. Degrade
  `grd → cli_agent` via injectable `_grd_available` / `_resolve_workspace`.
  Outer guard returns the legacy choice on any unexpected exception.
- **Tests**: 12 new cases covering every precedence level, legacy boolean
  mapping, non-CLI backend, both degrade triggers, and read/total-failure
  safety. Full `test_cli_agent_runner.py` = 50 passed.

## Deviations from Plan

None — plan executed exactly as written.

## Verification

- Level 1 (Sanity): resolver imports; migration registered (`assert any(t[0]==158 ...)`);
  `test_cli_agent_runner.py` → 50 passed.
- Migration applied implicitly via `isolated_db` (`init_db()`) so the precedence
  tests exercise the real columns under a temp DB.

## Self-Check: PASSED

- Files: all 5 modified files present.
- Commits: c8256be (mig+accessors), d1a3dee (resolver), c985f76 (tests) — all in log.
- Tests: 50 passed.
