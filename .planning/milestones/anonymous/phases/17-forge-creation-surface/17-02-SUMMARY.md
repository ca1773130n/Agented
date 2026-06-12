---
phase: 17-forge-creation-surface
plan: 02
subsystem: backend-forge-primitives
tags: [forge, subagent, db, migration, routes]
requires: []
provides:
  - "subagents table (migration 155, subag- id prefix)"
  - "subagent CRUD module + re-exports"
  - "subagent in VALID_KINDS / VALID_FORGE_BINDING_KINDS"
  - "/admin/subagents CRUD routes"
  - "_get_asset subagent dispatch (READ half)"
affects:
  - "17-04 (subagent materialization WRITE branch + 4-backend renderers)"
  - "17-05 (atomic create endpoint)"
tech-stack:
  added: []
  patterns:
    - "forge primitive mirrors skill/rule/hook/command (CRUD + router + VALID_KINDS + _get_asset)"
    - "str ids (subag-) resolved like mcp_server in _get_asset"
key-files:
  created:
    - backend/app/db/subagents.py
    - backend/app_litestar/routes/project_subagents.py
    - backend/tests/test_subagents_db.py
  modified:
    - backend/app/db/migrations/v07_features.py
    - backend/app/db/ids.py
    - backend/app/db/__init__.py
    - backend/app/db/project_forge_bindings.py
    - backend/app_litestar/main.py
    - backend/app/services/forge_materialization_service.py
decisions:
  - "Claimed migration 155 for the subagents table (156 owned by 17-03)"
  - "subagents is a brand-new table; legacy agents table / create_agent untouched"
  - "subagent ids are STR (subag-), resolved in _get_asset like mcp_server"
  - "_get_asset only does the READ/dispatch branch; WRITE branch left as TODO(17-04)"
metrics:
  duration: "~20m"
  completed: 2026-06-13
  tasks: 3
  files: 9
---

# Phase 17 Plan 02: Subagent Forge Primitive (DB + Registry) Summary

Registered `subagent` as a first-class forge primitive at the DB + registry +
dispatch layer by mirroring the skill/rule/hook/command pattern: a distinct
`subagents` table (migration 155, `subag-` id prefix), a CRUD module, a
Litestar CRUD router, dual kind-registry membership, and a `_get_asset` READ
branch. The materialization WRITE branch and 4-backend renderers remain 17-04's
job.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | migration 155 + subagents CRUD + subag- id | 157fc623ba | v07_features.py, ids.py, subagents.py, db/__init__.py |
| 2 | VALID_KINDS + routes + _get_asset dispatch | 5037fb1b0b | project_forge_bindings.py, project_subagents.py, main.py, forge_materialization_service.py |
| 3 | subagent DB + registry tests | 3466944f7d | tests/test_subagents_db.py |

## Migration

- **Migration number used: 155** (`_migrate_155_subagents`). 156 reserved by 17-03 (forge_bundles), so 155 was claimed here as instructed.
- Schema: `subagents(id TEXT PK, name TEXT UNIQUE NOT NULL, description, content TEXT NOT NULL, enabled INTEGER DEFAULT 1, project_id, source_path, created_at, updated_at)`. `content` holds the full `.claude/agents/<name>.md` body including frontmatter.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected the Task-1 verify command import path**
- **Found during:** Task 1 verification.
- **Issue:** The plan's verify snippet imported `app.db.database` / `app.db.schema`, which do not exist; the project initializes the DB via `app.database.init_db()`.
- **Fix:** Ran the equivalent verification using `from app.database import init_db; init_db()` plus `app.db.connection.get_connection`. No production code affected.

## Experiment Results

### Results

| Metric | Baseline | Target | Achieved | Status |
|--------|----------|--------|----------|--------|
| subagent CRUD + dual kind-registry membership | none | end-to-end at DB+registry+_get_asset | yes (5/5 tests pass) | PASS |
| subag- prefix | n/a | enforced | yes | PASS |
| name UNIQUE | n/a | raises on dup | yes (IntegrityError) | PASS |
| legacy agents table distinct | n/a | separate | yes | PASS |

### Analysis

The forge-primitive pattern mirrors cleanly. The only nuance vs rule/hook/command
is the STR id (`subag-`), handled exactly like `mcp_server` in `_get_asset`. The
legacy `agents` table and `create_agent` were never touched — `test_legacy_agents_table_distinct`
asserts both tables coexist and a subagent row never lands in `agents`.

## Handoff to 17-04

`_get_asset` resolves a `subagent` by str id (READ). The WRITE branch — rendering
each bound subagent to `.claude/agents/<name>.md` across the 4 backends — is marked
with `TODO(17-02→17-04)` in `forge_materialization_service.py::_get_asset`.

## Verification

- Level 1 (Sanity): subagents + legacy agents tables both present and distinct; both registries contain `subagent`; app builds with the new router; ruff clean on new modules.
- Level 2 (Proxy): `uv run pytest tests/test_subagents_db.py -v` → 5 passed.

## Self-Check: PASSED

All created files present; all 3 task commits exist (157fc623ba, 5037fb1b0b, 3466944f7d).
