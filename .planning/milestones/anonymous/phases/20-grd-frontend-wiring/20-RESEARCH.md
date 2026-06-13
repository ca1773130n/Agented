# Phase 20: GRD Frontend Wiring — Research

**Researched:** 2026-06-13
**Domain:** Litestar backend (CLI-wrapper routes + execution-type handler + SSE) + Vue 3 frontend (pages, api client, i18n) wiring of GRD's autoresearch and life-harness surfaces
**Confidence:** HIGH (every claim below verified in live code via CodeGraph MCP + grep/read; file:line anchors throughout)

## Summary

This phase is **mostly frontend wiring of already-shipped backend surfaces**, plus **one genuinely new backend slice** (autoresearch, REQ-14). The key correction to the phase framing: the "16 unwired GRD routes" plus the life-harness completion backends (autonomy editor, round revert, shared-forge adopt) **already exist and are fully implemented in the backend** — they simply have **zero frontend callers**. So REQ-16 is ~90% frontend + i18n, not backend. Only REQ-14 (`gd research` wrapper routes + a `grd_research` execution-type handler) requires new backend code.

The established patterns to mirror are crisp and verified:
- **Execution-type handler:** `GrdChatSessionHandler` (`backend/app/services/execution_type_handler.py:683`) registered in `HANDLER_REGISTRY` at `:824`/`:830`. Mirror it verbatim for `grd_research`, swapping the spawned command.
- **CLI wrapper:** `GrdCliService.run_gd` / `run_gd_json` (`backend/app/services/grd_cli_service.py:170`/`:185`) — the established way to shell out to the `gd` binary. Add a `research()` family here.
- **Frontend SSE:** `usePlanningSession.ts` consumes `grdApi.streamSession()` via `createAuthenticatedEventSource` — mirror for research sessions.
- **Command manifest:** `PlanningCommandBar.vue` already uses a declarative `commandGroups` array — extend it, don't rebuild it.

**Primary recommendation:** Decompose into 6 plans across 3 waves. Wave A = new autoresearch backend (REQ-14) + the `research.ts`/`grdHarness.ts` api modules (pure plumbing, parallelizable). Wave B = Research page (REQ-15) + life-harness panels (REQ-16) + PlanningCommandBar manifest (REQ-17), each consuming Wave A. Wave C = i18n parity sweep (REQ-18) + house-gate green. Treat the autonomy/round/forge backends as **fixed contracts** — do not modify them.

## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase (no `/grd:discuss-phase` was run). Constraints are taken from the phase goal, success criteria, and REQ-14..REQ-18 as provided by the orchestrator. The planner is otherwise free within those.

Inherited house rules that bind this phase (from CLAUDE.md / MEMORY.md):
- **i18n parity is mandatory** — every new UI string ships key-identical en/ko/ja/zh (`src/locales/{en,ko,ja,zh}.json`). This is REQ-18 and a repeated user directive.
- **LLM features support all 4 backends** — any new LLM-calling surface accepts `{backend_kind, model_override?}`; never claude-only. The autoresearch wrapper spawns `gd research` (which itself runs claude under GRD), so the surface inherits GRD's model profile; expose model override where GRD does, do not hardcode.
- **Frontend gate = no NEW failures.** Baseline carries 7 known failures (RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine areas) — do not touch those files.
- **`just kill` is port-scoped only**; never pkill node/vite.

---

## §1 — Backend Autoresearch Handler + Routes (REQ-14)

This is the only net-new backend in the phase. Two pieces: (a) a CLI-wrapper service surface for `gd research`, and (b) a `grd_research` execution-type handler for the long-running loop with SSE.

### 1a. The real `gd research` CLI surface (verified)

Source: `~/.claude-personal1/plugins/cache/claude-plugin-marketplace/grd/0.4.4/commands/research.md`.

```
gd research "<question>" [--max-iterations N] [--no-gates]   # start a new thread
gd research resume <id>                                       # resume a gate-paused thread
gd research status [<id>]                                     # list threads, or show one thread
```

