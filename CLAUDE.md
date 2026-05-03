# CLAUDE.md

**Agented** is a harness-engineering meta-layer for AI coding harnesses
— Claude Code, Codex, Gemini CLI, OpenCode, and similar tools. It
provides end-to-end product development with autonomous agents:
orchestrating multi-harness workflows, managing accounts/credentials,
coordinating products → projects → teams → agents, and wiring
plugins/skills/hooks/commands/rules into the harnesses themselves.

The Litestar backend drives the harnesses via `subprocess.Popen` and
SSE-streams their output. The Vue 3 frontend is the operator console.
A sidecar (ai-accounts) owns AI-backend identity. Triggers (webhooks,
GitHub events, schedules, manual) are the delivery mechanism, not the
product — the product is the autonomous-agent workflow on top.

## Environment variables

| Variable | Where | Default | Notes |
|---|---|---|---|
| `AI_ACCOUNTS_API_KEY` | sidecar | unset → reuse Flask admin key | Explicit token used by the ai-accounts Litestar sidecar (`backend/scripts/run_ai_accounts.py`). When unset, the sidecar reads the admin key from `agented.db`'s `user_roles` table. |
| `AI_ACCOUNTS_ALLOW_NOAUTH` | sidecar | unset (refuse) | Set to `1` only when running the sidecar locally without any keyed identity (e.g. immediately after `just reset`). The sidecar refuses to start otherwise — the previous "silent NoAuth fallback" exposed it through Vite's `/api/v1` proxy. |
| `VITE_HOST` | frontend dev server | `127.0.0.1` | Bind interface for `vite dev`. Localhost-only by default. Set to `0.0.0.0` to demo from another device — also set `AI_ACCOUNTS_API_KEY` and `VITE_ALLOWED_HOSTS` in that case. |
| `VITE_ALLOWED_HOSTS` | frontend dev server | unset (any host) | Comma-separated allowlist for the `Host` header. Use with `VITE_HOST=0.0.0.0` for LAN access without permitting arbitrary hostnames. |

## ai-accounts dev linking

`backend/pyproject.toml` and `frontend/package.json` ship with **local
`file:` pins** at `../../ai-accounts/packages/*` so iteration on the
sibling `ai-accounts` repo doesn't require publishing every change.
The `just dev-link-ai-accounts` recipe is the inverse path
(local→local) and is redundant in this configuration; switching back
to registry pins for release flips both pieces in one direction.

Edits to `ai-accounts/packages/*/src` are invisible to the frontend
until `npm run build` regenerates `dist/`. `just deploy` does this
automatically.

## Commands

```bash
# Setup
bash scripts/setup.sh            # Bootstrap (fresh clone)
just setup                       # Install all deps
just dev-backend                 # Backend on :20000
just dev-frontend                # Frontend on :3000
just build                       # Production build (vue-tsc + vite)
just deploy                      # Build + start both
just kill                        # Kill ports 3000/20000/20001 (port-scoped only — never pkill vite/node)

# Tests
cd backend && uv run pytest                                  # All backend
cd backend && uv run pytest tests/test_file.py::test_name -v # Single test
cd frontend && npm run test:run                              # All frontend
cd frontend && npm run test:coverage                         # With coverage gate

# Format
cd backend && uv run ruff format .   # line-length=100, py310
```

## Verification

All three must pass before any task is complete:

1. `just build` (vue-tsc type checking + vite build)
2. `cd backend && uv run pytest`
3. `cd frontend && npm run test:run`

## Architecture

**Backend** (`backend/`) — Litestar served by `gunicorn -c gunicorn.conf.py`
(UvicornWorker, workers=1) on `:20000`. Flask was retired in wave 80;
the Litestar app is the canonical surface. The ai-accounts sidecar
(`scripts/run_ai_accounts.py`) on `:20001` owns AI-backend
accounts/credentials/login flows.

- `app_litestar/main.py` — `create_app()` factory; registers route
  handlers, middleware, exception handlers, CORS, on_startup/shutdown.
- `app_litestar/routes/*.py` — `Router(...)` definitions. `/admin/*`
  management, `/api/*` public, `/health/*` open.
- `app_litestar/middleware.py` — SecurityHeaders (CSP/HSTS/X-Frame),
  RateLimit, RequestContext (request-id + current-user contextvars),
  ApiKey (global X-API-Key + bearer-session gate), RequestLogging.
