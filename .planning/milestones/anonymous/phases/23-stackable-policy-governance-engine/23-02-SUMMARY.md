---
phase: 23-stackable-policy-governance-engine
plan: 02
subsystem: backend/policy-engine
tags: [policy, governance, builtins, tdd, sandbox-inert]
requires: ["23-01"]
provides:
  - "_BUILTINS dispatch dict (four builtin evaluators) in policy_service.py"
  - "Pure (row, action) -> (decision, reason) evaluator functions"
affects:
  - "23-03 (enforcement wiring must populate action-ctx counters)"
  - "Phase 24 (enforce_sandbox becomes live)"
tech-stack:
  patterns: ["kind->evaluator dispatch dict", "pure-function evaluators", "store-now/enforce-later inert flag"]
key-files:
  created:
    - backend/tests/test_policy_builtins.py
  modified:
    - backend/app/services/policy_service.py
key-decisions:
  - "Evaluators take (row, action) — not (params, action) — to match the 23-01 _eval_row dispatch contract; params extracted internally via row.get('params')"
  - "cost_budget reuses budget_service hard/soft SEMANTICS but stays pure (live spend passed on action ctx), never calling check_budget (DB I/O)"
  - "enforce_sandbox is INERT until Phase 24: produces a verdict but invokes no sandbox; only gates a non-sandboxed launch, everything else allows with explicit 'inert' reason"
  - "Zero/absent caps (max_cost_usd<=0, max_tool_calls<=0) disable the hard limit rather than deny"
metrics:
  duration: ~10m
  completed: 2026-06-30
---

# Phase 23 Plan 02: Builtin Policy Evaluators Summary

Four builtin policy evaluators (`cost_budget`, `max_tool_calls_per_session`,
`ask_on_os_tools`, `enforce_sandbox`) wired into `PolicyService` via a
`kind → evaluator` `_BUILTINS` dispatch dict, so they flow through the 23-01
stacking/short-circuit engine unchanged. Built TDD (16 new tests, RED→GREEN).

## What Was Built

- `_BUILTINS` dispatch in `policy_service.py` mapping each `kind` to a pure
  module-level evaluator. `_eval_row` (23-01) already calls
  `_BUILTINS.get(kind)`; unknown/`custom` kinds fall back to stored `effect`.
- Four pure evaluators `(row, action) -> (decision, reason)`, decision in
  `{allow, deny, ask}`. No DB I/O — the live counters arrive on the action ctx.

## Evaluator contracts (params schema + action-ctx keys for 23-03)

| Builtin | params schema | action-ctx keys read | Verdict |
|---|---|---|---|
| `cost_budget` | `{max_cost_usd: float, ask_thresholds_usd: list[float]}` | `total_cost_usd` (fallback `spend`) | spend≥max_cost_usd(>0)→deny; spend≥any threshold→ask; else allow |
| `max_tool_calls_per_session` | `{max_tool_calls: int}` | `tool_calls` | count≥max(>0)→deny; else allow |
| `ask_on_os_tools` | `{}` or `{kinds: [...]}` (default shell/file_write/process_launch) | `kind` | kind∈kinds→ask; else allow |
| `enforce_sandbox` | `{require_sandbox: bool}` | `kind`, `sandboxed` | require & not sandboxed & kind∈{process_launch,shell}→deny; else allow (inert) |

**Action ctx the 23-03 enforcement plan must populate:** `total_cost_usd`,
`tool_calls`, `kind`, `sandboxed`.

## enforce_sandbox — INERT until Phase 24

Documented in both docstring and the `_BUILTINS` comment as STORE-NOW /
ENFORCE-IN-PHASE-24. It produces a deny/allow verdict but invokes no sandbox
(no sandbox runtime exists until Phase 24). The flag is stored now so policies
can be authored ahead of the runtime.

## Deviations from Plan

**1. [Rule 3 - Blocking] Evaluator signature is `(row, action)`, not `(params, action)`**
- **Found during:** RED phase, reconciling with 23-01's `_eval_row`.
- **Issue:** The plan's behavior table names evaluators `_eval_<kind>(params, action)`, but 23-01's shipped dispatch calls `builtin(row, action)`. Honoring the plan's `(params, action)` signature would break the 23-01 contract.
- **Fix:** Evaluators accept `(row, action)` and extract `params = row.get("params") or {}` internally — purity and unit-testability preserved, 23-01 stacking tests untouched.
- **Files:** `backend/app/services/policy_service.py`
- **Commit:** aedcfc5ae8

## Verification

- `pytest tests/test_policy_builtins.py` — 16 new tests pass (case tables per builtin + dispatch wiring).
- `pytest tests/test_policy_evaluator.py` — 10 SC1 stacking tests still green (builtins flow through unchanged).
- `ruff format --check app/services/policy_service.py` — clean.

## Commits

- `27e5c58f9d` test(23-02): add failing tests for four builtin policy evaluators
- `aedcfc5ae8` feat(23-02): implement four builtin policy evaluators + dispatch

## Next Phase Readiness

Ready for 23-03 (enforcement wiring): route goal_loop exit-ladder budgets +
bot-security/bot-pr-review checks through `PolicyService.evaluate`, populating
the action ctx keys above and raising `PolicyDenied` on a DENY verdict.

## Self-Check: PASSED
- backend/tests/test_policy_builtins.py exists
- _BUILTINS populated with four evaluators
- Commits 27e5c58f9d, aedcfc5ae8 present on branch
