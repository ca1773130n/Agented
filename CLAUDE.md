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
| `AGENTED_DISABLE_SIGNUP` | backend | unset (open) | Set to `1` to close open self-registration (`POST /api/auth/signup` → 403). Open by default for single-operator onboarding (the **first** registrant becomes admin). **Set this once you've registered, and always before exposing the instance to an untrusted network** — otherwise an attacker could race to be the first signup and gain admin. Surfaced to the SPA via `signup_enabled` in `/health/auth-status`. |
| `AGENTED_SERVER_NO_LLM_KEYS` | backend | unset (read env keys) | Set truthy (`1`/`true`/`yes`/`on`) to make the server **refuse to read raw LLM inference keys from its own process environment** (e.g. a `ANTHROPIC_API_KEY` baked into the deploy). Credentials must instead flow in per-request via explicit `api_key` args sourced from the ai-accounts sidecar — isolating a shared/"poison" server-wide key from silently backing every user's inference. Read dynamically (not cached) through `config.env_llm_key`, which gates the server-side fallbacks (`cliproxy_chat_service.stream_chat_direct`, `conversation_streaming` direct-API path, `orchestration_service._build_account_env`) **and** the harness subprocess env (`config.subprocess_env`/`scrub_env_inplace` — pipe, PTY-fork, and cli-agent-runner paths). Default (unset) reads env keys as before — byte-for-byte unchanged. |
| `DATABASE_URL` | backend | unset → SQLite | **SQLite is the zero-config default; unset ⇒ byte-for-byte unchanged.** Set to a `postgres://`/`postgresql://` URL to run the backend on Postgres via the Phase-26 DB-API adapter (`app/db/connection.py`). ⚠️ **Postgres is EXPERIMENTAL / not production-ready** — full cross-backend parity is incomplete (tracked DEFER-26-01, PR #289): fresh-schema DDL (`fts5`/`randomblob`, one cyclic FK), `row_factory`/`cursor.description` compat that breaks auth on PG, sidecar still reading admin keys from SQLite, some untranslated date/catalog SQL. Use SQLite for production until parity lands. |

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
2. `cd backend && uv run pytest` — **known issue:** the full serial suite
   hangs at ~40-48% (no failures before the hang). Procedure: attempt the
   full suite under a ~12-minute watchdog; on hang, kill it and run a
   comprehensive targeted set (all suites touched by the change + execution/
   streaming/harness regressions), and disclose the substitution in the PR.
   Never present targeted runs as the full suite.
3. `cd frontend && npm run test:run` — baseline carries 7 known pre-existing
   failures (RateLimitGauge, MarkdownContent, WorkingMemoryView,
   useTourMachine areas); the gate is **no NEW failures**.

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
- **Unified loop layer (v0.6.0)** — `LoopSpec` (`app/models/loop_spec.py`,
  `from_legacy_config`) is the one schema for all loop patterns; the SINGLE
  executor is `goal_loop_runner.py`, which drives BOTH goal-loops and Ralph
  (deep-unified). It owns the exit ladder (quality-gate → stagnation →
  convergence → budgets), per-iteration records (`goal_loop_iterations`,
  migrations 166–170), checkpoint/resume, pause/intervene/human-gate control,
  and `context_policy` (`carry` vs `reset`-per-iteration). The eval quality-gate
  runs through `goal_judge_service.py`; deterministic checks are sandboxed via
  `sandbox_eval.py` (snapshot + scrubbed env + process-group kill). In the
  runner, the stable operator id never moves — only `live_id` follows a reset
  child (broadcasts/DB/memory always key off the stable id).
- `app/models/` — Pydantic v2 + msgspec Struct request/response.
- Entity IDs: prefixed random (`bot-`, `agent-`, `conv-`, `team-`, `prod-`,
  `proj-`, `plug-` + 6-char suffix).
- Predefined bots (cannot delete): `bot-security`, `bot-pr-review`.

**Frontend** (`frontend/`) — Vue 3 + TypeScript, Vue Router 4.

- `src/services/api/` — API client **package** (NOT a single `api.ts`):
  per-domain modules (`triggers.ts` with `executionApi`/`triggerApi`,
  `budgets.ts`, `answer-eval.ts`, …), shared `apiFetch` in `client.ts`,
  types under `types/`, all re-exported through the `index.ts` barrel
  (`import { executionApi } from '../services/api'`). No state library —
  `ref`/`reactive`, props/emits, `provide`/`inject`. SSE streaming via
  Litestar `Stream`.
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

**ALWAYS use CodeGraph MCP to find or modify code — before any grep/Read/edit.**
It is the pre-built index of every symbol, edge, and file; a blind grep/Read
loop (or delegating exploration to a sub-agent) repeats work it already did.

- "what's the deal with X / this feature or bug" → `codegraph_context` (PRIMARY — one call composes search + node + callers + callees)
- "where is symbol X?" → `codegraph_search`; "show its source/signature" → `codegraph_node`
- "what calls X?" / "what would changing X break?" → `codegraph_callers` / `codegraph_impact`
- survey several related symbols at once → `codegraph_explore`

Reach for raw Read/Grep only to confirm a specific detail CodeGraph didn't
cover, or when you already know the exact file+line to edit. CodeGraph can
query other indexed repos via `projectPath` (e.g. `~/Developer/Projects/HypePaper`).

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
`.planning/milestones/v*/` (v0.5.0 onboarding tour → v0.6.0 unified loops
shipped: `LoopSpec` + single executor + eval/sandbox + observability/control,
migrations 166–170).

## Tooling

- **GRD**: `/grd:progress`, `/grd:plan-phase`, `/grd:execute-phase`, `/grd:verify-phase`.
- **HarnessSync**: `/harness-sync:sync`, `/harness-sync:sync-status`.
- **Superpowers**: `/superpowers:brainstorming`, `/superpowers:writing-plans`, `/superpowers:executing-plans`, `/superpowers:test-driven-development`.
- **Simplify / Commit**: `/simplify`, `/commit-commands:commit`, `/commit-commands:commit-push-pr`.
