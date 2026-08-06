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
| `AGENTED_TESSERAE_CONSOLIDATE` | backend | unset (on) | Gates the Tesserae 0.23/0.24 **sleep-cycle daemon** — a lifecycle-supervised `tesserae engine --all --consolidate` (`app/services/tesserae_engine_daemon.py`, started in `lifecycle._register_cleanup_handlers`, atexit-stopped, `killpg` on shutdown). On idle it discovers cross-agent connections (`associate`, needs the `[semantic]` extra `scripts/setup.sh` installs) and pre-warms community summaries (`SUMMARIZE`). It runs with **`TESSERAE_AGENT_DISTILL=0`**: the daemon's third op, agent DISTILL, is deliberately off, because it and Auto-distill (below) would otherwise write the same `.tesserae/agents/<key>/distilled.graph.json` from two OS processes with nothing able to serialize them (the daemon's tick takes no `.tesserae/compile.lock`). Agent memory compression and forgetting-by-disuse therefore happen only on the Auto-distill path — per-project opted-in and priced — not fleet-wide. **What stays fleet-wide is this daemon's own ASSOCIATE + SUMMARIZE spend**, which runs `--all` over every project in `~/.tesserae/registry.json` and is gated **only** by this variable — `projects.tesserae_distill_enabled` does not gate it and never did. So "the per-project toggle controls spend" is true of agent-distill specifically, not of all Tesserae LLM spend: a project with the toggle off still gets summarised by this daemon whenever it is on. Honors `AGENTED_SERVER_NO_LLM_KEYS` (LLM keys scrubbed from the daemon env; Tesserae resolves its backend from the harness config dir, not a raw key). Set to `0`/`false` to disable — consolidation is a real background CPU/LLM consumer. No-op under `AGENTED_LITESTAR_SKIP_STARTUP=1` (tests never spawn it). Status is surfaced on the Memory Health page via `/admin/system/memory/config` → `consolidation`. |

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
daily total. Two things narrow the gap and neither closes it: the distill **scope**
— `graph.json` *and* `.tesserae/agents/registry.json`, which tesserae reads as
`known_agent_keys` — is re-hashed immediately before the real run and the run is
refused (`graph_moved_during_pricing`) if either moved while pricing was in
flight, so the priced bytes are the distilled bytes. Hashing the registry too is
load-bearing: a graph-only digest cannot see a scope swap that leaves `graph.json`
byte-identical. (`_scope_digest` is deliberately separate from `_graph_digest`,
which the change-detection policy uses — folding the registry into *that* would
make any super-agent rename dispatch a paid run.) And the dry run *over*-counts
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
(the operator's run is rebuilding the same runbooks, so the window is consumed).

**`served_by_operator_distill` is not a promise that the NEW graph was
distilled.** The operator's run may have started against an older graph and the
compile that triggered this check landed after it; the window is consumed either
way, so that digest can go undistilled until the *next* graph change. Consuming
the window is still right — a distill genuinely is in flight and a second
concurrent one would race the same artifact — but read the record as "a distill
covered this window", never as "this digest is now distilled".

**The 300 s pricing budget is still unvalidated, but no longer unexecuted.** The
dry run HAS now run against the real corpus (2026-08-06): `tesserae distill --all
--dry-run` in the live root returns in **under a second**, exit 0,
`clusters=0 estimated_llm_calls=0 scope=1`. Read that as a floor and nothing more
— it prices *one* agent holding *one* session, so it never enters the work the
budget exists to bound. The cost driver is full scope closure + clustering for
*every* agent with the watermark skip deliberately bypassed, and that work scales
with the agents and sessions this corpus does not yet have. The budget therefore
stays unvalidated; what is now false is "has never executed."

(The same paragraph used to put the live `graph.json` at ~12 MB. It is **5.1 MB**
— 5808 nodes / 8781 edges.)

The pass is free of provider calls — verified in tesserae's source, not
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

**Two traps if you run the dry run by hand.** Both cost a session on 2026-08-06,
and both look like a broken feature rather than a mistake at the prompt:

- **`TESSERAE_AGENT_DISTILL=1` is required.** Without it tesserae exits **1** with
  *"Agent distillation is opt-in — set TESSERAE_AGENT_DISTILL=1 or config.json
  {"agent_distill": {"enabled": true}}"* and prices nothing. The server path is
  unaffected — `super_agent_memory.py:457,641` set it on the subprocess env — so
  this bites only a human at the CLI, and it reads as a pricer failure when it is
  a missing flag. Same shape as the `write_sessions` empty-`producer` default:
  the path you get by not knowing is the failing one.
- **The tesserae root is not the repo checkout.** `get_tesserae_root(project_id)`
  resolves from the project record, and for `proj-xe3qj4` that is
  `~/Developer/Workspaces/projects/GetResearchDone` — *not* the same-named
  checkout under `~/Developer/Projects/`, which has its own unrelated
  `.tesserae/` (2061 nodes). Inspecting the wrong one shows a missing registry
  and a mismatched graph, i.e. exactly the symptoms of the bug you are hunting.
  Resolve the root before believing anything you find in a `.tesserae/`
  directory.

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

**The L2' hierarchy is structurally unpriceable until every declared child has
attributed sessions — and this is the feature's headline shape.**
`sync_agent_registry` sets `parent = <other agent>` whenever one super-agent
parents another (`super_agent_memory.py`), which is exactly what makes tesserae
treat it as a MANAGER. `_distill_manager` then raises `DistillError`
unconditionally when any declared child has no `distilled.graph.json`
(`agent_distill.py:2472-2479`), and a child with nothing attributed never writes
one (`no-sessions`, `:1940`). A dry run cannot create one either — it returns at
`:2236`, *before* the artifact write. **MEASURED against tesserae 0.28.2: both
`distill --all --dry-run` and the real `distill --all` exit 1 on that shape**, so
this does NOT clear by clicking Distill; the operator button fails the same way.
Surfaced as `estimate_unavailable_manager_children_unbuilt` rather than a generic
`exit_nonzero`, because the generic code reads as a broken CLI and hides the
cause. It fails closed — zero spend — but the automatic path stays a no-op for a
hierarchical registry, and each attempt still consumes its 6 h window. Flat
registries (every agent `parent: org:root`) price and run normally. Fixing it
properly needs tesserae to either exempt managers under `--dry-run` or treat a
`no-sessions` child as distillable-empty; until then, treat L2' manager rollups as
unsupported on the automatic path.

**No longer inert — the loop was closed by hand on 2026-08-01.** This section
previously said 0 projects had `tesserae_distill_enabled = 1`, that all 3
`super_agent_sessions` rows had `project_id IS NULL`, and that "nothing in this
feature has ever spawned `tesserae distill`". All three are now false. Measured
state: **1 project opted in** (GetResearchDone), **5 session rows, 1 correctly
attributed** (`sess-cv1uqiev` → `sa-apoc` → `proj-xe3qj4`), and the first
`distilled.graph.json` on this machine exists at
`.tesserae/agents/claude:unknown:sa-apoc/` (5 nodes: 2 Agent, 2 DistilledNote,
1 ExpertiseProfile).

Three things had to be fixed to get there, and each failed silently:

1. **The graph was never built.** `compile --changed-only` reported
   `processed=0 skipped=316` against a `graph.json` holding 302 nodes — the
   manifest claimed every doc was current. A full re-extraction fixed it. A no-op
   compile is not evidence of anything; check `processed>0` before believing a
   compile did work.

   This line used to claim that re-extraction produced **8734 nodes / 12779
   edges**. It did not. That `graph.json` has not been rewritten since (mtime
   `2026-08-01 14:42`, two minutes before the auto-distill dispatch stamped in
   `tesserae_auto_distill_state`), and counted on 2026-08-06 it holds **5808
   nodes / 8781 edges** — which is the figure the 2026-08-02 handoff also
   records. Two independent reads agree with each other and disagree with the
   number that was written here, so treat 5808/8781 as the measurement and 8734/
   12779 as a transcription error. It is corrected rather than deleted because a
   node count is exactly the kind of figure that gets carried forward as
   evidence a compile succeeded.
2. **Sessions were never imported.** The DB row was correctly attributed and the
   registry declared the agent, yet `distill --all --dry-run` still priced it as
   `no-sessions`. `export_sessions_to_tesserae` had to run before the graph had
   anything attributed to any agent.
3. **The `project_id` was being dropped by a specific caller** — the thing the
   old text told you to go looking for. `_fix_stale_session`
   (`autofix_service.py`) deleted a stale super-agent session and recreated it
   via `get_or_create_session(super_agent_id)` without forwarding the project, so
   the replacement carried NULL. The Tesserae export hook opens with
   `if not project_id: return`, so agent memory for that project silently never
   populated again. Fixed; the 4 remaining NULL rows are `sa-system` autofix
   investigations that genuinely have no project.

**The AUTOMATIC path has now fired too, once, on 2026-08-01 — and spent
nothing.** A compile on the opted-in project produced, unprompted:

```
auto-distill scheduled for proj-xe3qj4 — graph.json changed to 375802fd4ed0,
  79849s since last dispatch, budget 60 estimated provider calls
auto-distill finished for proj-xe3qj4 — nothing_to_distill, 0 provider calls
```

So change-detection, the 6 h interval check, and the pricing gate all work as
documented, and the record persisted to `projects.tesserae_auto_distill_state`
with its digest and `at_epoch` (so the floor survives a restart, not just this
process).

Read the outcome precisely: `nothing_to_distill` here is the **priced-at-zero**
shape, not the `no-sessions` one. The free dry run reports
`clusters=0 estimated_llm_calls=0 scope=1` — the agent HAS scope, but one session
with 8 decisions does not form a cluster worth summarising. The chain is proven;
what is still unobserved is a dispatch that actually spends, and with it the
`≥n` partial-cost path and the 1800 s timeout. Do not read "the automatic path
works" as "the automatic path has been seen to bill".

**These gates assume `workers = 1`.** The coalesce map and the 6 h record are
in-process (`tesserae_integration`), and the DB write is a record, not an atomic
claim. `gunicorn.conf.py` pins `workers = 1` as MANDATORY, so today exactly one
process can dispatch. That comment frames the pin as temporary ("until in-memory
SSE state is migrated to Redis") — **whoever lifts it must first make the dispatch
an atomic claim**, or two workers seeing the same changed graph both dispatch,
doubling spend and racing the same artifact.

Last dispatch, outcome and measured call count surface at
`/admin/system/memory/tesserae/projects` → per-project `last_auto_distill`, and on
the Memory System settings row — durably, from the persisted row above, not from
process memory. A record can also sit unresolved at `graph_changed` with no cost:
the tesserae child is spawned with `start_new_session=True`, so a worker restart
mid-run orphans a child that keeps spending while the new process has no job to
resolve. An old `graph_changed` on that row means "outcome unknown", not "nothing
happened".
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
2. `cd backend && uv run pytest` — **the full serial suite completes. It does
   NOT hang.** Measured 2026-08-01 across two runs: 13m04s and 16m24s, both to
   100%. Run it and wait.

   This previously documented a hang at ~40-48% and told you to kill the run at
   **12 minutes** and substitute a targeted set. That is almost certainly the
   whole story — a 12-minute watchdog on a 13-to-17-minute suite kills it every
   time, at whatever percentage it happens to have reached, and the kill was
   then read as the hang. If you time out, raise the budget before concluding
   anything; do not reach for targeted runs first. (Two runs in this session
   looked like hangs for exactly this reason: a harness timeout at 10 minutes,
   not the suite.)

   **The suite is GREEN: 5469 passed, 0 failed** (2026-08-01, 14m13s). Any
   failure is yours. This previously listed 20 "pre-existing failures" to be
   tolerated; all 20 were triaged and fixed, and they were not noise — among
   them was a real bug (a PATH probe silently outranking the explicit
   `CLAUDE_PLUGIN_ROOT` override) whose three tests had been correct and red for
   seven weeks. Do not re-introduce a tolerated-failure list: it is how a suite
   stops being able to warn anyone.

   Two of the twenty depended on the DEVELOPER's environment, not on the code —
   worth knowing when a test fails for you and nobody else: a shell that exports
   `AGENTED_API_KEY` (this machine's `~/.zshrc` does) makes "no auth configured"
   false, and `config_status`/`graph_status` cache to `~/.cache/agented/tesserae`
   so a stubbed test could assert against your real cache. Both are now
   neutralised in `tests/conftest.py` and the tests themselves.
3. `cd frontend && npm run test:run` — **1727 passed / 191 files, zero
   failures** (measured 2026-08-01). This previously documented "7 known
   pre-existing failures (RateLimitGauge, MarkdownContent, WorkingMemoryView,
   useTourMachine)" and told you to gate on "no NEW failures". Those are fixed;
   the gate is now simply **green**. A red frontend suite is a real regression,
   not the baseline.

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
migrations 166–170). Latest shipped milestone: **v0.10.0**.

### GRD 0.5.0 — interactive research steering (wired)

GRD itself is at **0.5.0** (`gd --version`; note `gd` resolves to the local dev
clone at `~/Developer/Projects/GetResearchDone`, not the plugin cache).
`research_gates.interactive` is wired on in `.planning/config.json`: all four
stations (`seed`/`hypothesize`/`design`/`decide`), `max_rounds: 2`,
`max_questions: 4`, `hypothesis_candidates: 3`, `every_iteration: false`,
`fallback: "panel"`. Verified by GRD's own `readInteractiveConfig` — every key
accepted, no `[interactive-config]` warnings.

**With `autonomous_mode: true` the human checkpoints never fire.**
`resolveInteractive` returns `active:false` under *any* unattended condition —
`autonomous_mode`, autopilot/`GRD_AUTOPILOT`, `--no-gates`, portfolio
concurrency > 1 — and this project sets `autonomous_mode: true`. Measured:
`autonomousMode:false → {active:true}`, `autonomousMode:true → {active:false}`.
So the setting that actually does work here is `fallback`, which picks *who
answers* when no human is present. **To get real human-in-the-loop steering, set
`autonomous_mode: false`** — the four station flags are already on and will
engage immediately.

`fallback: "panel"` answers via a multi-backend AI discussion instead of each
question's recommended default. Its roster is `['claude','codex','gemini',
'opencode']` minus the loop's own backend (no self-consultation); all four are
installed on this machine, so the panel is real rather than degrading. It is
degrade-safe by design: empty synthesis, a rate-limited or logged-out panelist,
or any unforeseen error resolves to the recommended defaults. The loop never
pauses unattended either way (REQ-208). `every_iteration` is left `false`
deliberately — `true` runs a panel discussion every iteration, which is real
recurring LLM spend.

## Tooling

- **GRD**: `/grd:progress`, `/grd:plan-phase`, `/grd:execute-phase`, `/grd:verify-phase`.
- **HarnessSync**: `/harness-sync:sync`, `/harness-sync:sync-status`.
- **Superpowers**: `/superpowers:brainstorming`, `/superpowers:writing-plans`, `/superpowers:executing-plans`, `/superpowers:test-driven-development`.
- **Simplify / Commit**: `/simplify`, `/commit-commands:commit`, `/commit-commands:commit-push-pr`.
