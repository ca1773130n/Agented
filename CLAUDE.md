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
| `DATABASE_URL` | backend | unset → SQLite | **SQLite is the zero-config default; unset ⇒ byte-for-byte unchanged.** Set to a `postgres://`/`postgresql://` URL to run the backend on Postgres via the Phase-26 DB-API adapter (`app/db/connection.py`). ⚠️ **Postgres is EXPERIMENTAL.** Core paths are verified on a live Postgres 16 (PR #289 / DEFER-26-01): fresh-schema build + full migration replay, CRUD, auth/RBAC/sessions, date/analytics queries, and the sidecar admin-key lookup. Remaining caveats: full-text search degrades to `ILIKE` (no `fts5` BM25 ranking), a few SQLite-only maintenance/backup paths are skipped on PG, and not every code path is PG-exercised yet. Validate your workload before production; SQLite stays the supported default. |
| `AGENTED_TESSERAE_CONSOLIDATE` | backend | unset (on) | Gates the Tesserae 0.23/0.24 **sleep-cycle daemon** — a lifecycle-supervised `tesserae engine --all --consolidate` (`app/services/tesserae_engine_daemon.py`, started in `lifecycle._register_cleanup_handlers`, atexit-stopped, `killpg` on shutdown). On idle it discovers cross-agent connections (`associate`, needs the `[semantic]` extra `scripts/setup.sh` installs) and pre-warms community summaries (`SUMMARIZE`). It runs with **`TESSERAE_AGENT_DISTILL=0`**: the daemon's third op, agent DISTILL, is deliberately off, because it and Auto-distill (below) would otherwise write the same `.tesserae/agents/<key>/distilled.graph.json` from two OS processes with nothing able to serialize them (the daemon's tick takes no `.tesserae/compile.lock`). Agent memory compression and forgetting-by-disuse therefore happen only on the Auto-distill path — per-project opted-in and priced — not fleet-wide. Honors `AGENTED_SERVER_NO_LLM_KEYS` (LLM keys scrubbed from the daemon env; Tesserae resolves its backend from the harness config dir, not a raw key). Set to `0`/`false` to disable — consolidation is a real background CPU/LLM consumer. No-op under `AGENTED_LITESTAR_SKIP_STARTUP=1` (tests never spawn it). Status is surfaced on the Memory Health page via `/admin/system/memory/config` → `consolidation`. |

### Auto-distill (super-agent L1 runbooks)

`projects.tesserae_distill_enabled` now authorises two spending passes, not one:
the compile-time Runbook/Gotcha pass (`--distill`) **and** automatic super-agent
L1 distillation. The latter chains off `compile_workspace` — after a compile that
succeeded **and** whose `.tesserae/graph.json` digest changed, an opted-in project
dispatches `agent-distill` at most **once per 6 hours**, coalesced per (project,
op). The run is refused unless a free `distill --all --dry-run` prices it at **≤60
provider calls**; it is deliberately run **uncapped** (`--max-llm-calls` degrades
over-budget clusters to uncached deterministic fallback behind a stamped
watermark, so it damages the artifact instead of bounding it).

**What the ≤60 is and is not.** It is a go/no-go taken *before* the run, never a
throttle inside it, so 4 windows × 60 is an **expectation of about 240 provider
calls per project per day, not an enforced ceiling** — nothing anywhere counts a
daily total. Two things narrow the gap and neither closes it: `graph.json` is
re-hashed immediately before the real run and the run is refused
(`graph_moved_during_pricing`) if a compile landed while pricing was in flight,
so the priced bytes are the distilled bytes; and the dry run *over*-counts
relative to a real run because it ignores the per-agent watermark skip. It can
also under-describe the run — dry-run clustering executes without the memo
`state` (`agent_distill.py:1999`), so cluster shapes can differ. Spend is a hard
zero for a project that has not opted in, a failed compile, an unchanged graph,
an unpriceable pass, or an over-budget estimate.

**The 6 h floor survives a restart.** The record — last digest, timestamp,
outcome and measured cost — is persisted as JSON in
`projects.tesserae_auto_distill_state` (migration 181) next to the toggle that
authorises it, and read back when this process didn't dispatch it. Without that
the in-memory map was empty after every gunicorn restart, `prev` was falsy, the
interval check was skipped as a "first dispatch", and the next successful compile
opened a fresh window. Within one process the age still comes from
`time.monotonic()` (immune to wall-clock changes); across a restart it comes from
the persisted `at_epoch`. A record with neither reads as infinitely old, so a
corrupt row costs one extra *priced* dispatch rather than wedging the policy shut.
Persisting is best-effort: a failed write is logged and leaves the in-memory
record intact, which degrades to exactly the old behaviour.

