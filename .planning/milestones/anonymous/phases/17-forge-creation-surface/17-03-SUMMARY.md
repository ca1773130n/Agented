---
phase: 17-forge-creation-surface
plan: 03
subsystem: backend/forge
tags: [sqlite, migration, forge, bundles, cross-kind]
requires: []
provides:
  - "forge_bundles + forge_bundle_items cross-kind grouping tables (migration 156)"
  - "conn-accepting _add_binding for atomic cross-kind bundle-bind (foundation for 17-05 route)"
affects:
  - backend/app/db/migrations/v07_features.py
  - backend/app/db/forge_bundles.py
  - backend/app/db/__init__.py
tech-stack:
  added: []
  patterns:
    - "conn-accepting internal _add_binding mirrors add_binding's upsert but neither opens nor commits, so a bundle-bind loop binds every item in ONE get_connection() transaction"
    - "Whitespace-normalized sqlite_master DDL guard pins a legacy table byte-for-byte"
key-files:
  created:
    - backend/app/db/forge_bundles.py
    - backend/tests/test_forge_bundles_db.py
  modified:
    - backend/app/db/migrations/v07_features.py
    - backend/app/db/__init__.py
decisions:
  - "Used migration 156 as the plan specified; 155 left reserved for 17-02 subagents (not yet executed — 154 was the highest existing)"
  - "No bundle-bind route stub added — the bundle-bind route is explicitly 17-05; the 3-task plan body only covers migration + DB module + test"
  - "_add_binding carries conflict_policy explicitly (10-column upsert) for full provenance parity with 17-01's replace_for_project, vs add_binding which relies on the column DEFAULT"
  - "delete_forge_bundle does an explicit item DELETE in addition to ON DELETE CASCADE as belt-and-suspenders (PRAGMA foreign_keys is ON in get_connection)"
metrics:
  duration: 9min
  completed: 2026-06-13
---

# Phase 17 Plan 03: Cross-Kind Forge Bundles Summary

Added a cross-kind grouping primitive to the Forge: `forge_bundles` (named,
scope-tagged group) + `forge_bundle_items(bundle_id, kind, asset_id, position)`
that holds primitives of ANY kind in one bundle — unlike the skills-only legacy
`skill_sets`. Provided a conn-accepting `_add_binding(conn, ...)` so a future
bundle-bind endpoint (17-05) can bind every item of any kind in one transaction
atomically. The legacy `skill_sets` DDL is pinned byte-for-byte unchanged.

## Migration number used

**156** (`_migrate_156_forge_bundles`). Highest pre-existing was 154; 155 is
reserved for 17-02 (subagents, not yet executed). 17-03 owns 156 per plan.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | migration 156 forge_bundles + forge_bundle_items | 9309cbebbb | backend/app/db/migrations/v07_features.py |
| 2 | forge_bundles CRUD + conn-accepting _add_binding | d0af6594da | backend/app/db/forge_bundles.py, backend/app/db/__init__.py |
| 3 | cross-kind bundle CRUD + skill_sets-unchanged guard | a47bffd2e7 | backend/tests/test_forge_bundles_db.py |

## What Changed

- **Migration 156**: `forge_bundles(id PK 'bundle-' prefix, name UNIQUE, description,
  scope DEFAULT 'project', created_at)` + `forge_bundle_items(bundle_id, kind,
  asset_id, position, PK(bundle_id,kind,asset_id), FK→forge_bundles ON DELETE
  CASCADE)` + index on `(bundle_id, position)`. Idempotent CREATE IF NOT EXISTS.
  skill_sets/skill_set_items untouched.
- **forge_bundles.py**: `create_forge_bundle`, `get_forge_bundle`,
  `get_forge_bundle_by_name`, `list_forge_bundles(scope)`, `delete_forge_bundle`,
  `add_bundle_item` (kind validated against `VALID_KINDS`, auto-position),
  `list_forge_bundle_items` (ordered by position). Plus internal
  `_add_binding(conn, ...)` — same upsert SQL as `project_forge_bindings.add_binding`
  but conn-accepting (no open/commit), carrying all four provenance columns +
  conflict_policy. Comment marks the two must-stay-in-sync (RESEARCH Open Q3).
- **db/__init__.py**: re-exported the public bundle CRUD in the forge block.

## Deviations from Plan

### Auto-fixed Issues

None — no bugs or blocking issues encountered.

### Notes (not deviations)

- The plan frontmatter listed `backend/app_litestar/routes/project_forge_bindings.py`
  as a possible touched file ("stub bundle-bind route wiring" in the objective prose),
  but the 3-task plan body does NOT include a route task and the bundle-bind ROUTE is
  explicitly deferred to 17-05. No route file was modified — `_add_binding` is the
  foundation 17-05 will consume.

## Experiment Results

### Results

| Metric | Baseline | Target | Achieved | Status |
|--------|----------|--------|----------|--------|
| cross-kind bundle round-trip + ordered items | no bundle tables | binds cross-kind in one structure | 3 kinds round-trip ordered by position | PASS |
| skill_sets DDL unchanged | n/a | byte-for-byte | normalized DDL matches migration-87 | PASS |
| delete cascades items | n/a | no orphans | 0 orphan rows after delete | PASS |

### Analysis

A single bundle held skill + command + rule items and `list_forge_bundle_items`
returned them ordered by position (cmd-bbb@0, skill-aaa@1, rule-ccc@2),
demonstrating the cross-kind grouping skill_sets cannot express. The
skill_sets guard reads the live `sqlite_master.sql` and compares it
(whitespace-normalized, IF-NOT-EXISTS stripped) to the migration-87 DDL — green,
confirming success criterion #4. The conn-accepting `_add_binding` is the
atomicity foundation for the 17-05 bundle-bind route.

### Artifacts

- DB module: `backend/app/db/forge_bundles.py`
- Test: `backend/tests/test_forge_bundles_db.py` (5 tests)

## Verification

- Task 1 sanity: `forge_bundles` + `forge_bundle_items` present after `init_db()` — OK
- Task 2 sanity: module imports, `_add_binding` importable, `ruff check` clean
- Task 3 proxy: `cd backend && uv run pytest tests/test_forge_bundles_db.py -v` — 5 passed
- `ruff check` on both new files — clean

## Self-Check: PASSED

- FOUND: backend/app/db/forge_bundles.py
- FOUND: backend/tests/test_forge_bundles_db.py
- FOUND: backend/app/db/migrations/v07_features.py (modified, migration 156)
- FOUND: backend/app/db/__init__.py (modified, re-exports)
- FOUND commit: 9309cbebbb (Task 1)
- FOUND commit: d0af6594da (Task 2)
- FOUND commit: a47bffd2e7 (Task 3)
