# Architecture Research

**Domain:** Flask+Vue bot automation platform — production evolution
**Researched:** 2026-02-25
**Confidence:** HIGH (codebase directly inspected; patterns verified via Context7 and official docs)

---

## Standard Architecture

### Current State (As-Built)

```
┌──────────────────────────────────────────────────────────────┐
│  Browser (Vue 3 SPA, Port 3000 dev / Flask static prod)      │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP + SSE
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  Flask (flask-openapi3, Port 20000)                          │
│  44+ APIBlueprints, no auth middleware                       │
│                                                              │
│  Services (90+ classes, class-level singletons)              │
│  ├── In-memory state (~10 services)  ← blocks scaling        │
│  ├── subprocess: claude/opencode/gemini/codex CLIs           │
│  ├── APScheduler (background cron)                           │
│  └── threading.Queue → SSE fans                              │
│                                                              │
│  SQLite (single file, agented.db)                            │
│  Raw SQL, 53 migrations in one 3,210-line file               │
└──────────────────────────────────────────────────────────────┘
```

**Critical structural problems for production:**
- No auth layer — every route is open
- In-memory SSE queues and subprocess state are incompatible with >1 Gunicorn worker
- Flask dev server (`python run.py`) used as production runtime
- `execution_service.py` at 1,387 lines owns too many responsibilities
- `migrations.py` at 3,210 lines mixes schema evolution with seeding and operational logic

---

### Target Architecture (Production-Ready)

```
┌──────────────────────────────────────────────────────────────┐
│  Browser (Vue 3 SPA)                                         │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTPS
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  Nginx (reverse proxy)                                       │
│  - Serves frontend/dist/ as static files                     │
│  - Proxies /api/* /admin/* /health/* → Gunicorn              │
│  - TLS termination                                           │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  Gunicorn (gevent workers, 4-8 workers)                      │
│  Flask app (flask-openapi3)                                  │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Auth Middleware (before_request)                     │    │
│  │  - Static API key for single-user/self-hosted use   │    │
│  │  - JWT (flask-jwt-extended) for multi-user future   │    │
│  │  - Bypass for /health/*, /github/webhook (HMAC)     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Route Layer (44+ APIBlueprints, unchanged surface)          │
│                                                              │
│  Service Layer (refactored)                                  │
│  ├── ExecutionCoordinator  ← split from ExecutionService     │
│  ├── PromptRenderer        ← extracted from ExecutionService │
│  ├── SubprocessRunner      ← extracted from ExecutionService │
│  ├── RateLimitDetector     ← extracted from ExecutionService │
│  └── [other services unchanged initially]                    │
└──────┬──────────────────────────────────────────────────────┘
       │
       ├── SQLite (retain for single-machine; path toward Postgres)
       ├── Redis (new: pub/sub for SSE fan-out, dedup state)
       ├── subprocess: claude/opencode/gemini/codex CLIs (unchanged)
       └── APScheduler (unchanged, single-process)
```

---

## Component Responsibilities

| Component | Responsibility | Current Implementation | Target Implementation |
|-----------|----------------|------------------------|-----------------------|
| Nginx | TLS, static serving, proxy routing | Not present (Vite dev proxy only) | nginx reverse proxy + static Vue build |
| Gunicorn | WSGI process management, concurrency | Present but unconfigured | Configured with gevent workers + worker count |
| Auth Middleware | Request authentication gate | Not present | `app.before_request` + API key or JWT |
| Route Layer | HTTP API surface, OpenAPI spec | 44+ APIBlueprints, unchanged | Unchanged; auth enforced below route level |
| ExecutionService | CLI subprocess lifecycle | 1,387-line god module | Split into 4-5 focused classes |
| ExecutionLogService | SSE log streaming | In-memory Queue per process | Redis pub/sub for cross-worker SSE |
| ProcessManager | Subprocess tracking | In-memory dict | Persisted to DB + in-memory cache |
| RateLimitService | Detect provider rate limits | Class-level dict | Redis-backed or DB-backed state |
| SchedulerService | APScheduler cron management | Class-level singleton | Unchanged (single-process constraint) |
| SQLite DB | Persistent state | Raw SQL, 53 migrations | Retain SQLite; extract seeding from migrations.py |
| Migrations | Schema evolution | 3,210-line single file | Split: schema.py owns DDL, migrations append-only, seeding in separate module |