- `app_litestar/exception_handlers.py` — JSON ErrorResponse shape +
  SPA 404 fallback. Exception handler registry covers
  `IntegrityError`, `OperationalError`, `ValueError`, and a
  last-resort `Exception` handler that pipes to `error_capture`.
- `app_litestar/lifecycle.py` — DB seed, backend detection, scheduler
  init + periodic jobs, queue/message-bus dispatchers, CLIProxy
  bootstrap. Honors `AGENTED_LITESTAR_SKIP_STARTUP=1` for tests.
- `app/database.py` — Raw SQLite, `get_connection()` context manager,
  no ORM.
- `app/services/` — Business logic. `ExecutionService` runs CLI
  harnesses via `subprocess.Popen`.
- `app/models/` — Pydantic v2 + msgspec Struct request/response.
- `app/__init__.py` — empty package marker (Flask factory deleted in
  wave 82).
- Entity IDs: prefixed random (`bot-`, `agent-`, `conv-`, `team-`,
  `prod-`, `proj-`, `plug-` + 6-char suffix).
- Predefined bots (cannot delete): `bot-security`, `bot-pr-review`.

**Frontend** (`frontend/`) — Vue 3 + TypeScript, Vue Router 4.

- `src/services/api.ts` — API client with per-domain objects
  (`botApi`, `agentApi`, etc.).
- No state library — `ref`/`reactive`, props/emits, `provide`/`inject`.
- SSE streaming for real-time logs/conversations via Litestar `Stream`.
- Vitest + happy-dom + @vue/test-utils.
- Vite proxies `/api/v1/*` → `:20001` (sidecar) and
  `/api/*`, `/admin/*`, `/health/*`, `/schema/*` → `:20000` (Litestar).

## Conventions

- Python: Ruff `line-length=100`, target `py310`.
- Backend tests: `isolated_db` fixture (patches `DB_PATH` to temp
  file). For Litestar route tests, the TestClient logger doesn't
  propagate to `caplog` reliably — use a `monkeypatch` spy on
  `module.logger.warning` instead.
- Frontend: Geist font, dark theme, CSS custom props in `App.vue`.
- Tests for the tour state machine maintain ≥ 90% branch coverage on
  `useTourMachine.ts` (enforced by `vitest.config.ts` thresholds).

## Context-Mode MCP tools

Use these for large outputs instead of Bash/Read:

```
ctx_execute(language, code)            # Run code in sandbox (>20 lines of output)
ctx_execute_file(path, language, code) # Analyze a file (instead of Read for analysis)
ctx_batch_execute(commands, queries)   # Multiple commands in one call
ctx_search(query)                      # Semantic search across indexed content
ctx_fetch_and_index(url)               # Fetch URL and index
ctx_doctor() / ctx_stats() / ctx_upgrade()
```

Bash is reserved for short-output operations: `git`, `mkdir`, `rm`,
`mv`, navigation. Use `Read` only when the file is going to be `Edit`'d
afterward.

## GRD planning

`.planning/` contains roadmaps, codebase analysis, and phase plans:

- `.planning/config.json` — GRD config.
- `.planning/milestones/v0.5.0/` — onboarding tour, complete.
- `.planning/milestones/v0.5.1/` — patch: OB-24 anchor + coverage gate.
- `.planning/milestones/v0.5.2/` — silent-failure cleanup pass 1.
- `.planning/milestones/v0.5.3/` — silent-failure cleanup pass 2 +
  modal-interaction E2E.
- `.planning/milestones/v0.6.0/` — TBD.

## Tooling

- **GRD**: `/grd:progress`, `/grd:plan-phase`, `/grd:execute-phase`,
  `/grd:verify-phase`.
- **HarnessSync**: `/harness-sync:sync`, `/harness-sync:sync-status`.
- **Superpowers**: `/superpowers:brainstorming`,
  `/superpowers:writing-plans`, `/superpowers:executing-plans`,
  `/superpowers:test-driven-development`.
- **Simplify**: `/simplify` — post-change code review.
- **Commit**: `/commit-commands:commit`, `/commit-commands:commit-push-pr`.

<!-- Managed by HarnessSync -->
# Rules synced from Claude Code

<!-- [harness-sync:start source=CLAUDE.md line=1-162] -->
# [Project rules from CLAUDE.md]

