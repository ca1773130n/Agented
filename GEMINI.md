<!-- Managed by HarnessSync -->
# Rules synced from Claude Code

# CLAUDE.md

**Agented** is a harness-engineering meta-layer for AI coding harnesses
— Claude Code, Codex, Gemini CLI, OpenCode, and similar tools. It provides
end-to-end product development with autonomous agents: orchestrating
multi-harness workflows, managing accounts/credentials, coordinating
products → projects → teams → agents, and wiring plugins/skills/hooks/
commands/rules into the harnesses themselves.

The Litestar backend drives the harnesses via `subprocess.Popen` and
SSE-streams their output. The Vue 3 frontend is the operator console. A
sidecar (ai-accounts) owns AI-backend identity. Triggers (webhooks, GitHub
events, schedules, manual) are the delivery mechanism, not the product —
the product is the autonomous-agent workflow on top.

## Environment variables

| Variable | Where | Default | Notes |
|---|---|---|---|
| `AI_ACCOUNTS_API_KEY` | sidecar | unset → reuse admin key | Token for the ai-accounts sidecar (`backend/scripts/run_ai_accounts.py`). When unset, reads the admin key from `agented.db`'s `user_roles` table. |
| `AI_ACCOUNTS_ALLOW_NOAUTH` | sidecar | unset (refuse) | Set to `1` only to run the sidecar locally with no keyed identity (e.g. just after `just reset`). Otherwise it refuses to start — prevents a silent NoAuth fallback through Vite's `/api/v1` proxy. |
| `VITE_HOST` | frontend dev | `127.0.0.1` | Bind interface for `vite dev`. Set `0.0.0.0` to demo from another device (also set `AI_ACCOUNTS_API_KEY` + `VITE_ALLOWED_HOSTS`). |
| `VITE_ALLOWED_HOSTS` | frontend dev | unset (any host) | Comma-separated `Host` allowlist. Use with `VITE_HOST=0.0.0.0` for LAN access without permitting arbitrary hostnames. |

## ai-accounts dev linking

`backend/pyproject.toml` and `frontend/package.json` ship with local `file:`
pins at `../../ai-accounts/packages/*` so iterating on the sibling
`ai-accounts` repo needs no publish. Edits to `ai-accounts/packages/*/src`
are invisible to the frontend until `npm run build` regenerates `dist/`;
`just deploy` does this automatically. (`just dev-link-ai-accounts` is the
redundant inverse path in this config; switching to registry pins is the
release flip.)

## Commands

```bash
bash scripts/setup.sh   # Bootstrap (fresh clone)
just setup              # Install all deps
just dev-backend        # Backend on :20000
just dev-frontend       # Frontend on :3000
just build              # Production build (vue-tsc + vite)
just deploy             # Build + start both
just kill               # Kill ports 3000/20000/20001 (port-scoped only — never pkill vite/node)

cd backend && uv run pytest                                  # All backend
cd backend && uv run pytest tests/test_file.py::test_name -v # Single test
cd frontend && npm run test:run                              # All frontend
cd frontend && npm run test:coverage                         # With coverage gate
cd backend && uv run ruff format .                           # Format (line-length=100, py310)
```

## Verification — all three must pass before any task is complete

1. `just build` (vue-tsc type checking + vite build)
2. `cd backend && uv run pytest`
3. `cd frontend && npm run test:run`

## Architecture

**Backend** (`backend/`) — Litestar served by `gunicorn -c gunicorn.conf.py`
(UvicornWorker, workers=1) on `:20000`. Flask was retired in wave 80; the
Litestar app is canonical. The ai-accounts sidecar
(`scripts/run_ai_accounts.py`) on `:20001` owns AI-backend accounts/
credentials/login flows.

- `app_litestar/main.py` — `create_app()` factory; registers handlers,
  middleware, exception handlers, CORS, on_startup/shutdown.
- `app_litestar/routes/*.py` — `Router(...)` defs. `/admin/*` management,
  `/api/*` public, `/health/*` open.
- `app_litestar/middleware.py` — SecurityHeaders (CSP/HSTS/X-Frame),
  RateLimit, RequestContext (request-id + current-user contextvars),
  ApiKey (global X-API-Key + bearer-session gate), RequestLogging.
- `app_litestar/exception_handlers.py` — JSON ErrorResponse + SPA 404
  fallback. Covers `IntegrityError`, `OperationalError`, `ValueError`, and
  a last-resort `Exception` handler piping to `error_capture`.