---

## Recommended Project Structure (Backend Evolution)

The current `backend/app/` structure is sound. Target changes are additive — no directory restructuring needed.

```
backend/app/
├── __init__.py              # create_app() — add auth init
├── auth/                    # NEW: auth layer
│   ├── __init__.py
│   ├── middleware.py        # before_request handler; bypass list
│   └── tokens.py           # API key validation or JWT helpers
├── db/
│   ├── migrations.py        # Append-only migration history (no seeding)
│   ├── seeds.py             # NEW: extracted seed functions (predefined triggers, MCP servers)
│   └── [domain files unchanged]
├── services/
│   ├── execution_service.py         # Reduced: orchestration entry point only
│   ├── execution_coordinator.py     # NEW: extracted subprocess lifecycle
│   ├── prompt_renderer.py           # NEW: extracted template rendering
│   ├── subprocess_runner.py         # NEW: extracted Popen + thread management
│   └── [all other services unchanged]
└── [routes/, models/, utils/ unchanged]
```

---

## Architectural Patterns

### Pattern 1: Static API Key Middleware (Auth — Phase 1)

**What:** A single shared secret in `Authorization: Bearer <token>` or `X-API-Key: <token>` header, checked in `app.before_request`. Bypass list covers unauthenticated paths (health probes, GitHub webhook which uses its own HMAC).

**When to use:** Single-user or internal-network deployments. Easiest auth primitive to implement and verify.

**Trade-offs:**
- Pro: Zero UX friction, no login flow, no token expiry, no state
- Pro: Works with the existing Vue frontend with a single config change (add header to `apiFetch`)
- Con: Single credential — compromise requires key rotation everywhere
- Con: No per-user identity (upgrade to JWT required for multi-user)

**Build sequence:** `auth/middleware.py` → register in `create_app()` → update `apiFetch` in frontend → update `EventSource` instantiation to pass header (via custom SSE wrapper)

**Source:** Flask `before_request` pattern — HIGH confidence (official Flask docs, multiple verified sources)

```python
# backend/app/auth/middleware.py
from flask import request, jsonify, current_app
import os

BYPASS_PREFIXES = ("/health/", "/github/webhook", "/openapi", "/docs")

def register_auth(app):
    api_key = os.environ.get("AGENTED_API_KEY", "")

    @app.before_request
    def check_auth():
        if not api_key:
            return  # Auth not configured — open access (dev mode)
        path = request.path
        if any(path.startswith(p) for p in BYPASS_PREFIXES):
            return
        provided = (
            request.headers.get("X-API-Key")
            or request.headers.get("Authorization", "").removeprefix("Bearer ")
        )
        if provided != api_key:
            return jsonify({"error": "Unauthorized"}), 401
```

---

### Pattern 2: Redis Pub/Sub for SSE Fan-Out (State Externalization)

**What:** Replace `threading.Queue` in `ExecutionLogService` with Redis pub/sub channels. Each execution has a channel `execution:{id}`. Workers publish log lines; any worker's SSE handler subscribes and streams to the client.

**When to use:** Required when running Gunicorn with `--workers > 1`. Also required for log replay across restarts (store log history in Redis sorted sets or DB, not only in-process list).

**Trade-offs:**
- Pro: Enables multiple Gunicorn workers — any worker can serve any SSE subscription
- Pro: Enables log replay after reconnect without relying on process-local buffer
- Con: Adds Redis as a required infrastructure dependency
- Con: Requires `gevent` or `eventlet` worker class (not default `sync`) for long-lived SSE connections
- Con: Redis pubsub has no persistence — need to read buffered lines from DB on reconnect

**Build sequence:** Add Redis dep → rewrite `ExecutionLogService.subscribe()` to use `redis.pubsub()` → rewrite `ExecutionLogService.append_log()` to also publish → update Gunicorn config to use gevent workers

**Source:** Flask-SSE library uses this exact pattern (Redis-backed SSE); Gunicorn gevent worker docs confirm requirement — HIGH confidence

```
# gunicorn.conf.py (new file)
bind = "127.0.0.1:20000"
workers = 4
worker_class = "gevent"
worker_connections = 1000
timeout = 120
keepalive = 5
```

---

### Pattern 3: God Module Split (ExecutionService)