# CLAUDE.md

**Agented** is a harness-engineering meta-layer for AI coding harnesses
— Claude Code, Codex, Gemini CLI, OpenCode, and similar tools. It
provides end-to-end product development with autonomous agents:
orchestrating multi-harness workflows, managing accounts/credentials,
coordinating products → projects → teams → agents, and wiring
plugins/skills/hooks/commands/rules into the harnesses themselves.

The Litestar backend drives the harnesses via `subprocess.Popen` and
SSE-streams their output. The Vue 3 frontend is the operator console.
A sidecar (ai-accounts) owns AI-backend identity. Triggers (webhooks,
GitHub events, schedules, manual) are the delivery mechanism, not the
product — the product is the autonomous-agent workflow on top.

## Environment variables

| Variable | Where | Default | Notes |
|---|---|---|---|
| `AI_ACCOUNTS_API_KEY` | sidecar | unset → reuse Flask admin key | Explicit token used by the ai-accounts Litestar sidecar (`backend/scripts/run_ai_accounts.py`). When unset, the sidecar reads the admin key from `agented.db`'s `user_roles` table. |
| `AI_ACCOUNTS_ALLOW_NOAUTH` | sidecar | unset (refuse) | Set to `1` only when running the sidecar locally without any keyed identity (e.g. immediately after `just reset`). The sidecar refuses to start otherwise — the previous "silent NoAuth fallback" exposed it through Vite's `/api/v1` proxy. |
| `VITE_HOST` | frontend dev server | `127.0.0.1` | Bind interface for `vite dev`. Localhost-only by default. Set to `0.0.0.0` to demo from another device — also set `AI_ACCOUNTS_API_KEY` and `VITE_ALLOWED_HOSTS` in that case. |
| `VITE_ALLOWED_HOSTS` | frontend dev server | unset (any host) | Comma-separated allowlist for the `Host` header. Use with `VITE_HOST=0.0.0.0` for LAN access without permitting arbitrary hostnames. |

## ai-accounts dev linking

`backend/pyproject.toml` and `frontend/package.json` ship with **local
`file:` pins** at `../../ai-accounts/packages/*` so iteration on the
sibling `ai-accounts` repo doesn't require publishing every change.
The `just dev-link-ai-accounts` recipe is the inverse path
(local→local) and is redundant in this configuration; switching back
to registry pins for release flips both pieces in one direction.

Edits to `ai-accounts/packages/*/src` are invisible to the frontend
until `npm run build` regenerates `dist/`. `just deploy` does this
automatically.

## Commands

```bash
# Setup
bash scripts/setup.sh            # Bootstrap (fresh clone)
just setup                       # Install all deps
just dev-backend                 # Backend on :20000
just dev-frontend                # Frontend on :3000
just build                       # Production build (vue-tsc + vite)
just deploy                      # Build + start both
just kill                        # Kill ports 3000/20000/20001 (port-scoped only — never pkill vite/node)

# Tests
cd backend && uv run pytest                                  # All backend
cd backend && uv run pytest tests/test_file.py::test_name -v # Single test
cd frontend && npm run test:run                              # All frontend
cd frontend && npm run test:coverage                         # With coverage gate

# Format
cd backend && uv run ruff format .   # line-length=100, py310
```

## Verification

All three must pass before any task is complete:

1. `just build` (vue-tsc type checking + vite build)
2. `cd backend && uv run pytest`
3. `cd frontend && npm run test:run`

## Architecture

**Backend** (`backend/`) — Litestar served by `gunicorn -c gunicorn.conf.py`
(UvicornWorker, workers=1) on `:20000`. Flask was retired in wave 80;
the Litestar app is the canonical surface. The ai-accounts sidecar
(`scripts/run_ai_accounts.py`) on `:20001` owns AI-backend
accounts/credentials/login flows.

- `app_litestar/main.py` — `create_app()` factory; registers route
  handlers, middleware, exception handlers, CORS, on_startup/shutdown.
- `app_litestar/routes/*.py` — `Router(...)` definitions. `/admin/*`
  management, `/api/*` public, `/health/*` open.
- `app_litestar/middleware.py` — SecurityHeaders (CSP/HSTS/X-Frame),
  RateLimit, RequestContext (request-id + current-user contextvars),
  ApiKey (global X-API-Key + bearer-session gate), RequestLogging.
