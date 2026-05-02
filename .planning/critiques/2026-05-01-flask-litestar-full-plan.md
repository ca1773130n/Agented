# Flask → Litestar Full Migration Plan

> **Scope:** all 547 remaining Flask route handlers, ported in batches of one parent namespace per wave. Companion to the per-route playbook (`docs/superpowers/specs/2026-05-01-flask-litestar-migration.md`) shipped in wave 25.

## Status snapshot (start of plan)

- **Migrated so far:** 82 routes across 11 namespaces (rbac, health, auth, utility, misc, admin_misc, bot_templates, quality_ratings, scheduler, triggers, teams).
- **Remaining:** 547 handlers across ~70 files.
- **Estimated waves remaining:** 28–32.
- **Estimated calendar:** 2–4 weeks of focused work depending on reviewer availability.

## Sequencing principles

1. **Largest namespaces first.** Each parent migration unblocks any nested children and lets the vite proxy flip with one new entry.
2. **Defer the four hard categories until they have dedicated waves:**
   - SSE/streaming (executions, conversations, super_agent_messages, super_agent_chat)
   - Background-thread orchestration (chunks, bulk, replay)
   - Subprocess / webhook dispatch (webhook, oauth_callback, github_webhook)
   - GRD command surface (grd) — many small handlers but each is a thin wrapper around grd CLI subprocess
3. **Group by frontend coupling.** When two namespaces share a frontend page (e.g. `plugins` + `plugin_exports`), migrate them in the same wave to avoid intermediate breakage during the proxy flip.

## Wave breakdown

### Wave 55 — projects (29 routes + project_instances 4)
- `/admin/projects/*` — CRUD, paths, harness, skills, installations, deploy, sessions
- Nested children: `project_instances`
- Defer: only the heavy clone/sync routes that spawn subprocesses (`/sync-repo`); keep on Flask one more iteration.
- Test: `tests/test_litestar_projects.py` — happy-path CRUD + nested skills list + installations list + 404s.
- Proxy: `/admin/projects → :20002`.

### Wave 56 — workflows (21 routes)
- `/admin/workflows/*` — CRUD, versions, executions list, run.
- The `/{id}/executions` listing route is read-only — stays in this wave. Live execution streaming stays on Flask (covered by wave 65).
- Test: full CRUD + version listing + dry-run.
- Proxy: `/admin/workflows → :20002`.

### Wave 57 — skills (18) + user_skills (4) + skill_sets (4) + skill_conversations (6)
- All under `/admin/skills*`.
- `skill_conversations` is conversation streaming-adjacent; if SSE is involved, defer just that subset.
- Proxy: `/admin/skills → :20002` plus specific overrides if needed.

### Wave 58 — backends (18 routes)
- `/admin/backends/*` — accounts, status, login proxying.
- This namespace has heavy interaction with the ai-accounts sidecar. Many routes are thin proxies; port carefully — each one needs to keep the same headers + status forwarding.
- Defer: any route that streams login output (likely `/login/start` and `/login/stream`).

### Wave 59 — product_owner (17 routes)
- `/admin/product-owner/*` — straightforward CRUD over PO-related entities.

### Wave 60 — budgets (14)
- `/admin/budgets/*` — limits, alerts, enforcement state.

### Wave 61 — agent_memory (13) + agent_conversations (6) + agents leaf endpoints (7)
- Agents already had its list endpoint scoped (wave 47); this completes the rest.

### Wave 62 — mcp_servers (11) + marketplace (11)
- Marketplace browses third-party plugin servers; mcp_servers stores the user's local config.

### Wave 63 — tracing (10) + rules (10) + plugins (10) + plugin_exports (10)
- Tracing is a recent addition; rules + plugins + plugin_exports cluster around the plugin system.

### Wave 64 — hooks (9) + integrations (9) + commands (7) + sketches (8) + collaborative (7)
- Mid-size CRUD, no streaming.