**What:** Extract the four distinct responsibilities from `execution_service.py` (1,387 lines) into focused modules. The existing public API (`ExecutionService.run_trigger`, `ExecutionService.dispatch_*`) is preserved — callers don't change.

**When to use:** Before adding any new execution features. The current file is already at a complexity level where bugs hide and tests are difficult to write.

**Responsibility split:**

| New Module | Extracted From | Responsibility |
|---|---|---|
| `execution_coordinator.py` | `ExecutionService` | Entry point: validate, call renderer, call runner, handle retry |
| `prompt_renderer.py` | `ExecutionService._render_prompt*` | Template substitution, GitHub data injection, path resolution |
| `subprocess_runner.py` | `ExecutionService._spawn_process*` | `Popen`, thread management, budget monitor thread, PGID kill |
| `rate_limit_detector.py` | `ExecutionService._detect_rate_limit*` | stderr pattern matching, cooldown state, retry scheduling |

`ExecutionService` becomes a thin facade importing from these modules, preserving the existing call sites.

**Trade-offs:**
- Pro: Each file is testable in isolation
- Pro: Rate limit detection logic can change without touching subprocess lifecycle
- Con: Requires careful dependency ordering — coordinator imports renderer and runner; runner imports log service
- Con: Medium refactor risk without comprehensive tests for `run_trigger` first

**Build sequence:** Write integration tests for `run_trigger` end-to-end → extract `prompt_renderer` (pure function, no state) → extract `subprocess_runner` (stateless except ProcessManager) → extract `rate_limit_detector` → `execution_coordinator` becomes the entry point

---

### Pattern 4: Migration File Decomposition

**What:** Stop adding seeding and operational logic to `migrations.py`. Create `backend/app/db/seeds.py` for `seed_predefined_triggers()`, `seed_preset_mcp_servers()`, and `auto_register_project_root()`. Leave `migrations.py` as an append-only schema changelog.

**When to use:** Before the next migration is added (currently at 53 migrations, 3,210 lines). The seeding functions are operationally distinct from schema migration.

**Trade-offs:**
- Pro: `migrations.py` becomes read-only history — new contributors only append
- Pro: Seeds can be independently tested and re-run
- Con: Minor refactor — `create_app()` must import from `seeds.py` instead of `migrations.py`

---

### Pattern 5: Nginx + Gunicorn Deployment (Operational)

**What:** Replace `just deploy` (which runs Flask dev server) with a proper nginx + gunicorn setup. Nginx serves `frontend/dist/` as static files and reverse-proxies API paths to Gunicorn on 127.0.0.1:20000.

**When to use:** Any production or internet-accessible deployment.

**Trade-offs:**
- Pro: Gunicorn provides worker management, restart-on-crash (via systemd or supervisor)
- Pro: Nginx handles TLS termination, request buffering, static caching
- Pro: Separates frontend serving from API — no Flask `spa_bp` needed in production
- Con: Requires nginx and systemd/supervisor configuration
- Con: Multi-process Gunicorn requires Redis for SSE (see Pattern 2); single-process Gunicorn avoids this

**Single-machine, single-process alternative:** Run `gunicorn --workers=1 --worker-class=gevent` to preserve in-memory SSE state while using a production-grade server. This is the minimal viable step before Redis.

**Source:** TestDriven.io "Dockerizing Flask with Postgres, Gunicorn, and Nginx" (Dec 2025 codezup guide); Gunicorn official docs — HIGH confidence

---

## Data Flow

### Request Flow (Current vs. Target)

**Current:**
```
Browser → Flask (dev server, single-threaded)
       → before_request: [nothing]
       → Route handler
       → Service (class-level singleton, in-process state)
       → SQLite
```

**Target:**
```
Browser → Nginx
       → Gunicorn (gevent worker pool)
       → before_request: auth check (API key / JWT)
       → Route handler [unchanged]
       → Service [refactored, same interface]
       → SQLite + Redis (for SSE state)
```

### Key Data Flows

1. **Webhook → Bot Execution (unchanged):**
   `POST /` → `ExecutionService.dispatch_webhook_event()` → `OrchestrationService.execute_with_fallback()` → `ExecutionCoordinator.run_trigger()` → `subprocess.Popen(claude -p ...)` → log threads → `ExecutionLogService.finish_execution()`

