# v0.5.12 State

Status: COMPLETE — ready for tag/release.

## Shipped

### Backend

- Migration 109: 3 new columns on `sessions`
  (`rotated_from_token`, `revoked_at`, `revoke_reason`) + new
  `session_events` audit table + 4 indices.
- `app/db/session_events.py`: `log_session_event` (best-effort write)
  + `list_session_events` (read with filters + pagination + corrupt-
  metadata resilience).
- `app/db/sessions.py`: `rotate_session(token)`, `revoke_user_sessions
  (user_id, *, reason)`, idle-expiry path + revocation check + grace-
  window match in `get_session_by_token`, soft-delete `revoke_session`.
  Constants: `DEFAULT_IDLE_LIFETIME = 30 minutes`,
  `ROTATION_GRACE_WINDOW = 5s`. (`DEFAULT_LIFETIME` stays 14 days.)
- `app/db/rbac.py`: revocation hooks on `update_user_role` (reason=
  `role_change`) + `rotate_user_role` (reason=`key_rotation`).
- `app_litestar/auth_guards.py`: `ROLE_RANK` + `ROLE_REQUIRED` table
  + `PUBLIC_PATHS` + `required_role(method, path)` +
  `has_sufficient_role(role, required)` + `requires_role(min_role)`
  guard factory (validates role at construction).
- `app_litestar/middleware.py`: `ApiKeyMiddleware` enforces coarse
  role + rotates session token on every bearer request + emits
  `X-New-Session-Token` response header + stashes
  `principal = {user_id, role}` in `scope["state"]`. New `_forbidden`
  helper for 403 responses.
- `app_litestar/routes/auth_management.py`:
  `POST /admin/auth/logout` (revokes caller's sessions; in
  PUBLIC_PATHS so any authenticated principal can logout),
  `POST /admin/users/:user_id/sessions/revoke` (admin-only),
  `GET /admin/auth/session-events` (admin-only,
  filter/limit/offset).
- Per-route guards: `requires_role("admin")` added to
  `POST /api/setup/bundle-install` (subprocess install) and
  `POST /admin/backends/:id/install` (subprocess install).

### Frontend

- `services/api/client.ts`: `apiFetchSingle` reads
  `X-New-Session-Token` response header (before `response.ok` check
  so it fires on 4xx too) and updates stored token via
  `setSessionToken`.
- `services/__tests__/api.test.ts`: pre-existing `mockResponse`
  helper updated to include `headers: new Headers()` so it
  matches the real Response shape.

### Tests added

- `test_migration_109.py` — 8 tests (columns + table + indices +
  idempotency)
- `test_session_events.py` — 8 tests (round-trip + filters +
  pagination + best-effort + combined filters + corrupt metadata)
- `test_sessions_lifecycle.py` — 10 tests (rotate / revoke-by-user
  / idle / revoked-lookup)
- `test_rbac_session_revocation.py` — 3 tests (role-change +
  key-rotation hook isolation)
- `test_auth_guards.py` — 12 tests (table + ranks + construction
  validation + logout-public)
- `test_apikey_middleware_rbac.py` — 7 tests (RBAC matrix +
  rotation header)
- `test_auth_management_routes.py` — 5 tests (logout + admin
  revoke + session events read)
- `test_per_route_admin_guards.py` — 5 tests (editor → 403 / admin
  → ok on guarded routes)
- Frontend `client.test.ts` — 3 tests (rotation header consumption
  on 200 + no-header + 4xx)

Total new: 58 backend + 3 frontend = 61.

## Verification

- `cd frontend && npm run test:run` — **1128 passed** (1125 baseline + 3 new) ✓
- `cd backend && uv run pytest` — **2257 passed**, 1 skipped, 1 xfailed (2199 baseline + 58 new) ✓
- `just build` — vue-tsc + vite clean ✓

## Plan-vs-reality adaptations

- `create_user_role` actual signature is `(api_key, label, role,
  user_id) -> str` (returns role_id; takes api_key as first
  positional). Plan tests adapted to use `generate_api_key()` to
  mint keys.
- Logout route revokes by `user_id`, not by token, because the
  middleware rotates tokens per-request — by the time the logout
  handler runs, the auth-header bearer may already be in
  `rotated_from_token`. Revoking by user_id covers both states.
- `/admin/auth/logout` added to `PUBLIC_PATHS` so viewer-role
  principals can logout (otherwise the coarse `POST /admin/ →
  editor` rule would 403 them before the handler runs).
- `mockResponse` helper in pre-existing `frontend/src/services/
  __tests__/api.test.ts` updated to include `headers: new
  Headers()` — needed because the new client.ts rotation hook
  calls `response.headers.get(...)` on every response.
- Audit found only 2 actually-sensitive routes for per-route
  admin guards (not 5 from the plan's candidate list). Existing
  RBAC routes already use a `require_role("admin")` dependency
  pattern; cliproxy install routes don't exist as named.

## Deferred

- Observability UI for `session_events` (operator-facing dashboard
  reading `/admin/auth/session-events`) → v0.5.13+ candidate.
- OAuth refresh — operator auth doesn't use OAuth; ai-accounts
  sidecar owns AI-backend OAuth refresh. Out of scope by design.
- `purge_expired_sessions` is still hard DELETE (inconsistent
  with soft-delete `revoke_session`). Pre-existing function;
  rename to `expire_sessions` + soft-delete in a follow-up.
- `get_session_by_token` does a `SELECT * FROM sessions` full-table
  scan per authenticated request. Acceptable for SQLite + low
  session count; flag for production-scale follow-up.
- MFA, per-resource ACLs, frontend session-management UI, CSRF
  tokens → out of scope by design.

## Next milestone

**v0.5.13** — B (deploy story): production gunicorn config, env-var
hygiene, secrets management, deploy/release runbook. Different
surface; fresh brainstorming pass.

After B: D (rate limiting), E (backups). Per the original sequencing.
