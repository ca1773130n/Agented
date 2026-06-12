---
phase: 17-forge-creation-surface
plan: 05
subsystem: backend/forge
tags: [forge, atomic-create, compensation, lifo, bundle-bind, routes]
requires:
  - "17-02 subagent create_subagent + VALID_FORGE_BINDING_KINDS + _get_asset"
  - "17-03 forge_bundles + conn-accepting _add_binding"
  - "17-04 subagent materialize write branch (.claude/agents/<name>.md)"
provides:
  - "POST /admin/projects/{id}/forge/create atomic create+bind+materialize with LIFO compensation"
  - "POST /admin/projects/{id}/forge/bundles/{id}/bind cross-kind bundle-bind in one transaction"
  - "create_and_bind_and_materialize service with error-safe LIFO compensation"
affects:
  - backend/app/services/forge_create_service.py
  - backend/app_litestar/routes/project_forge_bindings.py
  - backend/tests/routes/test_forge_bindings_routes.py
tech-stack:
  added: []
  patterns:
    - "Explicit LIFO compensation stands in for an absent DB+FS saga: forward steps tracked, undone in reverse on any exception"
    - "Each compensation action wrapped in its own try/except so cleanup errors cannot mask the original; original re-raised"
    - "Service imports add_project_forge_binding/materialize_primitives into its own namespace so tests monkeypatch app.services.forge_create_service.<name>"
    - "Manifest reconcile in compensation runs _finalize_manifest with empty result for the kind to drop the just-written bucket entries"
key-files:
  created:
    - backend/app/services/forge_create_service.py
  modified:
    - backend/app_litestar/routes/project_forge_bindings.py
    - backend/tests/routes/test_forge_bindings_routes.py
decisions:
  - "forge/create dispatch supports the create-capable kinds (subagent/rule/command/hook/mcp_server); skill has no db create fn and is excluded"
  - "create return type is normalized: subagent/mcp_server return full row dict, rule/command/hook return int lastrowid -> coerced to asset_id"
  - "bundle-bind forced to status_code=200 (Litestar POST default is 201); binds all items in ONE get_connection() block, commit-once or rollback"
  - "ValueError (bad/unsupported kind, project-not-found) -> 400; compensated re-raised RuntimeError -> 5xx via existing handlers"
metrics:
  duration: ~12m
  completed: 2026-06-13
  tasks: 3
  files: 3
---

# Phase 17 Plan 05: Atomic Forge Create + Bundle-Bind Summary

Built `POST /admin/projects/{id}/forge/create` `{kind, payload, bind, materialize}`
as a single atomic flow over a codebase that has NO DB+filesystem saga
abstraction. Atomicity is explicit LIFO compensation in
`create_and_bind_and_materialize`: it performs up to three forward steps
(create row -> bind -> materialize), tracks exactly which completed, and on any
mid-flow exception undoes them in reverse (unlink written files + reconcile
manifest -> remove binding -> delete asset row), re-raising the original error.
Each cleanup action is isolated so a compensation failure cannot mask the
original. Also added the cross-kind bundle-bind route consuming 17-03's
conn-accepting `_add_binding` so every item binds in one transaction.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | forge_create_service with LIFO compensation | a5685b4f95 | backend/app/services/forge_create_service.py |
| 2 | forge/create + bundle-bind route handlers | c63a29d4ad | backend/app_litestar/routes/project_forge_bindings.py |
| 3 | route tests: create success + 2-stage no-orphan + bundle-bind | e1900102f1 | backend/tests/routes/test_forge_bindings_routes.py |

## Deviations from Plan

None — plan executed as written. (One in-flight correction: the bundle-bind
handler needed an explicit `status_code=200` because Litestar defaults POST to
201; caught by the test and fixed before the Task 2/3 commits were finalized.)

## Experiment Results

### Results

| Metric | Baseline | Target | Achieved | Status |
|--------|----------|--------|----------|--------|
| no-orphan on injected bind failure | no endpoint | no row/binding/file | 0 row, 0 binding, 0 file | PASS |
| no-orphan on injected materialize failure | no endpoint | no row/binding/file | 0 row, 0 binding, 0 file | PASS |
| create success 201 + file on disk | no endpoint | row+binding+.claude/agents/<name>.md | all present | PASS |
| bundle-bind cross-kind one call | no route | all items bound | 3 kinds (rule/command/subagent) bound | PASS |

### Analysis

The materialize-stage failure test is the strongest: both the row AND the
binding completed before the injected exception, so compensation had to unwind
two steps; assertions confirm zero rows, zero bindings, zero repo files remain.
The bind-stage test exercises single-step unwind (row only). Bundle-bind seeded
a 3-kind bundle and asserted all three (kind, asset_id) pairs are bound after
one POST.

### Artifacts

- Service: `backend/app/services/forge_create_service.py`
- Routes: `backend/app_litestar/routes/project_forge_bindings.py`
- Tests: `backend/tests/routes/test_forge_bindings_routes.py`

## Verification

- Level 1 (Sanity): service imports; `forge/create` + `bundles/{id}/bind` routes
  registered in the built app; ruff clean on all three files.
- Level 2 (Proxy): `cd backend && uv run pytest tests/routes/test_forge_bindings_routes.py -v`
  -> **12 passed** (includes create-success, both injected-failure no-orphan
  cases, bad-kind 400, and cross-kind bundle-bind).

## Self-Check: PASSED