2. **SSE Log Stream (post-Redis):**
   `GET /admin/executions/{id}/stream` → worker A subscribes to `redis.pubsub("execution:{id}")` → worker B's log thread publishes to Redis → worker A yields SSE events to browser

3. **SSE Log Stream (pre-Redis, single-worker):**
   `GET /admin/executions/{id}/stream` → same worker subscribes `Queue` → same worker's log thread puts to Queue → yields SSE events (requires `--workers=1`)

4. **Auth Flow (new):**
   Any request → `before_request` → check `X-API-Key` header → 401 if missing/wrong, else pass through

5. **Frontend Auth (new):**
   `apiFetch()` in `client.ts` → adds `X-API-Key: ${config.apiKey}` header on every request → `EventSource` replaced with `fetchEventSource` (or custom wrapper) to pass header

---

## Scaling Considerations

| Scale | Architecture |
|-------|-------------|
| Single user, local | Current architecture acceptable; add API key auth only |
| Single machine, multiple concurrent executions | Gunicorn `--workers=1 --worker-class=gevent` + auth; no Redis needed |
| Single machine, high SSE concurrency | Gunicorn gevent workers + Redis pub/sub for SSE; SQLite write contention acceptable up to ~20 concurrent writes |
| Multi-machine (future) | Redis for all in-memory state; PostgreSQL (via SQLAlchemy) replacing SQLite; external process queue (Celery/RQ) for subprocess dispatch |

**SQLite retention rationale:** For Agented's workload (bots run serially or at low concurrency, not bulk OLTP), SQLite with WAL mode is adequate for single-machine production. The 5-second busy timeout handles burst contention. Migrating to PostgreSQL is a large effort (no ORM, raw SQL rewrites) and is not required unless running multiple machines. Retain SQLite in the near term.

---

## Anti-Patterns

### Anti-Pattern 1: Adding More Class-Level Singletons with In-Memory State

**What people do:** Continue the existing pattern of `_state: Dict[str, ...] = {}` as class variables in new service classes.

**Why it's wrong:** Each new class-level state dict is another blocker for running `--workers > 1`. State fragmentation compounds — a request handled by worker 1 can't see state written by worker 2.

**Do this instead:** New state that must survive across requests goes in SQLite or Redis from day one. In-memory caches are acceptable only if they are derived (can be reconstructed) and have TTLs.

---

### Anti-Pattern 2: Protecting Routes with Per-Route Decorators

**What people do:** Add `@jwt_required()` or `@api_key_required` to individual route handlers one at a time.

**Why it's wrong:** With 44+ blueprints and hundreds of routes, decorator-per-route approach has coverage gaps. Missing one decorator leaves the route open.

**Do this instead:** Use `app.before_request` as the single enforcement point. Maintain an explicit allowlist of unauthenticated paths (health, GitHub webhook HMAC). All other routes are protected by default.

---

### Anti-Pattern 3: Using `EventSource` Directly in Frontend After Auth Is Added

**What people do:** Keep `new EventSource(url)` after adding API key auth to the backend.

**Why it's wrong:** The browser `EventSource` API does not support custom headers. The `Authorization: Bearer` or `X-API-Key` header cannot be set on a native `EventSource`. All SSE streams will get 401.

**Do this instead:** Use `@microsoft/fetch-event-source` (npm) or a custom `fetch`-based SSE wrapper that supports request headers. This affects all composables that use `new EventSource(...)` directly (`useAiChat.ts`, `useProjectSession.ts`, `useWorkflowExecution.ts`, and others).

---

### Anti-Pattern 4: Migrating to PostgreSQL as an Early Phase

**What people do:** Treat the SQLite → PostgreSQL migration as a prerequisite for other production improvements.

**Why it's wrong:** The codebase uses raw SQL with no ORM. Migrating to PostgreSQL requires rewriting every query file in `backend/app/db/` (19+ files, 3,000+ lines of SQL) plus adding `psycopg2` connection pooling. This is a multi-week effort that blocks auth, SSE, and deployment improvements which are higher priority.

**Do this instead:** Keep SQLite with WAL mode for single-machine production. The bottleneck is not the database — it is the lack of auth, single-process deployment, and in-memory SSE. Address those first.

---

