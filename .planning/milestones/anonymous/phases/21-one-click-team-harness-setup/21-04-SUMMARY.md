---
phase: 21-one-click-team-harness-setup
plan: 04
subsystem: backend/services
tags: [harness-setup, forge-bundles, tesserae, bundle-selection, idempotency]
requires: ["21-02", "21-03"]
provides: ["_step_bundle_binding", "_step_tesserae_enable", "_select_bundles_for_stack"]
affects: ["backend/app/services/team_harness_setup_service.py"]
tech-stack:
  patterns: ["pure-selection-helper", "always-bind-floor", "existence-check-reconcile", "idempotent-set-no-unset"]
key-files:
  modified:
    - backend/app/services/team_harness_setup_service.py
    - backend/tests/test_team_harness_setup_service.py
decisions:
  - "forge-creator is the ONLY unconditional bind (the floor); language bundles bound only when get_forge_bundle_by_name returns a seeded row"
  - "Missing forge-creator is a hard failure (RuntimeError); missing language bundle is a silent skip"
  - "Static language->bundle map {python: forge-python, typescript: forge-typescript}; parsed case-insensitively from STACK.md ## Languages section only"
  - "tesserae reconcile: skipped when get_tesserae_root already == resolved local_path, else ok; set_tesserae_root always re-called (idempotent)"
metrics:
  tasks: 2
  duration: ~12m
  completed: 2026-06-13
---

# Phase 21 Plan 04: Bundle binding + Tesserae enable Summary

Implemented steps c (project-tailored forge-bundle binding) and d (per-project Tesserae enablement), replacing the wave-1 placeholders. Bundle selection is the REQ-21 tailoring surface: a pure `_select_bundles_for_stack` parses STACK.md `## Languages`, always emits the `forge-creator` floor, and adds a language-specific bundle only when seeded. Tesserae leans on the already-idempotent `set_tesserae_root`.

## Tasks Completed

- **Task 1 — `_step_bundle_binding` + `_select_bundles_for_stack`** (`ad11aa469d`): Pure helper slices the `## Languages` section, lowercases it, and appends mapped bundle names (dedup, order-preserving) after the `forge-creator` floor; `None`/empty → floor only. Step reads `<local_path>/.planning/codebase/STACK.md` (None if absent), binds each seeded bundle via `bind_bundle_to_project` (idempotent upsert), silently skips unseeded language bundles, and raises if the guaranteed `forge-creator` floor is missing. No DELETE/unbind path touched (SC4).
- **Task 2 — `_step_tesserae_enable`** (`ad11aa469d`): Resolves the root to the project's `local_path`, calls `set_tesserae_root` (idempotent, also best-effort binds the per-project Tesserae MCP), and reconciles — `skipped` when `get_tesserae_root` already equals the resolved root, else `ok`. `unset_tesserae_root_bindings` is never called (P2/SC4).

Both step changes share one file write and were committed atomically (intertwined dispatch-table rebind).

## Deviations from Plan

None — plan executed as written. (Task-level commits collapsed into one atomic commit because both step bodies live in the same dispatch table / file and were not separable without a broken intermediate state.)

## Experiment Results

### Results

| Check | Target | Achieved | Status |
|-------|--------|----------|--------|
| P3 Python fixture | floor + forge-python, no forge-typescript | pass | PASS |
| P3 TypeScript fixture | floor + forge-typescript, no forge-python | pass | PASS |
| P3 missing STACK.md | `["forge-creator"]` only | pass | PASS |
| P3 floor bind | `bind_bundle_to_project` called with forge-creator id | pass | PASS |
| P3 idempotency | re-run adds zero binding rows | count stable | PASS |
| P2 tesserae idempotent | re-run skipped, root persists | pass | PASS |
| P2 no destructive | `unset_tesserae_root_bindings` never called | monkeypatch-to-raise not triggered | PASS |

`tests/test_team_harness_setup_service.py`: 17 passed (6 new: 5 bundle_selection + 1 tesserae). `ruff format` + `ruff check`: clean.

## Self-Check: PASSED

- FOUND: backend/app/services/team_harness_setup_service.py (`_step_bundle_binding`, `_step_tesserae_enable`, `_select_bundles_for_stack`, `_read_stack_md`)
- FOUND: backend/tests/test_team_harness_setup_service.py (bundle_selection + tesserae tests)
- FOUND commit: ad11aa469d
