---
phase: 21-one-click-team-harness-setup
plan: 05
subsystem: team-harness-setup
tags: [autonomy-policy, repeated-request-gate, harness-autonomy, idempotent]
requires: ["21-02"]
provides: ["_step_default_policies dual-consumer autonomy policy"]
affects: ["repeated_request_gate._auto_apply_policy", "harness_autonomy.autonomous_apply_eligible"]
tech-stack:
  added: []
  patterns: ["upsert_policy idempotent ON CONFLICT", "get_policy equality reconcile skip-vs-run"]
key-files:
  created: []
  modified:
    - backend/app/services/team_harness_setup_service.py
    - backend/tests/test_team_harness_setup_service.py
decisions:
  - "Single project_autonomy_config row satisfies both gate readers: enabled=True arms takeaway auto-apply; allowed_kinds=['discovered_procedure'] + block_deletes + max_ops_per_round=1 keep evolution autonomy conservative"
  - "confidence_threshold (0.85) and rate_limit_per_day (10) left at conservative model defaults"
metrics:
  duration: ~12m
  completed: 2026-06-13
---

# Phase 21 Plan 05: Default Autonomy Policy (Step e) Summary

Step e of the team-harness setup orchestrator now writes the single dual-consumer
`project_autonomy_config` row — `AutonomyPolicy(enabled=True, allowed_kinds=["discovered_procedure"],
block_deletes=True, max_ops_per_round=1)` — turning takeaway auto-apply ON (scoped to
skill-from-repetition) while keeping evolution autonomy conservative, written idempotently
via `upsert_policy`.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Step e dual-consumer AutonomyPolicy via upsert_policy | 38a78fd5bb | team_harness_setup_service.py |
| 2 | autonomy_policy test — both gate readers + idempotency | f20b3081a2 | test_team_harness_setup_service.py |

## Implementation

- `_step_default_policies(project_id, existing_row)` builds the target via `_default_autonomy_policy()`,
  reconciles against `get_policy(project_id)` (equality → `skipped`, else `upsert_policy` → `ok`),
  and never deletes the row (SC4). `AutonomyPolicy` imported lazily under `TYPE_CHECKING` for the
  annotation + at call time inside the helper.
- Bound into `_STEP_FUNCS["default_policies"]` (the dispatch table already referenced the function name;
  replacing the placeholder body was sufficient).

## Exact policy field values written

| Field | Value | Source |
|-------|-------|--------|
| enabled | True | armed (auto-apply ON) |
| allowed_kinds | ["discovered_procedure"] | excludes rule/hook → evolution gate-blocked |
| block_deletes | True | conservative |
| max_ops_per_round | 1 | blast-radius cap |
| confidence_threshold | 0.85 | model default (conservative) |
| cooldown_seconds | 3600 | model default |
| rate_limit_per_day | 10 | model default (conservative) |

## Dual-consumer note

`repeated_request_gate._auto_apply_policy` reads `policy_json` and looks for the key `"kinds"`
(not `"allowed_kinds"`). Since `AutonomyPolicy` serializes `allowed_kinds`, the gate finds no
`"kinds"` key and falls through to `return True` (because `enabled=True`). The scoped-True
outcome holds regardless. Verified by test assertion `_auto_apply_policy(pid) is True`.

## Deviations from Plan

None — plan executed exactly as written.

## Experiment Results

### Parameters

| Parameter | Value |
|-----------|-------|
| enabled | True |
| allowed_kinds | ["discovered_procedure"] |
| block_deletes | True |
| max_ops_per_round | 1 |

### Results

| Metric (P7) | Target | Achieved | Status |
|-------------|--------|----------|--------|
| get_policy row shape | enabled/block_deletes True, allowed_kinds scoped, max_ops 1 | matches | PASS |
| _auto_apply_policy(project_id) | True | True | PASS |
| evolution conservative | no rule/hook in allowed_kinds, block_deletes True | holds | PASS |
| idempotent re-run | exactly 1 row, status skipped | 1 row, skipped | PASS |

### Analysis

`test_default_policies_dual_consumer_autonomy_policy` green; full file 18/18 passing.
Per EVAL P7 blind-spot note, evolution conservatism is asserted structurally (allowed_kinds
exclusion + block_deletes) rather than by exercising `autonomous_apply_eligible` with fixtures.

## Self-Check: PASSED

- FOUND: backend/app/services/team_harness_setup_service.py (`_step_default_policies` non-placeholder)
- FOUND: backend/tests/test_team_harness_setup_service.py (`test_default_policies_dual_consumer_autonomy_policy`)
- FOUND commit: 38a78fd5bb
- FOUND commit: f20b3081a2
