---
phase: 21-one-click-team-harness-setup
plan: 02
subsystem: backend-service
tags: [orchestrator, harness-setup, idempotency, state-machine]
requires:
  - "21-01: get/set_harness_setup_status + upsert/get_harness_setup_steps helpers"
provides:
  - "TeamHarnessSetupService.setup(project_id) -> final status"
  - "HARNESS_SETUP_STEP_KEYS (6 ordered keys)"
  - "StepResult dataclass (step_key, status, detail, fingerprint)"
  - "_STEP_FUNCS dispatch table (placeholder bodies for 21-03..06 to replace)"
affects:
  - "21-03..06 (step-group plans plug real bodies into _STEP_FUNCS)"
  - "21-07 (route plan calls setup())"
tech-stack:
  added: []
  patterns:
    - "thin sequential orchestrator; per-step try/except -> StepResult"
    - "none->running->ready/failed state machine; setup() never raises"
    - "first-failure-stops; later steps left unrecorded (retryable)"
    - "re-run skips rows already status='ok' (idempotency floor)"
key-files:
  created:
    - backend/app/services/team_harness_setup_service.py
    - backend/tests/test_team_harness_setup_service.py
  modified: []
decisions:
  - "Steps return StepResult; the orchestrator (not the step) persists the row via upsert_harness_setup_step — keeps step bodies side-effect-free w.r.t. the step log and centralises failure recording"
  - "_STEP_FUNCS is a class attribute assigned after the module-level placeholder defs; 21-03..06 rebind individual keys, tests monkeypatch the whole dict"
  - "On first failure, break out of the loop and leave later steps unrecorded (absence == retryable) rather than marking them pending — matches SC4 no-destructive + P6 retryable"
  - "Skip floor honours an existing status=='ok' row; per-step fingerprint logic (StepResult.fingerprint) is reserved for 21-03..06 to add finer skip-vs-rerun"
metrics:
  tasks: 2
  files: 2
  completed: 2026-06-13
---

# Phase 21 Plan 02: TeamHarnessSetupService Skeleton Summary

A thin sequential orchestrator over six harness-setup steps:
`HARNESS_SETUP_STEP_KEYS` (6), a `StepResult` contract, the
none->running->ready/failed state machine, step-row persistence via 21-01's
upsert, and retry-skips-completed logic. Placeholder step bodies make import
smoke (S3) and the skeleton tests green immediately; 21-03..06 replace the
bodies in `_STEP_FUNCS`.

## What Was Built

- **Task 1 — Service skeleton** (`team_harness_setup_service.py`):
  `HARNESS_SETUP_STEP_KEYS = [grd_init, team_topology, bundle_binding,
  tesserae_enable, default_policies, materialize_compile]`; `StepResult`
  dataclass; `TeamHarnessSetupService.setup(project_id)` sets status "running",
  loads existing step rows, iterates keys (skipping rows already "ok"), wraps
  each `_STEP_FUNCS[key]` call in try/except, persists the row on success,
  records a "failed" row + breaks on exception, and finalises "ready"/"failed".
  A catch-all guard ensures `setup()` never raises. Side-effect-free placeholder
  `_step_*` bodies wired into `_STEP_FUNCS`.
- **Task 2 — Skeleton tests** (`test_team_harness_setup_service.py`): import
  smoke (S3), fresh-run->ready with 6 ok rows, `failed_step` (2nd step raises ->
  failed status + log row with detail + later steps unrecorded), `idempotent`
  re-run skips ok steps, retry re-attempts a failed prefix, and a placeholder
  end-to-end dispatch test. 6/6 green.

## Step dispatch contract (for 21-03..06)

Each step is `def _step_<name>(project_id: str, existing_row: dict | None) -> StepResult`:
- `existing_row` is the persisted `harness_setup_steps` row (dict) or `None`.
- The step inspects `existing_row`/computes a fingerprint to decide skip-vs-run,
  calls existing DB/service helpers, and returns
  `StepResult(step_key, status, detail="", fingerprint=None)` where status is
  `"ok" | "skipped" | "failed"`.
- The step does NOT persist its row — the orchestrator calls
  `upsert_harness_setup_step(...)` with the result.
- Raising an exception == hard failure: orchestrator records a `failed` row with
  `detail=str(exc)`, sets overall failed, and STOPS (later steps stay retryable).
- Rebind by assigning into `TeamHarnessSetupService._STEP_FUNCS[<key>]` (or
  replacing the module-level `_step_<name>` then re-registering). Tests
  monkeypatch the whole `_STEP_FUNCS` dict.
- Steps must NOT perform destructive deletes on re-run (SC4 / P2).

## Deviations from Plan

None - plan executed exactly as written.

## Experiment Results

### Results

| Metric | Target | Achieved | Status |
|--------|--------|----------|--------|
| S3: import smoke, 6 step keys | prints ok | prints ok | PASS |
| S5 prereq: ruff check service + test | clean | clean | PASS |
| P6 foundation: failed step -> failed + log + retryable | green | green | PASS |
| P1 foundation: re-run skips ok steps | green | green | PASS |
| Skeleton test suite | all green | 6/6 pass | PASS |

### Analysis

State machine, per-step isolation, and idempotency floor verified against
`isolated_db`. The retry test confirms an already-ok prefix is skipped while a
previously-failed step is re-attempted on the next run, satisfying the P6
retryable invariant without rolling back prior steps.

## Commits

- 169dbdab6d: feat(21-02) TeamHarnessSetupService skeleton + 6-step dispatch
- b2288670f0: test(21-02) skeleton orchestrator tests (import/state-machine/retry)

## Self-Check: PASSED

Both files exist on disk; both commit hashes present in git log.
