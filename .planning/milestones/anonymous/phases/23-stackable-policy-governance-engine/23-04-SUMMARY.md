# 23-04 SUMMARY — /admin/policies router + PolicyMiddleware

**Status:** DONE. `app_litestar/routes/policies.py` (new), `middleware.py` (PolicyMiddleware), `main.py` (registration) + `tests/test_policies_router.py` (now 11 tests) and `tests/test_policy_middleware.py` (4 tests), green. Commit `3c4cac5536` (+ admin-gate hardening `329a79cc3d`).

- `policies_router = Router(path="/admin/policies", ...)` mirroring `budgets_router`: GET (list) / PUT (upsert → `create_policy`/`update_policy`) / DELETE `/{policy_id}`, with scope/kind/effect validation. Registered next to `budgets_router` in `main.py`.
- POST `/admin/policies/decision` resolves a pending ASK via `PolicyService.submit_policy_decision` (mirrors `grd_routes.loop_gate_decision`) — the HTTP entry the frontend ASK card POSTs to.
- `PolicyMiddleware(ASGIMiddleware)`: non-blocking pass-through that annotates the request with its governance scope (`policy_scope_var` contextvar + scope state + `X-Policy-Scope` header) when the path carries a session id; registered after `RequestContextMiddleware`. Enforcement stays at the action boundaries (23-03), not the middleware.

Deviation/hardening: round-2 codex hardening (`329a79cc3d`) gated the whole `/admin/policies` router at admin (`requires_role`, mirrors `secrets_router`) plus coarse `ROLE_REQUIRED` rows — policies are the governance substrate, so they are admin-only; `test_policies_router.py` grew from 8 to 11 tests. Round-3 made the `/decision` POST carry a required `ask_id`.
