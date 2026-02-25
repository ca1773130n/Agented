# Technology Stack

**Analysis Date:** 2026-02-25

## Languages

**Primary:**
- Python 3.10+ — Backend API server (`backend/`)
- TypeScript 5.4 — Frontend SPA (`frontend/src/`)

**Secondary:**
- HTML/CSS — Frontend templates and styles (`frontend/src/style.css`, `frontend/src/App.vue`)

## Runtime

**Backend Environment:**
- Python >= 3.10 (required by `pyproject.toml`)
- Managed via `uv` (replaces pip/venv; lockfile: `backend/uv.lock`)

**Frontend Environment:**
- Node.js (version unspecified; npm required)
- Package manager: `npm`; lockfile: `frontend/package-lock.json`

## Frameworks

**Core Backend:**
- `Flask` 2.x (`>=2.2.3,<3.0`) — WSGI web framework (`backend/app/__init__.py`)
- `flask-openapi3` 3.x — OpenAPI/Swagger spec generation; uses `OpenAPI()` app factory and `APIBlueprint` (replaces standard `Flask()`/`Blueprint`); docs at `/docs` (`backend/app/__init__.py`)
- `flask-cors` 4.x — CORS middleware with configurable allowed origins (`backend/app/__init__.py`)

**Core Frontend:**
- `vue` 3.5 — Component framework (`frontend/src/main.ts`)
- `vue-router` 4.6 — SPA routing with `createWebHistory` (`frontend/src/router/`)
- `vite` 7.x — Build tool and dev server (`frontend/vite.config.ts`)
- `vue-tsc` 3.x — TypeScript type-checking for Vue (runs as part of `npm run build`)

**Data Validation:**
- `pydantic` 2.x — Request/response models for all API routes (`backend/app/models/`)

**Testing:**
- `pytest` 9.x (backend) — `backend/` tests; `uv run pytest`
- `vitest` 4.x (frontend) — unit tests with `happy-dom` environment (`frontend/vitest.config.ts`)
- `@vue/test-utils` 2.x — Vue component testing utilities
- `@playwright/test` + `playwright` 1.58 — End-to-end tests (`frontend/playwright.config.ts`)

**Build/Dev:**
- `just` — Task runner (`justfile`); wraps all dev, build, and deploy commands
- `uv` — Python package manager and virtual environment (`backend/pyproject.toml`)
- `@vitejs/plugin-vue` 6.x — Vite plugin for `.vue` SFC compilation
- `rollup` (via Vite) — Production bundler with manual chunk splitting (`frontend/vite.config.ts`)

## Key Dependencies

**Backend Critical:**
- `gunicorn` 21.x — Production WSGI server; used when running `python run.py` in non-debug mode (`backend/run.py`)
- `litellm` 1.81+ — LLM abstraction layer for chat completions via Claude/Codex/Gemini; used in `conversation_streaming.py`, `cliproxy_chat_service.py`, `sketch_routing_service.py`
- `APScheduler` 3.10 — Background cron-based job scheduler for triggers, monitoring, session collection, repo sync (`backend/app/services/scheduler_service.py`)
- `pyyaml` 6.x — YAML parsing for CLIProxyAPI config, plugin frontmatter, harness files (`backend/app/services/cliproxy_manager.py`, `backend/app/utils/plugin_format.py`)
- `httpx` 0.28+ — Async/sync HTTP client for CLIProxyAPI health checks and OpenAI-compatible API calls (`backend/app/services/cliproxy_chat_service.py`, `backend/app/services/cliproxy_manager.py`)
- `watchdog` 6.x — Filesystem event monitoring for plugin file sync and team directory watching (`backend/app/services/plugin_file_watcher.py`, `backend/app/services/team_monitor_service.py`)
- `cryptography` 41.x — AES/PBKDF2 cipher operations for decoding Chrome-stored OAuth tokens (`backend/app/services/cliproxy_manager.py`)
- `playwright` 1.40+ — Headless Chromium for OAuth login flows in CLIProxyAPI (`backend/app/services/cliproxy_manager.py`)
- `pytz` 2023.3 — Timezone handling for APScheduler and cron triggers (`backend/app/services/scheduler_service.py`)

