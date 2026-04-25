<!-- Managed by HarnessSync -->
# Project Conventions (synced from Claude Code)

<!-- [harness-sync:start source=CLAUDE.md line=1-97] -->
# [Project rules from CLAUDE.md]

# CLAUDE.md

Agented — bot automation platform. Flask backend + Vue 3 frontend. Manages AI bots that execute CLI tools (Claude, OpenCode) via webhooks, GitHub events, schedules, or manual triggers. Also manages products, projects, teams, agents, plugins, skills, hooks, commands, and rules.

## Environment variables

| Variable | Where | Default | Notes |
|---|---|---|---|
| `AI_ACCOUNTS_API_KEY` | sidecar | unset → reuse Flask admin key | Explicit token used by the ai-accounts Litestar sidecar (`backend/scripts/run_ai_accounts.py`). When unset the sidecar reads the Flask admin key from `agented.db`'s `user_roles` table. |
| `AI_ACCOUNTS_ALLOW_NOAUTH` | sidecar | unset (refuse) | Set to `1` only when running the sidecar locally without any keyed identity (e.g. immediately after `just reset`). The previous "silent NoAuth fallback" exposed the sidecar through Vite's `/api/v1` proxy; the sidecar now exits unless this flag is explicit. |
| `VITE_HOST` | frontend dev server | `127.0.0.1` | Bind interface for `vite dev`. Localhost-only by default — set to `0.0.0.0` to demo from another device, in which case you should also set `AI_ACCOUNTS_API_KEY` and `VITE_ALLOWED_HOSTS`. |
| `VITE_ALLOWED_HOSTS` | frontend dev server | unset (any host) | Comma-separated allowlist for the `Host` header. Used together with `VITE_HOST=0.0.0.0` for LAN access without permitting arbitrary hostnames. |

## ai-accounts dev linking

`backend/pyproject.toml` and `frontend/package.json` currently ship with **local `file:` pins** at `../../ai-accounts/packages/*` so iteration on the sibling `ai-accounts` repo doesn't require publishing every change. The `just dev-link-ai-accounts` recipe is the inverse path — it overwrites the same pins from local back to local — and is redundant in this configuration; switching back to registry pins for release flips both pieces in one direction.

## Commands

```bash
# Setup
bash scripts/setup.sh            # Bootstrap (fresh clone)
just setup                       # Install all deps
just dev-backend                 # Backend on :20000
just dev-frontend                # Frontend on :3000
just build                       # Production build (vue-tsc + vite)
just deploy                      # Build + start both
just kill                        # Kill ports 3000/20000/20001

# Tests
cd backend && uv run pytest                                           # All backend
cd backend && uv run pytest tests/test_file.py::test_name -v          # Single test
cd frontend && npm run test:run                                       # All frontend

# Format
cd backend && uv run ruff format .    # line-length=100, py310
```

## Verification

All three must pass before any task is complete:
1. `just build` (vue-tsc type checking + vite build)
2. `cd backend && uv run pytest`
3. `cd frontend && npm run test:run`

## Architecture

**Backend** (`backend/`) — Flask via **flask-openapi3** (uses `APIBlueprint`, `OpenAPI()`) on :20000, plus a Litestar sidecar (`scripts/run_ai_accounts.py`) on :20001 that owns AI-backend accounts/credentials/login flows.
- `app/__init__.py` — `create_app()` factory (DB, scheduler, blueprints)
- `app/database.py` — Raw SQLite, `get_connection()` context manager, no ORM
- `app/models/` — Pydantic v2 request/response validation
- `app/routes/` — `APIBlueprint` routes; `/admin/*` management, `/api/*` public
- `app/services/` — Business logic; `ExecutionService` runs CLI via `subprocess.Popen`
- Entity IDs: prefixed random (`bot-`, `agent-`, `conv-`, `team-`, `prod-`, `proj-`, `plug-` + 6-char suffix)
- Predefined bots (cannot delete): `bot-security`, `bot-pr-review`

**Frontend** (`frontend/`) — Vue 3 + TypeScript, Vue Router 4
- `src/services/api.ts` — API client with per-domain objects (`botApi`, `agentApi`, etc.)
- No state library — `ref`/`reactive`, props/emits, `provide`/`inject`
- SSE streaming for real-time logs/conversations
- Vitest + happy-dom + @vue/test-utils
- Vite proxies `/api/v1/*` to `:20001` (sidecar) and `/api/*`, `/admin/*`, `/health/*`, `/docs/*`, `/openapi/*` to `:20000` (Flask)

## Conventions

- Python: Ruff `line-length=100`, target `py310`
- Backend tests: `isolated_db` fixture (patches `DB_PATH` to temp file)
- Frontend: Geist font, dark theme, CSS custom props in `App.vue`

## Context-Mode MCP Tools

Use for large output operations instead of Bash/Read:

```
ctx_execute(language, code)            # Run code in sandbox (use instead of Bash for >20 lines)
ctx_execute_file(path, language, code) # Analyze file (use instead of Read for analysis)
ctx_batch_execute(commands, queries)   # Multiple commands in one call
ctx_search(query)                      # Semantic search across indexed content
ctx_fetch_and_index(url)               # Fetch URL and index
ctx_doctor() / ctx_stats() / ctx_upgrade()
```

## GRD Planning

`.planning/` contains roadmaps, codebase analysis, and phase plans:
- `.planning/config.json` — GRD config
- `.planning/milestones/` — v0.2.x, v0.3.0 complete; v0.4.0 active

## Tooling

- **GRD**: `/grd:progress`, `/grd:plan-phase`, `/grd:execute-phase`, `/grd:verify-phase`
- **HarnessSync**: `/harness-sync:sync`, `/harness-sync:sync-status`
- **Superpowers**: `/superpowers:brainstorming`, `/superpowers:writing-plans`, `/superpowers:executing-plans`, `/superpowers:test-driven-development`
- **Simplify**: `/simplify` — post-change code review
- **Commit**: `/commit-commands:commit`, `/commit-commands:commit-push-pr`

<!-- [harness-sync:end] -->

---
*Last synced by HarnessSync: 2026-04-25 03:07:48 UTC*
<!-- End HarnessSync managed content -->

---
*Last synced by HarnessSync: 2026-03-19 13:07:40 UTC*
<!-- End HarnessSync managed content -->

---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*
<!-- End HarnessSync managed content -->

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-19 13:07:40 UTC*

---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*

<!-- User annotations (preserved by HarnessSync) -->


---
*Last synced by HarnessSync: 2026-03-14 04:34:55 UTC*
