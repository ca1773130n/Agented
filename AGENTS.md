# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hive is a bot automation platform with a Flask backend and Vue.js frontend. It manages AI-powered bots that execute CLI tools (Claude, OpenCode) in response to webhooks, GitHub events, schedules, or manual triggers. The platform also provides organization management for products, projects, teams, agents, plugins, skills, hooks, commands, and rules.

## Development Commands

```bash
# Bootstrap (fresh clone — installs just, uv, node if missing)
bash scripts/setup.sh

# Setup (prerequisites already installed)
just setup                # Install all dependencies (backend + frontend)
just setup-backend        # cd backend && uv sync
just setup-frontend       # cd frontend && npm install

# Development (run in separate terminals)
just dev-backend          # Backend on http://127.0.0.1:20000 (debug mode)
just dev-frontend         # Frontend on http://localhost:3000

# Build & Deploy
just build                # Build frontend for production
just deploy               # Build + start both servers
just kill                 # Kill processes on ports 3000/20000

# Backend tests
cd backend && uv run pytest                          # Run all tests
cd backend && uv run pytest tests/test_github_webhook.py  # Single test file
cd backend && uv run pytest tests/test_github_webhook.py::test_name -v  # Single test

# Frontend tests
cd frontend && npm run test:run              # Run all tests once
cd frontend && npm test                      # Watch mode
cd frontend && npm run test:coverage         # With coverage

# Formatting
cd backend && uv run black .                 # Format Python (line-length=100)
```

API docs available at http://localhost:20000/docs (Swagger UI via flask-openapi3).

## Architecture

### Backend (`backend/`)

Flask app using the **flask-openapi3** library (not vanilla Flask). Routes use `APIBlueprint` instead of `Blueprint`, and the app is created with `OpenAPI()` instead of `Flask()`.

**Key patterns:**
- **App factory**: `app/__init__.py` — `create_app()` initializes DB, scheduler, and registers all blueprints
- **Database**: `app/database.py` — Raw SQLite with `get_connection()` context manager (no ORM). All CRUD functions are defined directly in this file. DB auto-initializes tables and seeds predefined bots on startup
- **Models**: `app/models/` — Pydantic v2 models for request/response validation (not DB models)
- **Routes**: `app/routes/` — API blueprints registered via `register_blueprints()` in `routes/__init__.py`
- **Services**: `app/services/` — Business logic. `ExecutionService` runs bots via subprocess (CLI invocations of `claude` or `opencode`) with real-time log streaming via threads

**Entity ID conventions**: Prefixed random IDs — `bot-`, `agent-`, `conv-`, `team-`, `prod-`, `proj-`, `plug-` (all 6-char random suffix)

**Two predefined bots** are seeded automatically and cannot be deleted:
- `bot-security` — Weekly Security Audit (webhook trigger)
- `bot-pr-review` — PR Review (GitHub trigger)

**Route prefix conventions**: Admin/management routes use `/admin/*`, public API routes use `/api/*`

### Frontend (`frontend/`)

Vue 3 SPA with TypeScript. Uses Vue Router 4 with `createWebHistory` for navigation. Routes are defined in `src/router/` with per-domain route files, global navigation guards for entity validation, and `<router-view>` in `App.vue`.

**Key patterns:**
- **API client**: `src/services/api.ts` — All API types and fetch functions. Each domain has its own API object (e.g., `botApi`, `agentApi`, `teamApi`)
- **No state management library** — Component-local state with Vue `ref`/`reactive`, parent-child via props/emits, cross-cutting via `provide`/`inject` (e.g., `showToast`)
- **SSE streaming**: Real-time execution logs and conversation streams use `EventSource`
- **Charting**: Chart.js for data visualization (FindingsChart, PrHistoryChart)
- **Testing**: Vitest + happy-dom + @vue/test-utils. Setup in `src/test/setup.ts`

### Frontend-Backend Communication

Vite dev server proxies `/api/*`, `/admin/*`, `/health/*`, `/docs/*`, `/openapi/*` to the backend at `127.0.0.1:20000`.

### Bot Execution Flow

1. Trigger arrives (webhook, GitHub event, schedule, or manual)
2. `ExecutionService.dispatch_*` matches payload to bots
3. Bot prompt template is rendered with placeholders (`{paths}`, `{message}`, `{pr_url}`, etc.)
4. CLI command is built (`claude -p ...` or `opencode run --prompt ...`)
5. Process runs via `subprocess.Popen` with threaded stdout/stderr streaming
6. Execution status tracked in-memory with 5-minute TTL after completion

## Verification

Always verify **both builds and tests** before declaring any task complete:

```bash
# Frontend build (includes vue-tsc type checking + vite build)
just build

# Backend tests
cd backend && uv run pytest

# Frontend tests
cd frontend && npm run test:run
```

All three must pass with zero errors. Do not skip the build step — type errors caught by `vue-tsc` will not surface in unit tests alone.

## Conventions

- Python formatting: Black with `line-length=100`, target `py310`
- Backend tests use `isolated_db` fixture (auto-patches `DB_PATH` to temp file per test)
- Frontend uses Geist font family and a dark theme with CSS custom properties defined in `App.vue`

## GRD Planning

Project roadmap, codebase analysis, and phase plans live in `.planning/`:

- `.planning/config.json` — GRD configuration
- `.planning/codebase/` — Architecture, stack, structure, conventions, testing, integrations, concerns
- `.planning/milestones/` — Roadmaps, requirements, and phase docs (v0.2.x, v0.3.0 complete; v0.4.0 active)