**A timed-out run reports a floor, not a total.** A run killed at the 1800 s
timeout records `llm_calls_partial` (rendered `≥n`) — the agent killed mid-flight
never printed its cost. `start_new_session` + `killpg` reap tesserae **and every
child still in its process group** — the CPU-burning graph work, and the pipe
holders that would otherwise wedge the drain. They do **not** reach the provider
call: tesserae spawns the Claude/Codex CLI with its own `start_new_session=True`
(`tesserae/llm_json.py` `_run_cli`), so it lives in a different session, and
tesserae being SIGKILLed means its own cleanup never runs either. One in-flight
provider call can survive a timeout, unbilled to us and unobserved — the reported
`≥n` is a floor for that reason as much as for the unprinted line.

**One distill per project, and never one path's outcome reported as the
other's.** The automatic policy and the operator's Distill button share the
`(project, op)` coalesce key, but `run_op_async` joins a running job only when it
was dispatched with the same arguments — and they never are, because only the
automatic path passes a budget. A mismatch returns `""`: nothing dispatched. So
the operator clicking Distill while an automatic run is in flight gets
`{job_id: null, reason: "auto_distill_running"}` and a "try again once it
finishes" note, not that run's budget refusal as the answer to an explicit
unpriced approval; and the automatic path, rather than recording a dispatch that
never ran, resolves its record to `served_by_operator_distill` with a cost of 0
(true — the operator's run is rebuilding the same runbooks from the same graph,
so the window is consumed).

**The 300 s pricing budget is unvalidated.** The dry run has never executed
against a real corpus; the live `graph.json` is ~12 MB and the pass does full
scope closure + clustering for *every* agent because it deliberately bypasses the
watermark skip. It is free of provider calls — verified in tesserae's source, not
assumed (`agent_distill.py:1567` returns the deterministic fallback before
`self.summarizer(request)`) — so overrunning costs CPU, not money, and fails
closed with `estimate_unavailable_timeout` plus the killed-at elapsed seconds in
the log. That log line is the evidence to set the real number from, and it is the
only evidence you get: **a refusal spends nothing but still consumes the 6 h
window**, so a pricing budget set too low does not fail loudly — it degrades into
"the runbook silently stops refreshing", one quiet refusal per window. That is a
deliberate trade (not re-consuming the window would re-burn the full CPU-bound
dry run on every compile), which is why the refusal reason is surfaced in the UI
via `last_auto_distill.reason` rather than left in the log: an
`estimate_unavailable_*` sitting on that row is the symptom to look for.

An `estimate_unavailable_*` reason always means the pricer failed. **Two**
healthy shapes price at 0 and report `nothing_to_distill` instead, and neither
may be shown as "could not price the pass": an empty scope (tesserae prints "No
agents observed in the compiled graph" and exits 0, `cli.py:6131`), and — the
shape this machine's data actually produces — agents that exist but have nothing
attributed to them, which print `no-sessions` and `continue` **without** an
`estimated_llm_calls=` line (`cli.py:6144-6146`), leaving a non-empty `results`
with no estimate anywhere and exit 0. `skipped-watermark` is the third such
`continue` but cannot occur while pricing: `agent_distill.py:1970` bypasses the
watermark skip under `dry_run`.

**Inert on this machine today, by data not by design.** 0 projects have
`tesserae_distill_enabled = 1`, and all 3 rows in `super_agent_sessions` have
`project_id IS NULL` while `_project_super_agents` joins on it — so
`distill_super_agents` returns `no_super_agents` and BOTH the manual Distill
button and this automatic path are no-ops here. The gates above are therefore
covered by tests, not by a production run: nothing in this feature has ever
spawned `tesserae distill`. Do a manual Distill first on a project that has
super-agent sessions with a `project_id` before trusting the automatic path — it
will also surface why `project_id` is never persisted on super-agent sessions,
which independently keeps super-agent expertise out of the graph.

Last dispatch, outcome and measured call count surface at
`/admin/system/memory/tesserae` → `last_auto_distill`, and on the Memory System
settings row — durably, from the persisted row above, not from process memory.
This is the **only** automatic agent distiller — the sleep-cycle
daemon's DISTILL op is switched off for exactly that reason (see
`AGENTED_TESSERAE_CONSOLIDATE` above). No env knob —
`_TESSERAE_AUTO_DISTILL_*` in `app/services/tesserae_integration.py` are spend
ceilings, not deployment config.

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
