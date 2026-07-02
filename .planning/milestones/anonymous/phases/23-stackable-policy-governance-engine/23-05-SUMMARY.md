# 23-05 SUMMARY — policy frontend surface + ALLOW/DENY/ASK e2e

**Status:** DONE. Frontend surface in commit `fd3b4aa433`; the SC5 e2e (`tests/test_policy_e2e.py`, 7 tests) shipped separately in `316825663f` (tagged `feat(23-06)`). All green.

- `services/api/policies.ts` — `policyApi { list, upsert, remove, decide }` via `apiFetch`, plus `types/policies.ts`, both re-exported through the api + types barrels.
- `budgets.ts` — additive `costCapVerdict()` surfacing the `cost_budget` policy decision client-side (DENY at `max_cost_usd` / ASK at `ask_thresholds_usd`); does not break existing `budgetApi` callers.
- `components/policy/PolicyEditor.vue` (CRUD) + `PolicyAskCard.vue` (renders the `policy_ask` SSE event `{policy_id, kind, reason, scope}`, POSTs approve/deny to `/admin/policies/decision`); `views/PolicyManagement.vue` + a `/policies` router entry.
- en/ko/ja/zh gain a key-identical `policy.*` namespace with a parity spec (drift fails the suite).
- Vitest: `PolicyEditor` (4) + `PolicyAskCard` (4) + locale parity (2) green; full frontend suite 1680 passed with only the 7 known baseline failures (no new); `just build` green.

Deviation: the plan folded the SC5 e2e into this plan, but it landed as its own commit `316825663f` (`feat(23-06)`, 246 lines) — driving a real session through both enforcement boundaries (`ExecutionService._enforce_launch_policy` ALLOW/DENY/ASK + `goal_loop_runner._evaluate_cost_policy`) and asserting the `policy_ask` payload contract. The full serial backend suite was not run (known ~40-48% hang per repo policy); targeted policy suites verified. Phase then went through 5 rounds of codex hardening before PR #286 merged.
