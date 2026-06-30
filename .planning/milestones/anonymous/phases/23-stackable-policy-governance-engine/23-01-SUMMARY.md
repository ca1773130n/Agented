---
phase: 23-stackable-policy-governance-engine
plan: 01
subsystem: governance
tags: [policy, sqlite, migration, tdd, governance, session-scope]

requires: []
provides:
  - "policies table (migration 176): scope/scope_id/kind/effect/params/enabled/priority"
  - "PolicyService.evaluate(session_id, team_id, action) -> PolicyVerdict dict"
  - "Stacking + short-circuit invariant (SC1): session DENY beats server ALLOW"
  - "PolicyService CRUD helpers (create/get/list/update/delete_policy)"
  - "PolicyDenied exception (for 23-03 enforcement)"
  - "_BUILTINS dispatch seam (kind -> evaluator) for 23-02"
affects: [23-02-builtins, 23-03-enforcement, policy-routes, governance]

tech-stack:
  added: []
  patterns:
    - "Classmethod service (mirrors BudgetService/ExecutionService) — no instance state"
    - "Single-table stacked policy engine read SESSION-first with first-DENY short-circuit"
    - "PolicyVerdict as a plain dict: {decision, policy_id, kind, reason, scope}"

key-files:
  created:
    - backend/app/services/policy_service.py
    - backend/tests/test_policy_evaluator.py
    - backend/tests/test_migration_176_policies.py
  modified:
    - backend/app/db/migrations/v07_features.py
    - backend/tests/test_migration_175_competitor_strategy_session.py

key-decisions:
  - "Default ALLOW returns scope=None; an explicit ALLOW row does not short-circuit and is effectively ignored (no scope attribution)"
  - "Server is the sentinel scope (scope_id IS NULL) and is always consulted; session/team are skipped when their id is None"
  - "Relaxed pre-existing test_schema_version_is_175 to assert >=175 (176 is now the head) rather than the exact head"

patterns-established:
  - "Pattern: _eval_row resolves a row via _BUILTINS dispatch, falling back to the stored effect — the extension seam 23-02 fills"
  - "Pattern: short-circuit proven in tests by spying on _rows_for and asserting 'server' is never queried after a session DENY"

duration: 18min
completed: 2026-06-30
---

# Phase 23 Plan 01: Stackable Policy Engine Primitive Summary

**A single `policies` SQLite table (migration 176) plus `PolicyService.evaluate` that stacks rows across session/team/server scopes, evaluates the SESSION scope first, and short-circuits on the first DENY — proving the SC1 stacking-order invariant (a session DENY beats a server ALLOW) before any builtin or enforcement code exists.**

## Performance

- **Duration:** ~18 min
- **Tasks:** 2 features via RED-GREEN (TDD)
- **Files created:** 3 | **Files modified:** 2

## Accomplishments
- `policies` table (migration 176) with `idx_policies_scope(scope, scope_id, enabled)` + `idx_policies_kind(kind, enabled)`, idempotent via `IF NOT EXISTS`.
- `PolicyService.evaluate(*, session_id, team_id=None, action)` returns the `PolicyVerdict` dict and short-circuits on the first DENY — server scope is never read after a session DENY (spy-asserted).
- CRUD helpers + `PolicyDenied` exception + `_BUILTINS` dispatch seam wired for downstream plans.
- 15 tests passing; ruff format + lint clean.

## PolicyVerdict shape

```python
{"decision": "allow"|"deny"|"ask", "policy_id": str|None,
 "kind": str|None, "reason": str, "scope": "session"|"team"|"server"|None}
```

- DENY: returned immediately on the first matching deny row (short-circuit), with `scope` = the scope it fired in.
- ASK: first ASK encountered is collected and returned only if no DENY is found anywhere.
- Default ALLOW: `{"decision":"allow", "policy_id":None, "kind":None, "scope":None}` — explicit ALLOW rows do not short-circuit.

## CRUD helper signatures (`PolicyService`)

- `create_policy(*, scope, scope_id=None, kind, effect="ask", params=None, enabled=1, priority=0) -> dict`
- `get_policy(policy_id) -> dict | None`
- `list_policies(scope=None) -> list[dict]`
- `update_policy(policy_id, **fields) -> dict | None` (fields: scope/scope_id/kind/effect/params/enabled/priority)
- `delete_policy(policy_id) -> bool`

IDs are `pol-` + 6 random chars via the central `app.db.ids.generate_id`.

## The `_BUILTINS` dispatch seam (for 23-02)

`_BUILTINS: dict = {}` maps a policy `kind` to a callable `(row, action) -> (decision, reason)`. `_eval_row` consults it first and falls back to the row's stored `effect` verbatim. 23-02 registers builtin evaluators here without touching `evaluate`/`_rows_for`.

## Task Commits

1. **RED: failing tests** — `d86c2987e9` (test)
2. **GREEN: migration 176** — `f7c6ba6e19` (feat)
3. **GREEN: PolicyService.evaluate + CRUD** — `6a22f67a9a` (feat)

_No REFACTOR commit — implementation was clean as written._

## Files Created/Modified
- `backend/app/services/policy_service.py` — PolicyService (evaluate + _rows_for + _eval_row + CRUD), `PolicyDenied`, `_BUILTINS` seam.
- `backend/app/db/migrations/v07_features.py` — `_migrate_176_policies` + `(176, "policies", ...)` registry entry.
- `backend/tests/test_policy_evaluator.py` — 9 stacking/short-circuit/CRUD tests.
- `backend/tests/test_migration_176_policies.py` — 6 migration apply/idempotency/index tests.
- `backend/tests/test_migration_175_competitor_strategy_session.py` — relaxed stale head-version assertion.

## Decisions Made
- Default ALLOW carries `scope=None`; explicit ALLOW rows are not attributed a scope and never short-circuit. (Plan-specified.)
- Server is the always-consulted sentinel scope (`scope_id IS NULL`); session/team are skipped when their id is None.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Stale schema-head assertion in migration-175 test**
- **Found during:** Feature 2 (migration 176)
- **Issue:** `test_schema_version_is_175` asserted `MAX(version) == 175`; adding migration 176 makes 176 the head, breaking it.
- **Fix:** Relaxed to `>= 175` and renamed to `test_schema_version_is_at_least_175`.
- **Files modified:** `backend/tests/test_migration_175_competitor_strategy_session.py`
- **Verification:** Both migration test files pass together.
- **Committed in:** `f7c6ba6e19`

---

**Total deviations:** 1 auto-fixed (1 × Rule 1). **Impact:** none — keeps the suite green as the schema head advances.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
Ready for 23-02 (builtin policy evaluators): register `kind`-keyed callables in `_BUILTINS` — no change to `evaluate`/`_rows_for` needed. 23-03 enforcement can import `PolicyDenied` and call `PolicyService.evaluate` at the SESSION scope. The full serial backend suite was not run here (known ~40-48% hang per repo policy); the plan's targeted Level-1 verification passed.

## Self-Check: PASSED

- Files exist: policy_service.py, test_policy_evaluator.py, test_migration_176_policies.py — all FOUND.
- Migration: `_migrate_176_policies` present + registry tuple `(176, "policies", ...)` — FOUND.
- Commits d86c2987e9 / f7c6ba6e19 / 6a22f67a9a — all FOUND.
- Tests: 15 passed; ruff format + lint clean.

---
*Phase: 23-stackable-policy-governance-engine*
*Completed: 2026-06-30*