- `app_litestar/lifecycle.py` — DB seed, backend detection, scheduler +
  periodic jobs, queue/message-bus dispatchers, CLIProxy bootstrap. Honors
  `AGENTED_LITESTAR_SKIP_STARTUP=1` for tests.
- `app/database.py` — Raw SQLite, `get_connection()` context manager, no ORM.
- `app/services/` — Business logic. `ExecutionService` runs CLI harnesses
  via `subprocess.Popen`.
- `app/models/` — Pydantic v2 + msgspec Struct request/response.
- Entity IDs: prefixed random (`bot-`, `agent-`, `conv-`, `team-`, `prod-`,
  `proj-`, `plug-` + 6-char suffix).
- Predefined bots (cannot delete): `bot-security`, `bot-pr-review`.

**Frontend** (`frontend/`) — Vue 3 + TypeScript, Vue Router 4.

- `src/services/api.ts` — API client with per-domain objects (`botApi`,
  `agentApi`, etc.). No state library — `ref`/`reactive`, props/emits,
  `provide`/`inject`. SSE streaming via Litestar `Stream`.
- Vitest + happy-dom + @vue/test-utils.
- Vite proxies `/api/v1/*` → `:20001` (sidecar) and `/api/*`, `/admin/*`,
  `/health/*`, `/schema/*` → `:20000` (Litestar).
- i18n: vue-i18n, catalogs in `src/locales/{en,ko,ja,zh}.json` (full
  parity). Onboarding has a language picker; add a `<surface>.*` namespace
  + `useI18n` for new UI, keeping all four locales key-identical.

## Conventions

- Python: Ruff `line-length=100`, target `py310`.
- Backend tests: `isolated_db` fixture (patches `DB_PATH` to temp file).
  For Litestar route tests, the TestClient logger doesn't propagate to
  `caplog` reliably — spy on `module.logger.warning` via `monkeypatch`.
- Frontend: Geist font, dark theme, CSS custom props in `App.vue`.
- Tour state machine: ≥90% branch coverage on `useTourMachine.ts`
  (enforced by `vitest.config.ts` thresholds).

## MCP tooling — reach for the right index before grep/Read

This repo is wired to three MCP indexes plus context-mode routing. Pick by
the question; don't duplicate a query across them.

| Question shape | Use |
|---|---|
| "Where is symbol X / file Y?" / "what calls X?" / blast radius | **CodeGraph** — `codegraph_context` is the primary one-call composer |
| "What did we decide about X / what past sessions touched X?" | **Tesserae** — `tesserae_ask`, `find_session_findings` (canonical session-memory store) |
| Run a shell command / code / fetch a URL with large output | **Context-Mode** — `ctx_execute`, `ctx_batch_execute`, `ctx_fetch_and_index` |

Context-mode routing (prevents large outputs flooding context): Bash is for
short-output `git`/`mkdir`/`rm`/`mv`/`ls`/`cd` only. Bash >20 lines →
`ctx_execute(language="shell")`. Read-for-analysis → `ctx_execute_file`
(Read is correct only when you'll Edit). `curl`/`wget`/inline HTTP/WebFetch
are blocked → `ctx_fetch_and_index` + `ctx_search`.

Memory tiers don't overlap: **Tesserae** owns session-derived memory
(decisions, insights, past-session refs); `agent_working_memory` owns the
tiny <1 KB always-loaded blob. Don't write the same fact to both.

## GRD planning

`.planning/` holds roadmaps, codebase analysis, and phase plans.
`config.json` is the GRD config; milestones live under
`.planning/milestones/v*/` (v0.5.0 onboarding tour complete → v0.6.0 TBD).

## Tooling

- **GRD**: `/grd:progress`, `/grd:plan-phase`, `/grd:execute-phase`, `/grd:verify-phase`.
- **HarnessSync**: `/harness-sync:sync`, `/harness-sync:sync-status`.
- **Superpowers**: `/superpowers:brainstorming`, `/superpowers:writing-plans`, `/superpowers:executing-plans`, `/superpowers:test-driven-development`.
- **Simplify / Commit**: `/simplify`, `/commit-commands:commit`, `/commit-commands:commit-push-pr`.

---
*Last synced by HarnessSync: 2026-06-01 00:00:00 UTC*
<!-- End HarnessSync managed content -->
