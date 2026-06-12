---
phase: 17-forge-creation-surface
plan: 01
subsystem: backend/forge
tags: [bugfix, tdd, sqlite, provenance]
requires: []
provides:
  - "replace_for_project preserves binding provenance across delete/re-insert"
affects:
  - backend/app/db/project_forge_bindings.py
tech-stack:
  added: []
  patterns:
    - "Mirror add_binding's full column set + coalescing in replace_for_project so the two write paths cannot drift"
key-files:
  created:
    - backend/tests/test_forge_replace_for_project.py
  modified:
    - backend/app/db/project_forge_bindings.py
decisions:
  - "Seed provenance via direct INSERT in test (add_binding has no conflict_policy param); read back via raw SELECT to avoid re-coalescing helpers"
  - "conflict_policy default 'local_wins' written explicitly rather than relying on column DEFAULT, matching add_binding semantics"
metrics:
  duration: 12min
  completed: 2026-06-13
---

# Phase 17 Plan 01: replace_for_project Provenance Fix Summary

Fixed the confirmed provenance-dropping bug in `replace_for_project`: the PUT-style
bulk replace now preserves `source_scope`, `source_shared_binding_id`, `fingerprint`,
and `conflict_policy` across its DELETE-then-INSERT, instead of silently degrading
every binding to project-local defaults.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | RED — failing round-trip regression test | 1af4643bf6 | backend/tests/test_forge_replace_for_project.py |
| 2 | GREEN — preserve full column set + ensure propagation columns | 9ae0610101 | backend/app/db/project_forge_bindings.py |

## What Changed

- `replace_for_project` re-INSERT widened from a 6-column list to the same
  10-column set `add_binding` uses, with identical default coalescing
  (`source_scope='project'`, `source_shared_binding_id=None`, `fingerprint=None`,
  `conflict_policy='local_wins'`).
- Added `_ensure_propagation_columns(conn)` before the DELETE/INSERT, mirroring
  `add_binding`, so a fresh DB lacking the propagation columns does not crash.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Test FK constraint + environment resolution**
- **Found during:** Task 1
- **Issue (a):** `project_forge_bindings.project_id` has a FOREIGN KEY to `projects`;
  the seed binding failed with `FOREIGN KEY constraint failed` (wrong-reason failure).
  **Fix:** Added `_seed_project()` helper inserting a `projects` row before the replace.
- **Issue (b):** The worktree's `../../ai-accounts/packages/*` `file:` pin resolved to a
  non-existent `.worktrees/ai-accounts`. **Fix:** Symlinked `.worktrees/ai-accounts` →
  the real `~/Developer/Projects/ai-accounts` (environment-only, no tracked-file change).

### Bug-class sweep (house rule)

Grepped `project_forge_bindings.py` for every INSERT/UPDATE into the table. Two write
sites: `add_binding` (already carries all four provenance columns — confirmed correct)
and `replace_for_project` (the bug, now fixed). No third write site exists. The
`_row_to_dict` reader already returns all four columns. No further fixes needed.

## Experiment Results

### Results

| Metric | Baseline | Target | Achieved | Status |
|--------|----------|--------|----------|--------|
| replace_for_project round-trip preserves 4 provenance columns | 0/4 (dropped) | 4/4 | 4/4 | PASS |
| Default coalescing matches add_binding | n/a | match | match | PASS |

### Analysis

The non-default round-trip test (`source_scope='shared'`, sshb=777,
`fingerprint='fp-deadbeef'`, `conflict_policy='shared_wins'`) failed pre-fix with
`source_scope == 'project'` (provenance dropped) and passes post-fix with exact equality.
The defaults test passed both pre- and post-fix because the dropped-column path
coincidentally produced the same column DEFAULTs — it is retained as a parity guard.
17 sibling forge tests (round-wiring + materialization) still pass — no regression.

### Artifacts

- Regression test: `backend/tests/test_forge_replace_for_project.py`

## Verification

- `cd backend && uv run pytest tests/test_forge_replace_for_project.py -v` — 2 passed
- `cd backend && uv run ruff check app/db/project_forge_bindings.py` — clean
- Sibling regression: `test_forge_round_wiring.py` + `test_forge_materialization.py` — 17 passed

## Self-Check: PASSED

- FOUND: backend/tests/test_forge_replace_for_project.py
- FOUND: backend/app/db/project_forge_bindings.py (modified)
- FOUND commit: 1af4643bf6 (RED)
- FOUND commit: 9ae0610101 (GREEN)