### Anti-Pattern 5: Running gunicorn `--workers=4` Without Redis (SSE Breakage)

**What people do:** Increase Gunicorn worker count for performance without first externalizing in-memory SSE state.

**Why it's wrong:** Each worker has independent `ExecutionLogService._log_buffers` and `._subscribers` dicts. A browser connecting to worker 1's SSE endpoint will receive nothing if the subprocess was started by worker 2.

**Do this instead:** Either keep `--workers=1 --worker-class=gevent` (safe, preserves current behavior) or implement Redis pub/sub before increasing workers. The gevent worker class handles SSE concurrency within a single worker via cooperative multitasking.

---

## Build Order (Dependency Graph)

The following order minimizes risk and unblocks subsequent work:

```
Phase 1: Foundation (no user-visible changes)
├── 1a. Gunicorn config file + gevent worker (replaces dev server in prod)
├── 1b. Nginx config for static serving + API proxy
└── 1c. Auth middleware (before_request, API key, bypass list)
    └── Requires: frontend apiFetch header injection + EventSource → fetchEventSource

Phase 2: State Externalization
├── 2a. Redis setup + ExecutionLogService SSE rewrite
│   └── Requires: Phase 1a (gevent workers)
└── 2b. Webhook dedup + rate limit state → Redis/DB (optional, lower priority)

Phase 3: Code Quality
├── 3a. Extract seeds.py from migrations.py (no behavior change)
├── 3b. ExecutionService split (coordinator / renderer / runner / rate-limit-detector)
│   └── Requires: integration test coverage of run_trigger first
└── 3c. App.vue decomposition (frontend: sidebar, toast, global state extraction)

Phase 4: Operational Hardening (can run in parallel with Phase 3)
├── 4a. SECRET_KEY persistence (env var enforcement, documented)
├── 4b. CORS lockdown (CORS_ALLOWED_ORIGINS must be set; no wildcard in prod)
├── 4c. Health endpoint auth (redact active execution details behind auth)
└── 4d. Log rotation + structured logging (replace stdout logging)
```

**Dependency rules:**
- Phase 1c (auth) must complete before Phase 2 (Redis) — auth headers needed by SSE clients
- Phase 3b (ExecutionService split) must have integration tests first — high regression risk
- Phase 1a and 1b are independent and can run concurrently
- Phase 4 items have no prerequisites and can be done in any order

---

## Sources

- Current codebase direct inspection: `backend/app/services/execution_service.py`, `execution_log_service.py`, `backend/app/__init__.py`, `backend/app/db/migrations.py` — HIGH confidence
- Flask `before_request` middleware: [Flask Middlewares — GeeksforGeeks](https://www.geeksforgeeks.org/python/flask-middlewares/), [Flask-HTTPAuth docs](https://flask-httpauth.readthedocs.io/) — HIGH confidence
- Flask-JWT-Extended patterns: Context7 `/vimalloc/flask-jwt-extended` — HIGH confidence
- Gunicorn gevent workers for SSE: Context7 `/benoitc/gunicorn` worker_class docs — HIGH confidence
- Flask-SSE Redis pub/sub pattern: [Flask-SSE docs](https://flask-sse.readthedocs.io/en/latest/quickstart.html), [GitHub flask-sse issue #7](https://github.com/singingwolfboy/flask-sse/issues/7) — HIGH confidence
- Nginx + Gunicorn + Flask deployment: [codezup.com 2025 guide](https://codezup.com/deploy-flask-docker-nginx/), [testdriven.io dockerizing Flask](https://testdriven.io/blog/dockerizing-flask-with-postgres-gunicorn-and-nginx/) — HIGH confidence
- EventSource header limitation (custom header not supported): Browser Web API specification, `@microsoft/fetch-event-source` README — HIGH confidence
- SQLite production adequacy for single-machine: [SQLite.org "Appropriate Uses For SQLite"](https://www.sqlite.org/whentouse.html) — HIGH confidence
- Python dependency injection: [python-dependency-injector docs](https://python-dependency-injector.ets-labs.org/tutorials/flask.html), [Flask-Injector PyPI](https://pypi.org/project/Flask-Injector/) — MEDIUM confidence (noted but not recommended as a near-term action given migration cost)

---

*Architecture research for: Agented — Flask+Vue bot automation platform production evolution*
*Researched: 2026-02-25*