- The slash-command form is `/grd:research "<question>"` (what a `grd_research` *session* spawns, mirroring grd_chat's `/grd:<cmd> "<task>"` one-shot).
- **There is no separate `report` or `portfolio` subcommand in the CLI.** Success criterion 1 names "report" and "portfolio" — the **safest interpretation** (flag this to the planner):
  - **report** = read the thread's `FINDING.md` (final structured finding written at FINALIZE) from disk via the thread browser, not a CLI call.
  - **portfolio** = list all threads under `.planning/research/threads/` with their status/iteration (i.e. an aggregate of `gd research status` + on-disk frontmatter). Treat "portfolio runs" as "the set of threads," surfaced by the thread browser.

### 1b. Thread storage layout (verified from research.md spec)

`.planning/research/threads/<thread-id>/` (thread-id = slug(question)+short-hash). Does **not** exist yet in this repo — created on first run. Contents:

| File | Purpose | Frontend use |
|---|---|---|
| `THREAD.md` | Resumable state-machine frontmatter: `id, question, status, iteration, max_iterations, gates{execute,kg_write}, budget_used, current_station, pending_gate` | thread list row (status/iteration), resume gate |
| `HYPOTHESES.md` | Append-only hypothesis ledger: `id, iteration, statement, rationale, predicted_outcome, status(open/testing/supported/refuted/inconclusive/superseded), parent_id, verdict` | **hypothesis ledger view** (REQ-15) |
| `experiments/<iter>/PLAN.md`,`result.json`,`RUN.md` | per-iteration experiment plan + metrics | iteration detail |
| `TAKEAWAYS.md` | typed takeaway ledger | optional panel |
| `FINDING.md` | final structured finding | **report viewer** (REQ-15) |
| `kg.json` | Tesserae nodes read/written | provenance (optional) |

Thread `status` values: `active, paused, supported, exhausted, error, abandoned`.

### 1c. CLI-wrapper service to add — mirror `GrdCliService`

File: `backend/app/services/grd_cli_service.py`. Existing methods establish the exact pattern: `run_gd(cls, cwd, *args, json_output=False)` (`:170`), `run_gd_json(cls, cwd, *args)` (`:185`), and typed wrappers like `get_health` (`:299`), `think` (`:315`), `genome_show` (`:373`), `verify_mechanical` (`:403`). Each: check binary via `available()`/`gd_path()`, build argv, `_run` with timeout/capture, return dict (or `{"error": ...}` on unavailable).

Add a research family here (or a new `grd_research_service.py` if the planner prefers separation):
- `research_status(project_path, thread_id=None)` → `run_gd_json(cwd, "research", "status", *( [thread_id] if thread_id else []))`
- `list_threads(project_path)` → read `.planning/research/threads/*/THREAD.md` frontmatter on disk (the "portfolio"/thread browser). On-disk read is safer/cheaper than a CLI round-trip and matches how the genome/reflections DB-mirror reads work.
- `read_thread(project_path, thread_id)` → read THREAD.md + HYPOTHESES.md + FINDING.md from `.planning/research/threads/<id>/`.
- Start/resume are **long-running loops** → route through the execution-type handler (1d), not a blocking `run_gd`.

### 1d. The `grd_research` execution-type handler — mirror `GrdChatSessionHandler`

File: `backend/app/services/execution_type_handler.py`. Verified anchors:
- `GrdChatSessionHandler` class at **`:683`**; `start` builds `cmd` and calls `ProjectSessionManager.create_session(..., execution_type="grd_chat", stream_json=True, use_pty=False, forge_bundle=..., super_agent_id=...)`.
- Command shape (`:753`–`:767`): resolves `/grd:<cmd>` then spawns `["claude","-p","--output-format","stream-json","--verbose", f"{grd_command} {json.dumps(task)}"]`. **`json.dumps(task)` is the prompt-framing hardening from 19-04 (security follow-up) — keep it.**
- cwd resolved via `ProjectWorkspaceService.resolve_working_directory(project_id)` (`:project_workspace_service.py:74`, raises `ValueError` when no clone).
- `HANDLER_REGISTRY` static dict at **`:824`** (entries `direct, ralph_loop, team_spawn, goal_loop, grd_evolve, grd_chat` at `:830`); `get_handler` at `:834`. **Add `"grd_research": GrdResearchSessionHandler()`.**

`GrdResearchSessionHandler.start` mirrors grd_chat exactly, swapping the prompt to `/grd:research <json.dumps(question)>` (append `--max-iterations` / `--no-gates` translation if exposed). `monitor`/`stop`/`get_output` delegate to `ProjectSessionManager` identically.

### 1e. SSE bridge + route

- grd_chat bridges PSM stream-json → chat `state_delta` via `grd_chat_bridge.bridge_psm_to_chat` (event map: `text→content_delta`, `tool_use→tool_use`, `result→finish`, `error→error`). For research, the **session output stream is consumed the same way** the planning session is: the existing `@get("/{project_id}/sessions/{session_id}/output")` route (`grd_routes.py:928`) + `@get("/{project_id}/sessions")` (`:919`) already expose PSM sessions generically. **Recommendation:** reuse the generic session-output SSE rather than building a research-specific bridge — the Research page streams raw session output (like the planning session panel), and reads thread artifacts from disk for the structured ledger/report views.
- New routes belong in `grd_routes.py` under the existing `grd_router = Router(path="/api/projects")` (`:1658`). Suggested:
  - `POST /{project_id}/research/start` → create a `grd_research` session, return `{session_id}` (mirror `POST /{project_id}/planning/invoke` at `:718`).
  - `POST /{project_id}/research/{thread_id}/resume` → spawn `gd research resume <id>` session.
  - `GET /{project_id}/research/threads` → list (portfolio/thread browser).
  - `GET /{project_id}/research/threads/{thread_id}` → THREAD/HYPOTHESES/FINDING bundle.
  - `GET /{project_id}/research/status` → `gd research status` passthrough.

### Anti-patterns to avoid
- Do **not** make `start`/`resume` blocking `run_gd` calls — the loop runs minutes. Use the session handler (non-blocking PSM spawn) + SSE.
- Do **not** invent a `gd research report`/`portfolio` CLI call — they don't exist; read artifacts from disk.
- Do **not** reintroduce naive `f'"{question}"'` interpolation — use `json.dumps` (19-04 security fix).

---

## §2 — The "16 Unwired GRD Routes" Inventory (REQ-16 backend contracts)

**All already implemented; all currently have ZERO frontend callers.** Verified by reading the route files and grepping `frontend/src` for callers. Three router groups:

**Group A — Ouroboros + DB-mirror, `grd_router` (`grd_routes.py`, prefix `/api/projects`):**

| # | Method | Path (after prefix) | Handler / line | Response shape (source) | Proposed UI panel |
|---|---|---|---|---|---|
| 1 | GET | `/{id}/grd/health` | `grd_health` :124 | `GrdCliService.get_health` JSON | Health panel |
| 2 | POST | `/{id}/grd/think` | `grd_think` :155 | `think()` briefing | Think panel (button → briefing) |
| 3 | POST | `/{id}/grd/dead-ends` | `grd_add_dead_end` :176 | created dead-end | Dead-ends panel (add) |
| 4 | POST | `/{id}/grd/dead-ends/promote-from-phase/{phase}` | `grd_promote_dead_ends` :201 | promoted set | Dead-ends panel (promote) |
| 5 | GET | `/{id}/grd/dead-ends` | `list_grd_dead_ends` :1505 | dead-ends list (DB mirror) | Dead-ends panel (list) |
| 6 | GET | `/{id}/grd/genome` | `grd_genome` :233 | genome JSON | Genome panel |
| 7 | POST | `/{id}/grd/genome/snapshot` | `grd_genome_snapshot` :259 | snapshot | Genome panel (snapshot) |
| 8 | GET | `/{id}/grd/genome/snapshots` | `list_grd_genome_snapshots` :1516 | snapshot list | Genome panel (history) |
| 9 | GET | `/{id}/grd/genome/latest` | `latest_grd_genome_snapshot` :1529 | latest snapshot | Genome panel (current) |
| 10 | POST | `/{id}/grd/verify/mechanical/{phase}` | `grd_verify_mechanical` :277 | mechanical verify result | Verify panel |
| 11 | GET | `/{id}/grd/phases/{phase_id}/reflections` | `list_phase_reflections` :1480 | reflections list | Reflections panel |
| 12 | GET | `/{id}/grd/verdict-counts` | `grd_verdict_counts` :1493 | verdict tallies | Verdict-counts widget |
| 13 | POST | `/{id}/grd/evolve/start` | `start_grd_evolve` :1546 | `{run_id}` | Evolve panel (start) |
| 14 | GET | `/{id}/grd/evolve/runs` | `list_grd_evolve_runs` :1587 | runs list | Evolve panel (list) |
| 15 | GET | `/{id}/grd/evolve/runs/{run_id}` | `get_grd_evolve_run` :1602 | run detail | Evolve panel (detail) |
| 16 | POST | `/{id}/grd/evolve/runs/{run_id}/stop` | `stop_grd_evolve_run` :1616 | stop ack | Evolve panel (stop) |

That is the canonical "16" (health/think/dead-ends/genome/verify-mechanical/reflections/verdict-counts/evolve as the phase goal names). Group them into ~6 panels: **Health, Think, Dead-Ends, Genome, Verify-Mechanical, Reflections+Verdicts, Evolve.**

**Group B — life-harness completion, `harness_evolution_router` (`harness_evolution.py`, prefix `/admin`)** — REQ-16's autonomy/round/forge surfaces:

| Method | Path | Handler / line | Notes |
|---|---|---|---|
| POST | `/projects/{id}/evolution/dry-run` | `dry_run_round` :13 | harness round (dry) |
| POST | `/projects/{id}/evolution/apply` | `live_round` :32 | harness round (live) |
| GET | `/projects/{id}/evolution/rounds` | `list_project_rounds` :51 | rounds list |
| GET | `/evolution/rounds` / `/evolution/rounds/{rid}` | `list_all_rounds` :60 / `get_round_detail` :69 | round browse/detail |
| GET | `/evolution/rounds/{rid}/impact` | `get_round_impact` :77 | round impact |
| POST | `/evolution/rounds/{rid}/apply`·`/abort`·`/revert` | `approve_round` :85 / `abort_round` :92 / **`revert_round_route` :103** | **round revert (REQ-16)** → `harness_evolution_rollback.revert_round` |
| GET | `/shared-forge` | `list_shared_forge` :115 | **shared-forge browse** → `forge_promotion.list_shared_bindings` |
| POST | `/projects/{id}/adopt-shared/{shared_binding_id:int}` | `adopt_shared_route` :122 | **shared-forge adopt** → `harness_propagation.adopt_shared_binding` |
| GET | `/projects/{id}/autonomy` | `get_autonomy_config` :129 | **autonomy editor (read)** |
| PUT | `/projects/{id}/autonomy` | `set_autonomy_config` :142 | **autonomy editor (write)** |

Autonomy storage: SQLite `project_autonomy_config(project_id, policy_json, ...)` via `backend/app/db/project_autonomy_config.py` (`get_policy`/`upsert_policy`); model `backend/app/models/autonomy_policy.py::AutonomyPolicy`. **No backend change needed** — the editor just GETs the policy, edits fields, PUTs it back.

**Group C — `harness_takeaways_router` (`harness_takeaways.py`, prefix `/admin`):** list/recent/get/apply/dismiss takeaways (`:13`/`:31`/`:47`/`:55`/`:61`). Optional bonus panel; not strictly in the phase's named 16 but adjacent to evolution UI.

> ⚠️ **Auth/prefix gotcha for the planner:** Group A is `/api/projects/...` (public api, X-API-Key) while Groups B/C are `/admin/...` (admin-gated). The frontend api client must hit the right base and carry admin auth for the `/admin` routes. Confirm the admin-auth header path in `client.ts` at execution time.

---

## §3 — Research Page Composition (REQ-15)

Mirror `ProjectPlanningPage.vue` (`frontend/src/views/ProjectPlanningPage.vue`) which composes `EntityLayout` + `PageHeader` + a command bar + a session panel.

**Files to create:**
- Page: `frontend/src/views/ProjectResearchPage.vue` (mirror ProjectPlanningPage).
- Route: add to `frontend/src/router/routes/projects.ts` (mirror the `/projects/:projectId/planning` entry at ~`:32`): `path: '/projects/:projectId/research'`, lazy `component: () => import('../../views/ProjectResearchPage.vue')`, `props: true`, `meta: { requiresEntity: 'projectId' }`. Registered via the spread in `frontend/src/router/index.ts`.
- API module: `frontend/src/services/api/research.ts` (new), re-export in `frontend/src/services/api/index.ts` barrel (alongside `grdApi` at `:66`). Methods: `startResearch(projectId, question, opts)`, `resumeThread(projectId, threadId)`, `listThreads(projectId)`, `getThread(projectId, threadId)`, `streamResearch(projectId, sessionId)`.
- Composable: `frontend/src/composables/useResearchSession.ts` mirroring `usePlanningSession.ts:56-143` (the `createAuthenticatedEventSource` + `.addEventListener('output'|'question'|'complete'|'error')` + cleanup pattern).
- Components (under `frontend/src/components/grd/research/`): `QuestionIntake.vue`, `ThreadList.vue` (status/iteration rows), `HypothesisLedger.vue`, `ReportViewer.vue` (renders FINDING.md — **reuse the existing markdown renderer but NOT the known-broken `MarkdownContent`**; verify which renderer is safe at execution time), `PortfolioRuns.vue` (aggregate thread list).

SSE: `apiFetch` lives in `frontend/src/services/api/client.ts`; SSE via `createAuthenticatedEventSource(url, opts)` (uses `@microsoft/fetch-event-source`, auth headers). Mirror `grdApi.streamSession` (`frontend/src/services/api/grd.ts`).

---

## §4 — Life-Harness Completion UI (REQ-16)

Backends are fixed contracts (see §2 Group B). New frontend only.

- **API module:** `frontend/src/services/api/grdHarness.ts` (new) — methods wrapping Group A (16 routes) + Group B (autonomy get/set, rounds list/detail/impact/apply/abort/**revert**, shared-forge list, adopt). Note `/admin` base + admin auth.
- **Autonomy policy editor:** `frontend/src/components/grd/harness/AutonomyEditor.vue` — GET `/admin/projects/{id}/autonomy`, render `AutonomyPolicy` fields as a form (mirror `GrdSettings.vue` form patterns at `frontend/src/components/settings/GrdSettings.vue`), PUT on save.
- **Round revert:** `RoundList.vue` + `RoundDetail.vue` with a revert action → POST `/admin/evolution/rounds/{rid}/revert` (guard with a confirm; revert is destructive/git-reversible).
- **Shared-forge browse/adopt:** `SharedForgeBrowser.vue` — GET `/admin/shared-forge`, adopt button → POST `/admin/projects/{id}/adopt-shared/{bindingId}`.
- **16-route panels:** a `HarnessPanelHost.vue` (tabbed) mounting Health/Think/Dead-Ends/Genome/Verify/Reflections+Verdicts/Evolve panels. Reuse the repo's existing `TabbedViewHost` (per MEMORY.md sidebar-prune work) if present — verify at execution time.
- **Mount:** add a `/projects/:projectId/harness` route (mirror §3) OR mount the panel host inside the existing planning/settings surface. Recommend a dedicated route for clarity; confirm sidebar IA placement (MEMORY.md: a sidebar slot must be a daily/entry-point surface — harness panels likely live under the project, not top-level nav).

---

## §5 — PlanningCommandBar Manifest (REQ-17)

**Current state (verified):** `frontend/src/components/grd/PlanningCommandBar.vue` (~`:15-53`) already defines a **declarative** `commandGroups` const: `Array<{ labelKey, commands: Array<{ name, labelKey, descKey }> }>`, grouped (Project Setup / Phase Management / Research & Analysis / Requirements). Mounted in `ProjectPlanningPage.vue` (emits `invoke`, handled by `handleInvokeCommand`). It is already manifest-shaped — REQ-17 is **completing + regrouping** it, not building a registry.

**Proposed manifest:** extract `commandGroups` to a standalone module `frontend/src/components/grd/planningCommands.ts` (so it's testable + reusable), typed as:
```ts
export interface GrdCommand { name: string; labelKey: string; descKey: string }
export interface GrdCommandGroup { labelKey: string; commands: GrdCommand[] }
export const GRD_COMMAND_MANIFEST: GrdCommandGroup[]
```
Groups per success criterion 4: **Plan / Execute / Verify / Research / Harness / Misc.** Populate from the supported `/grd:` set (the skills list: plan-phase, plan-milestone-gaps, autoplan, discuss-phase / execute-phase, autopilot, quick / verify-phase, verify-work, assess-baseline / research, survey, deep-dive, compare-methods, feasibility / harness, evolve(deprecated), settings, sync, map-codebase / progress, help, etc.). Mark deprecated (`evolve`) appropriately. Each command → i18n keys under `planningCommandBar.cmd.*`.

The `invoke` path currently calls `grdApi.invokePlanningCommand` → a `grd_chat`/planning session. Research commands should route to the new research-start path (§1e) when `group === 'research'`; harness commands may deep-link to §4 panels instead of spawning a session. The planner should decide invoke-routing per group.

---

## §6 — i18n Plan (REQ-18)

- Catalogs: `frontend/src/locales/{en,ko,ja,zh}.json`. Convention: nested objects under a top-level surface namespace, dot-accessed via `t('ns.key')`. Existing example: `planningCommandBar.{title,groups.*,cmd.*}`.
- New namespaces (key-identical across all 4): `surface.research.*` (intake, thread list, ledger, report, portfolio), `surface.harness.*` (autonomy, rounds, forge, the 7 panels), and additions to `planningCommandBar.cmd.*` / `planningCommandBar.groups.*` for the new command groups.
- `useI18n` usage: `const { t } = useI18n()` then `t('surface.research.title')` (example: `frontend/src/components/settings/GrdSettings.vue:4`).
- **Parity check approach:** the repo enforces key-identity by convention. At execution time, write/borrow a tiny key-diff script (`jq`-based: compare key sets of the 4 catalogs) and run it as a verification step. Korean `*.ko.md` doc siblings are required only for prose docs (MEMORY.md), not for these UI catalogs.

---

## §7 — Test Strategy per Area

| Area | Suite type | Mirror example | Notes |
|---|---|---|---|
| `grd_research` handler | backend pytest | `backend/tests/test_grd_chat_handler.py` (spy_psm fixture, asserts on `create_session` kwargs: execution_type, stream_json, use_pty, cmd) | assert `execution_type="grd_research"`, prompt `/grd:research <json.dumps(question)>`, cwd resolution, stop |
| autoresearch routes | backend pytest | route tests using `isolated_db` + Litestar `TestClient`; spy on `module.logger.warning` via monkeypatch (CLAUDE.md: TestClient logger doesn't propagate to caplog) | mock `GrdCliService`/disk reads; test thread-list, thread-bundle, start→session_id |
| SSE streaming | backend pytest | grd_chat bridge test `backend/tests/test_grd_chat_bridge.py` (if reusing generic session SSE, test the route emits session output) | Level 2 proxy; real PSM loop is Level 3 deferred |
| `research.ts` / `grdHarness.ts` | frontend vitest | `frontend/src/services/api/__tests__/bot-health.test.ts` (`vi.mock('../client')`, assert `apiFetch` called with path) | one test per method asserting path/method/body |
| Research page components | frontend vitest | `frontend/src/webmcp/__tests__/page-specific-tools.test.ts` (mount + @vue/test-utils + nextTick) | per-component: intake, thread list, ledger, report |
| harness panels | frontend vitest | same | per-panel render + api-call assertion |
| `useResearchSession` | frontend vitest | `frontend/src/composables/__tests__/useProjectSession.test.ts` (mock grdApi + EventSource) | mirror |
| PlanningCommandBar manifest | frontend vitest | component test mounting the bar, asserting groups render + `invoke` emits | manifest module is plain TS — also unit-test the manifest shape |

**House gates (must pass, REQ "no new failures"):** `just build` (vue-tsc + vite) · `cd backend && uv run pytest` (12-min watchdog; on the known ~40-48% hang, run targeted set: all touched suites + execution/streaming/harness regressions, disclose substitution) · `cd frontend && npm run test:run` (no NEW failures vs the 7-failure baseline; do NOT touch RateLimitGauge/MarkdownContent/WorkingMemoryView/useTourMachine).

---

## §8 — Proposed Plan Decomposition (skeleton for the planner)

**Wave A — backend + api plumbing (parallel):**
- **Plan 20-01 — Autoresearch backend (REQ-14):** `GrdResearchSessionHandler` + registry entry; `research()` family on `GrdCliService` (or `grd_research_service.py`) incl. on-disk thread browser; new `/api/projects/{id}/research/*` routes; handler + route + SSE tests. *Deps: none (mirrors grd_chat).*
- **Plan 20-02 — Frontend api modules (REQ-15/16 plumbing):** `research.ts` + `grdHarness.ts` (all §2 + §1e routes) + barrel export + api-module tests. *Deps: 20-01 route shapes (can stub/parallelize against the route table in §2).*

**Wave B — UI surfaces (parallel, each consumes Wave A):**
- **Plan 20-03 — Research page (REQ-15):** `ProjectResearchPage.vue` + route + `useResearchSession` + intake/thread-list/ledger/report/portfolio components + tests. *Deps: 20-01, 20-02.*
- **Plan 20-04 — Life-harness panels (REQ-16):** autonomy editor, round list/detail/revert, shared-forge browse/adopt, 7 panels for the 16 routes, panel host + route + tests. *Deps: 20-02.*
- **Plan 20-05 — PlanningCommandBar manifest (REQ-17):** extract `planningCommands.ts`, regroup to Plan/Execute/Verify/Research/Harness/Misc, wire invoke-routing (research→§1e, harness→§4), tests. *Deps: 20-03/20-04 for deep-link targets (or stub routes).*

**Wave C — parity + gates:**
- **Plan 20-06 — i18n parity + house-gate green (REQ-18):** add `surface.research.*`, `surface.harness.*`, expanded `planningCommandBar.*` to all 4 catalogs key-identical; key-diff verification; full gate run (build + frontend no-new-failures + targeted backend). *Deps: 20-03/04/05 (all strings exist).*

Dependencies are tight but the waves are clean: A unblocks B; B unblocks C. 20-04 and 20-05 can start as soon as 20-02 lands.

---

## §9 — Risks / Unknowns / Verify-at-Execution

1. **`gd research report`/`portfolio` are not CLI subcommands (HIGH confidence).** Success criterion 1 implies them; treat report=read `FINDING.md`, portfolio=thread aggregate. Confirm with `gd research --help` on the live binary at execution; if a real subcommand exists, prefer it.
2. **`.planning/research/threads/` does not exist yet.** The thread-browser code must handle the empty/missing dir gracefully (return `[]`). **Dogfood (MEMORY.md): run ≥1 real `gd research` thread through the parser before declaring the browser done** — hand-crafted fixtures will miss real frontmatter format quirks.
3. **`/admin` vs `/api` base + auth.** Group B/C routes are admin-gated; the frontend client must carry admin auth to the `/admin` base. Verify `client.ts` admin-auth handling before wiring grdHarness.ts.
4. **Markdown rendering for FINDING.md / ledger.** `MarkdownContent` is in the 7-failure baseline — do **not** reuse it blindly. Verify which markdown renderer the repo uses elsewhere (e.g. in chat) and is green.
5. **`TabbedViewHost` reuse.** MEMORY.md says a reusable tabbed host exists from the sidebar-prune work; confirm its path/API before building a new panel host.
6. **Sidebar IA placement (MEMORY.md "judgment can't be auto-classified").** Don't auto-add a top-level sidebar slot for research/harness just because the backend exists; place under the project surface unless it's a daily entry-point. Defer the nav decision to a product call.
7. **Backend serial-suite hang (~40-48%).** Known; use the 12-min watchdog + targeted-set procedure and disclose substitution in the PR.
8. **No CONTEXT.md / no LANDSCAPE/PAPERS/KNOWHOW research files** exist for this milestone (research dir empty) — this is a wiring phase, not an R&D phase; paper-backed recommendations are N/A. Confidence rests on verified live code, which is the right authority here.

## Sources

### Primary (HIGH — verified in live code via CodeGraph + grep/read)
- `backend/app/services/execution_type_handler.py` — `GrdChatSessionHandler` :683, `start`/cmd :753-767, `HANDLER_REGISTRY` :824/:830, `get_handler` :834.
- `backend/app/services/grd_cli_service.py` — `run_gd` :170, `run_gd_json` :185, `get_health` :299, `think` :315, `genome_show` :373, `verify_mechanical` :403.
- `backend/app_litestar/routes/grd_routes.py` — 16 GRD/DB-mirror/evolve routes (table §2), `grd_router` :1658; chat route :515.
- `backend/app_litestar/routes/harness_evolution.py` — rounds/revert :103, shared-forge :115, adopt :122, autonomy get/set :129/:142, `Router(path="/admin")` :165.
- `backend/app_litestar/routes/harness_takeaways.py` — takeaway routes :13/:31/:47/:55/:61.
- `backend/app/db/project_autonomy_config.py`, `backend/app/models/autonomy_policy.py` — autonomy storage/model.
- `~/.claude-personal1/plugins/cache/claude-plugin-marketplace/grd/0.4.4/commands/research.md` — `gd research` CLI surface + thread layout (HYPOTHESES/THREAD/FINDING).
- Frontend: `PlanningCommandBar.vue` (declarative `commandGroups`), `services/api/{client.ts,grd.ts,index.ts}`, `composables/usePlanningSession.ts:56-143` (SSE), `views/ProjectPlanningPage.vue`, `router/routes/projects.ts`, `locales/{en,ko,ja,zh}.json`, tests `services/api/__tests__/bot-health.test.ts`, `webmcp/__tests__/page-specific-tools.test.ts`, `composables/__tests__/useProjectSession.test.ts`.
- Phase 19 docs: `.planning/milestones/anonymous/phases/19-grd-default-driver/19-04-SUMMARY.md`, `19-RESEARCH.md` (grd_chat + bridge pattern).

### Secondary (MEDIUM)
- GRD plugin spec `docs/superpowers/specs/2026-05-25-autoresearch-loop-spine-design.md` (autoresearch loop stations; reported by sub-agent, not line-verified).

## Citation Recovery

N/A — wiring phase, no academic citations. No PAPERS.md / citation graph for this milestone.

| Component | Source | Status | Priority |
|-----------|--------|--------|----------|
| autoresearch loop | grd plugin research.md | Resolved | Normal |

**Unresolved critical dependencies:** 0

## Metadata

**Confidence breakdown:**
- Backend handler/route patterns: HIGH — read live code with line anchors.
- 16-route inventory + wired/unwired status: HIGH — read route files + grepped frontend for callers.
- `gd research` CLI surface: HIGH for start/resume/status (read research.md); MEDIUM for report/portfolio (inferred — flagged in §9.1).
- Frontend conventions: HIGH — verified component/api/test paths.

**Research date:** 2026-06-13
**Valid until:** ~30 days (stable internal codebase; GRD plugin version pinned at 0.4.4)

## RESEARCH COMPLETE