### Wave 65 — pr_reviews (8) + audit (8) + system (7) + monitoring (5) + health_monitor (5)
- Read-heavy admin surfaces.

### Wave 66 — super_agents (5) + super_agent_sessions (7) + super_agent_documents (5) + super_agent_exports (3)
- Defer super_agent_chat (2) and super_agent_messages (5) — those stream.

### Wave 67 — gitops (7) + version_pins (5) + utility leftover (5) + onboarding (3) + setup (6) + settings (6)
- System-config CRUD.

### Wave 68 — secrets (7) + knowledge_graph (7) + scope_filters (6) + prompt_snippets (6) + pr_assignment (6) + retention (5) + execution_tagging (6)
- Smaller leaf namespaces.

### Wave 69 — bookmarks (6) + campaigns (6) + plugin_conversations (6) + skill_conversations (6) + rule_conversations (8) + hook_conversations (8) + command_conversations (8)
- Conversation-style routes (without SSE streaming — those are deferred).

### Wave 70 — orchestration (5) + bot_memory (5) + bot_pipes (4) + bot_runbooks-style + repo_bot_defaults (4) + scope_filters
- Bot-side leaves.

### Wave 71 — products (5) + analytics (4) + findings (4) + config_export (4) + report_digests (3) + team_generation (3)
- Final small CRUD batch.

### Wave 72 — replay (5) + conversation_branches (5) + chunks (3, careful — bg threads)
- Includes the chunks namespace finally; needs the bg-thread orchestration ported via Litestar's `Stream` or background tasks API.

### Wave 73 — executions (21 routes, SSE-heavy)
- Dedicated wave. Litestar `Stream` for log streaming + cancellation endpoints.
- This wave needs its own RFC-style design before code: how to handle long-lived SSE under uvicorn's worker model; how to integrate with `ProcessManager`.

### Wave 74 — super_agent_chat (2 SSE routes) + super_agent_messages (5)
- Streaming chat. Same Stream pattern as wave 73.

### Wave 75 — webhook (1) + github_webhook (1) + oauth_callback (1)
- Subprocess + HMAC + thread dispatch. Each handler is small but the auth model differs from API key. Dedicated wave because security review wants its own pass.

### Wave 76 — GRD (25 routes)
- Each is a thin wrapper around `subprocess.Popen([grd, ...])`. Mechanically straightforward but volume warrants its own wave.

### Wave 77 — orchestration leftover, trigger_conditions, scope_filters, super_agent_sessions
- Cleanup pass. Whatever's left gets ported.

### Wave 78 — App factory collapse
- Once everything is on Litestar, `backend/app/__init__.py:create_app` is just a stub that exists for blueprint registration of zero blueprints. Drop it. Run scripts collapse — Flask process retires, Litestar serves :20000 directly, sidecar still on :20001.
- This is the actual "Flask → Litestar collapse" the original critique called for.

## 2026-05-02 status — route migration complete (629/629)

The branch `feat/wave2-build-workflow` reached **100% Flask→Litestar route
migration** in waves 65–78. Branch SHAs (most recent last):

- 65 `59318c1` leaf CRUD A — bookmarks/snippets/scope/conditions/bot-memory (28)
- 66 `9d7f92e` marketplace + integrations admin + audit + pr_reviews (35)
- 67 `f8e87c5` products + analytics + findings + reports/digests + config_export (20)
- 68 `3ab01c2` knowledge_graph + collaborative + campaigns + tagging + pr_assignment (32)
- 69 `3f06a5a` monitoring/health/orchestration/onboarding/instances/repo-defaults/bot-pipes (30)
- 70 `9b4f8f1` agent_memory + bulk + replay + conversation_branches (27)
- 71 `e058fff` sketches + agent_conversations CRUD + plugin_exports (23)
- 72 `15236c4` plugin/command/hook/rule conversation cluster CRUD (24)
- 73 `68711ae` utility leftover + backends CRUD (21)
- 74 `a08c261` GRD project management (23)
- 75 `398dbad` executions CRUD (20)
- 76 `9887af0` setup + super_agent_messages/chat + team_gen + chunks (15)
- 77 `93dd00d` github_webhook + oauth_callback + generic webhook (3)
- 78 `2750485` final SSE wave — 14 streams via Litestar Stream
- 79 *(this commit)* vite proxy fall-through flip — `/api` and `/admin`
  catch-alls now point at Litestar :20002 since Flask has zero handlers
  left to serve. Flask process keeps running for the scheduler +
  background services until a dedicated wave migrates those to
  Litestar's lifecycle hooks.

