# v0.5.14 State

Status: COMPLETE — pending Codex review + merge.

## Shipped

### Layer 1 — coarse defaults (`app_litestar/middleware.py`)

- `_RATE_LIMITS` extended to `(method, prefix, limit, window)` with
  method wildcard `*`.
- New default rules: GET `/api/*` = 60/min, POST/PUT/PATCH `/api/*`
  = 30/min, DELETE `/api/*` = 15/min, any-method `/admin/*` = 30/min.
- Existing webhook rules (POST `/api/webhooks/github` = 30/min,
  POST `/` = 20/10s) preserved at the front of the table.
- Defaults are `_int_env`-read at module load with safe fallback on
  parse error + WARN log.

### Layer 2 — per-route guard (`app_litestar/rate_limit_guard.py`)

- `requires_rate_limit(limit, window_seconds)` factory. Validates
  positive args at construction. Registers `(method, path) →
  (limit, window)` on first request via lazy registry.
- Exposed: `get_override`, `register_override`, `clear_overrides`.
- Middleware consults the registry before falling through to the
  coarse table.

### Layer 3 — keying (`app_litestar/middleware.py:_resolve_rate_key`)

- Reads `scope["state"]["principal"]["user_id"]` (set by
  `ApiKeyMiddleware` in v0.5.12). Authed → `("user", user_id)`.
  Unauthed → `("ip", client_ip)`.
- Limiter key: `(f"{kind}:{val}", path)` so the same user has
  separate budgets per path (login vs API call).

### Layer 4 — config (`scripts/check_env.py` + `.env.example`)

- Added 4 OPTIONAL_VARS: `RATE_LIMIT_API_GET_PER_MIN` (60),
  `RATE_LIMIT_API_WRITE_PER_MIN` (30), `RATE_LIMIT_ADMIN_PER_MIN`
  (30), `RATE_LIMIT_LOGIN_PER_MIN` (informational; actual override
  hardcoded at 5).
- `.env.example` documents them in a "Rate limiting (v0.5.14)"
  section.

### Per-route overrides applied

| Route | Guard |
|---|---|
| POST `/api/auth/login` | `requires_rate_limit(5, 60.0)` |
| POST `/api/auth/signup` | `requires_rate_limit(5, 60.0)` |
| POST `/api/auth/forgot-password` | `requires_rate_limit(3, 60.0)` |
| POST `/api/auth/reset-password` | `requires_rate_limit(5, 60.0)` |
| POST `/api/setup/bundle-install` | `requires_rate_limit(10, 3600.0)` (admin + rate) |
| POST `/admin/backends/:id/install` | `requires_rate_limit(10, 3600.0)` (admin + rate) |

### Tests added

- `test_rate_limit_guard.py` — 3 tests (factory validation, register/lookup, clear).
- `test_rate_limit_v2.py` — 13 tests (per-IP, per-key, key isolation,
  same-user-different-IP, override beats default, 429 shape, env
  parser, webhook regression, health bypass).
- `test_check_env.py` — `_clean_env` fixture extended for 4 new vars.
- Total new: 16 backend tests.

## Verification

- `cd frontend && npm run test:run` — **1128 passed** (no change) ✓
- `cd backend && uv run pytest` — pending full-suite confirmation
- `just build` — vue-tsc + vite clean ✓

## Plan-vs-reality adaptations

- Per-route override registration is lazy (registers on first
  request, not at app startup). Documented in the spec; trade-off
  is one coarse-rule pass-through on the very first request to
  each guarded route.

## Out of scope (deferred)

- Distributed limiter (Redis) — workers=1 keeps in-memory safe.
- Token-bucket / sliding window — fixed window suffices.
- Operator UI for current consumption.
- Eager startup walker that populates the override registry from
  Litestar's route table at boot (cleaner than lazy first-request
  registration; deferred).

## Next milestone

**v0.5.15** — E (backups): periodic SQLite snapshot, off-site
storage option, restore procedure, retention policy.