- `app_litestar/exception_handlers.py` — JSON ErrorResponse shape +
  SPA 404 fallback. Exception handler registry covers
  `IntegrityError`, `OperationalError`, `ValueError`, and a
  last-resort `Exception` handler that pipes to `error_capture`.
- `app_litestar/lifecycle.py` — DB seed, backend detection, scheduler
  init + periodic jobs, queue/message-bus dispatchers, CLIProxy
  bootstrap. Honors `AGENTED_LITESTAR_SKIP_STARTUP=1` for tests.
- `app/database.py` — Raw SQLite, `get_connection()` context manager,
  no ORM.
- `app/services/` — Business logic. `ExecutionService` runs CLI
  harnesses via `subprocess.Popen`.
- `app/models/` — Pydantic v2 + msgspec Struct request/response.
- `app/__init__.py` — empty package marker (Flask factory deleted in
  wave 82).
- Entity IDs: prefixed random (`bot-`, `agent-`, `conv-`, `team-`,
  `prod-`, `proj-`, `plug-` + 6-char suffix).
- Predefined bots (cannot delete): `bot-security`, `bot-pr-review`.

**Frontend** (`frontend/`) — Vue 3 + TypeScript, Vue Router 4.

- `src/services/api.ts` — API client with per-domain objects
  (`botApi`, `agentApi`, etc.).
- No state library — `ref`/`reactive`, props/emits, `provide`/`inject`.
- SSE streaming for real-time logs/conversations via Litestar `Stream`.
- Vitest + happy-dom + @vue/test-utils.
- Vite proxies `/api/v1/*` → `:20001` (sidecar) and
  `/api/*`, `/admin/*`, `/health/*`, `/schema/*` → `:20000` (Litestar).

## Conventions

- Python: Ruff `line-length=100`, target `py310`.
- Backend tests: `isolated_db` fixture (patches `DB_PATH` to temp
  file). For Litestar route tests, the TestClient logger doesn't
  propagate to `caplog` reliably — use a `monkeypatch` spy on
  `module.logger.warning` instead.
- Frontend: Geist font, dark theme, CSS custom props in `App.vue`.
- Tests for the tour state machine maintain ≥ 90% branch coverage on
  `useTourMachine.ts` (enforced by `vitest.config.ts` thresholds).

## Context-Mode MCP tools

Use these for large outputs instead of Bash/Read:

```
ctx_execute(language, code)            # Run code in sandbox (>20 lines of output)
ctx_execute_file(path, language, code) # Analyze a file (instead of Read for analysis)
ctx_batch_execute(commands, queries)   # Multiple commands in one call
ctx_search(query)                      # Semantic search across indexed content
ctx_fetch_and_index(url)               # Fetch URL and index
ctx_doctor() / ctx_stats() / ctx_upgrade()
```

Bash is reserved for short-output operations: `git`, `mkdir`, `rm`,
`mv`, navigation. Use `Read` only when the file is going to be `Edit`'d
afterward.

## GRD planning

`.planning/` contains roadmaps, codebase analysis, and phase plans:

- `.planning/config.json` — GRD config.
- `.planning/milestones/v0.5.0/` — onboarding tour, complete.
- `.planning/milestones/v0.5.1/` — patch: OB-24 anchor + coverage gate.
- `.planning/milestones/v0.5.2/` — silent-failure cleanup pass 1.
- `.planning/milestones/v0.5.3/` — silent-failure cleanup pass 2 +
  modal-interaction E2E.
- `.planning/milestones/v0.6.0/` — TBD.

## Tooling

- **GRD**: `/grd:progress`, `/grd:plan-phase`, `/grd:execute-phase`,
  `/grd:verify-phase`.
- **HarnessSync**: `/harness-sync:sync`, `/harness-sync:sync-status`.
- **Superpowers**: `/superpowers:brainstorming`,
  `/superpowers:writing-plans`, `/superpowers:executing-plans`,
  `/superpowers:test-driven-development`.
- **Simplify**: `/simplify` — post-change code review.
- **Commit**: `/commit-commands:commit`, `/commit-commands:commit-push-pr`.

<!-- [harness-sync:end] -->

---
*Last synced by HarnessSync: 2026-05-03 00:23:22 UTC*
<!-- End HarnessSync managed content -->