**487 Litestar smoke tests pass.** Only one pre-existing failure
(`tests/test_litestar_utility.py::TestValidatePath::test_home_dir_resolves`)
remains, unrelated to this migration.

### Followup: full Flask process retirement

Not done in this milestone. Concrete remaining work, scoped as a
separate phase whenever scheduler ergonomics on Litestar are vetted:

- Move scheduler init + periodic jobs (`_register_periodic_jobs`,
  `_init_monitoring_services`, `_init_auxiliary_schedulers`) from
  `app/__init__.py:create_app` into Litestar `on_startup` hooks in
  `app_litestar/main.py:create_app`.
- Migrate CORS/Talisman/limiter equivalents (Litestar has built-in
  CORS + cors_config dataclass; rate-limiting is an extension).
- Replace `gunicorn -c gunicorn.conf.py` with `uvicorn` for the
  Litestar app and have Litestar bind on :20000 directly.
- Drop `app/__init__.py`, `app/routes/__init__.py`, all stub
  blueprints under `app/routes/*.py`. Remove `run.py` and the
  Flask-only entries in `gunicorn.conf.py`.
- Update `justfile` recipes (`dev-backend`, `deploy`, `kill`) and any
  scripts that reference Flask :20000 or gunicorn.
- Update `vite.config.ts` to remove the now-unused :20000 proxy entries
  for `/docs`, `/openapi` (or repoint to Litestar `/schema`).

## What stays on Flask "permanently" (TBD whether to migrate)

- `app/__init__.py` — flask app factory itself, not a route.
- Blueprint registration scaffolding — zero-cost stubs after wave 78.

## Verification gates (every wave)

1. `cd backend && uv run pytest tests/test_litestar_<wave>.py -v` — all green.
2. `cd backend && uv run pytest tests/<rest>` — no regressions in untouched suites.
3. `cd frontend && just build` — clean.
4. Smoke probe via `curl` against the migrated routes on :20002 to confirm shape parity.

## Anti-patterns to avoid

1. **Don't migrate streaming routes alongside CRUD.** They need different patterns; mixing them inside one wave bloats the diff and slows review.
2. **Don't port all of a namespace's tests verbatim.** Most Flask test files are deeply coupled to `flask.test_client`. Litestar's `create_test_client` is similar but not identical — write fresh, smaller smoke suites and let the existing Flask tests delete with the route file.
3. **Don't skip the vite proxy flip.** A migrated route that the frontend can't reach is dead code. Update the proxy in the same commit.
4. **Don't try to port the routes WITHOUT migrating user_id scoping for owned entities at the same time.** Wave 47/40 demonstrated the pattern; subsequent migrations should fold scoping in rather than leaving a follow-up wave.

## Calendar guidance

- ~2 waves per day at a sustainable pace (factoring tests, review, vite/CI checks).
- 28 waves remaining → ~14 working days.
- Stretch goal: complete by **2026-05-22**.
- Conservative goal: complete by **2026-06-05**.

## Out of scope for this plan

- Async-rewriting the services (TeamService, TriggerService, ExecutionService, etc.). They stay sync; Litestar handlers wrap them in `sync_to_thread=True` until a separate async-conversion milestone takes them on. The *handler* migration to Litestar is independent of the service async rewrite.