**Frontend Critical:**
- `chart.js` 4.5 + `chartjs-adapter-date-fns` — Time-series usage charts (`frontend/src/components/monitoring/`)
- `@vue-flow/core` 1.48 + `@dagrejs/dagre` 2.x — Interactive directed graph canvas for workflow/team/org visualizations (`frontend/src/composables/useWorkflowCanvas.ts`, `useTeamCanvas.ts`, `useOrgCanvas.ts`)
- `marked` 17.x + `dompurify` 3.x — Markdown rendering with XSS sanitization (`frontend/src/`)
- `highlight.js` 11.x — Syntax highlighting in code blocks
- `streaming-markdown` 0.2 — Incremental markdown rendering during LLM streaming
- `vue-draggable-plus` 0.6 — Drag-and-drop list reordering (Kanban board)
- `@mcp-b/global` 1.5 — WebMCP polyfill for `navigator.modelContext` tool registration (`frontend/src/main.ts`, `frontend/src/webmcp/`)
- `@mcp-b/webmcp-types` 0.2 — TypeScript types for WebMCP W3C spec
- `date-fns` 4.x — Date formatting and manipulation
- `html-to-image` 1.x — Canvas export to PNG/JPEG

**Frontend DevDependencies:**
- `@vitest/coverage-v8` 4.x — Code coverage via V8
- `happy-dom` 20.x — Lightweight DOM implementation for unit tests
- `typescript` 5.4 — TypeScript compiler

## Database

- **SQLite** (Python stdlib `sqlite3`) — Single-file database at `backend/agented.db` (configurable via `AGENTED_DB_PATH` env var)
- Connection managed by `backend/app/db/connection.py` — context manager `get_connection()` with `row_factory = sqlite3.Row`, foreign keys enabled, 5s busy timeout
- No ORM; all queries are raw SQL defined in `backend/app/db/` module files (one file per domain entity)
- Schema migrations in `backend/app/db/migrations.py`; auto-applied at startup via `init_db()`

## Configuration

**Environment Variables:**
- `AGENTED_DB_PATH` — Override SQLite file path (default: `backend/agented.db`)
- `SECRET_KEY` — Flask session secret (auto-generated with `secrets.token_hex(32)` if unset)
- `CORS_ALLOWED_ORIGINS` — Comma-separated allowed CORS origins (default: `*`)
- `GITHUB_WEBHOOK_SECRET` — HMAC-SHA256 secret for GitHub webhook signature verification
- `ANTHROPIC_API_KEY` — Direct Anthropic API key (fallback when CLIProxyAPI unavailable)
- `CLAUDE_PLUGIN_ROOT` — Path to GRD CLI binary directory

**No `.env` file detected** — environment variables must be set in the shell or process environment.

**Build:**
- Frontend: `npm run build` → `vue-tsc -b && vite build` → outputs to `frontend/dist/`
- Backend: no build step; runs directly via `uv run python run.py`
- Rollup chunk splitting configured in `frontend/vite.config.ts`: vendor-chart, vendor-highlight, vendor-vue-flow, vendor-markdown, vendor-core

## Platform Requirements

**Development:**
- macOS or Linux (PTY service uses `os.fork()` and `pty` module — POSIX-only)
- `just` task runner
- `uv` Python package manager
- Node.js + `npm`
- `gh` CLI (GitHub CLI) — required for GitHub repo clone/push/PR operations
- `git` — required for worktree management and repo sync
- Optional: `claude`, `opencode`, `codex`, `gemini` CLI binaries (backend detection service probes for these at runtime)

**Production:**
- gunicorn serves backend on port 20000
- Vite dev server or static file server serves frontend on port 3000
- Vite proxy forwards `/api/*`, `/admin/*`, `/health/*`, `/docs/*`, `/openapi/*` to backend at `127.0.0.1:20000`

---

*Stack analysis: 2026-02-25*
