# Project Research Summary

**Project:** Agented — Agentic Development Platform
**Domain:** Flask + Vue.js agentic development platform — production hardening
**Researched:** 2026-02-25
**Confidence:** HIGH

---

## Executive Summary

Agented is a feature-complete single-org internal tool for orchestrating AI CLI bots (Claude, OpenCode, Gemini, Codex) via webhook, GitHub, schedule, and manual triggers. The platform already ships DAG-based workflow execution, SSE log streaming, agent topology management, budget enforcement, account rotation, and a GRD planning UI. The gap is not features — it is production readiness: no authentication, no production WSGI configuration, in-memory state that prevents multi-worker deployment, and a Flask dev server used as the production runtime. The research confirms this is a hardening milestone, not a feature milestone.

The recommended approach is strictly additive and sequenced by risk reduction per effort. The order is: stable SECRET_KEY + env config, then Gunicorn + gevent (fixing SSE concurrency), then API key authentication with EventSource replacement, then security headers + rate limiting, then observability. Critically, `--workers 1` must be enforced as a documented constraint until Redis pub/sub is introduced for SSE fan-out — running multiple workers without externalizing in-memory state will silently break SSE subscriptions. The architecture research confirms SQLite is appropriate for single-machine production and the PostgreSQL migration path should not be attempted until auth and deployment concerns are resolved.

The research identified ten concrete pitfalls specific to this codebase. The three most dangerous are: (1) auth middleware that misses the webhook receiver or double-wraps GitHub HMAC validation, (2) browser `EventSource` being incapable of setting custom headers — every SSE endpoint breaks silently after auth is added unless short-lived query-string tokens or cookie auth are used, and (3) gevent monkey patching breaking APScheduler and the subprocess PGID kill pattern. The research provides verified prevention strategies for all ten pitfalls and maps each to a specific implementation phase.

---

## Key Findings

### Recommended Stack

Existing stack (Flask 2.x + flask-openapi3, Vue 3.5 + TypeScript + Vite, SQLite, APScheduler, subprocess CLI execution, Gunicorn 21.x) is retained as-is. The following additions are recommended in priority order:

| Addition | Version | Purpose | Priority |
|----------|---------|---------|----------|
| `python-dotenv` | 1.2.1 | `.env` loading; fixes SECRET_KEY regeneration bug | P1 — immediate |
| `gevent` | 24.x | Gunicorn async workers; required for concurrent SSE | P1 — immediate |
| `gunicorn.conf.py` | — | Production WSGI config; `workers=1`, `worker_class=gevent` | P1 — immediate |
| `flask-jwt-extended` | 4.7.1 | JWT auth for API routes; supports multi-user future | P1 — auth phase |
| `flask-talisman` | 1.1.0 | CSP, HSTS, X-Frame-Options, X-Content-Type-Options | P1 — security phase |
| `flask-limiter` | 4.1.1 | Per-route rate limiting; Redis-upgradeable backend | P1 — security phase |
| `sentry-sdk[flask]` | 2.52.0 | Error tracking + performance monitoring | P2 — observability |
| Caddy 2.x | — | Reverse proxy; zero-config TLS; replaces dev serving | P2 — deployment |
| `ruff` | 0.15.2 | Linter + formatter; replaces Black + Flake8 in CI | P3 — code quality |
| SQLAlchemy + Alembic | 2.0.46 / 1.18.4 | DB migration tooling — Phase 2 only, if PostgreSQL planned | Deferred |

**What to avoid:** Flask-Login (session-based, wrong for API-first), flask-security-too (forces SQLAlchemy ORM), uWSGI (maintenance mode), gunicorn `--workers > 1` without Redis, Flask dev server for any production traffic.

### Expected Features

**Table stakes (required for production-safe launch):**
- API authentication (shared API key via `app.before_request` — single env var, zero login UX)
- CORS lockdown (explicit `CORS_ALLOWED_ORIGINS`; fail-closed if unset)
- Stable `SECRET_KEY` (env var; currently regenerates on every restart)
- Gunicorn + gevent WSGI config (`workers=1`, `worker_class=gevent`)
- Process supervisor with restart-on-crash (systemd unit file or Docker `restart: unless-stopped`)
- Structured logging with request IDs (Python `logging` + JSON formatter; no new dep)
- DB-backed webhook deduplication (replaces in-memory dict that leaks and resets on restart)
- `.env.example` with all environment variable documentation

**Should-have after initial hardening (v1.x):**
- Prompt injection guardrails (truncation + sanitization of externally-sourced content)
- Health endpoint hardening (strip sensitive fields from unauthenticated response)
- CLI tools health check on dashboard (surface `claude`/`opencode`/`gemini`/`codex` binary status)
- Execution replay / retry UI (re-run stored trigger params — high DX value for debugging)

**Defer to v2+:** Webhook payload inspector, execution concurrency control, workflow live visualization, OpenTelemetry trace export, rate limit notifications.

**Anti-features (deliberately avoid):** Multi-tenant user accounts + RBAC, PostgreSQL migration (as an early phase), Redis pub/sub (before single-worker constraint is a real bottleneck), horizontal scaling / Kubernetes, CI/CD pipeline integration.

### Architecture Approach

The current architecture is structurally sound for the hardening goal. Changes are additive — no directory restructuring needed.

**New component: `backend/app/auth/`**
- `middleware.py` — `app.before_request` handler with explicit bypass allowlist: `["/", "/api/webhooks/github/", "/health/*", "/docs/*", "/openapi/*"]`
- `tokens.py` — API key validation helpers (JWT helpers for future multi-user path)

**Existing component modifications:**
- `backend/app/__init__.py` — register auth middleware; add `sentry_sdk.init()`, `load_dotenv()`
- `backend/gunicorn.conf.py` (new file) — `workers=1`, `worker_class=gevent`, `timeout=120`
- `backend/app/db/migrations.py` — append-only schema changelog; seeding extracted to `seeds.py`
- `backend/app/db/seeds.py` (new file) — extracted seeding functions from `migrations.py`
- Frontend `apiFetch()` — add `X-API-Key` header on every request
- Frontend SSE composables — replace `new EventSource(url)` with `@microsoft/fetch-event-source` or short-lived query-string token approach

**Key patterns:**
1. Auth as single `before_request` gate (not per-route decorators) — avoids coverage gaps across 44+ blueprints
2. `--workers 1` enforced and documented — single constraint that prevents all multi-worker SSE state fragmentation
3. ExecutionService split deferred — extract stateless helpers (PromptRenderer, CommandBuilder) first, stateful components only after state is DB-persisted
4. Migration decomposition — separate `seeds.py` from schema changelog before next migration is added

**Scaling path (documented, not immediate):** Single-worker gevent (current target) → Redis pub/sub for SSE fan-out (enables `--workers > 1`) → PostgreSQL via SQLAlchemy Core (enables multi-machine).

### Critical Pitfalls

**Pitfall 1: Auth middleware misses webhook receiver**
The `POST /` webhook endpoint and `/api/webhooks/github/` (HMAC-authenticated) must be on the explicit bypass list. Per-blueprint auth decorators have coverage gaps with 44+ blueprints. Use `app.before_request` with path-prefix allowlist only. Verify with an integration test that enumerates all routes from the OpenAPI spec.

**Pitfall 2: EventSource cannot send auth headers**
Browser `EventSource` does not support custom headers. All SSE endpoints (`/admin/executions/{id}/stream`, `/admin/super-agents/{id}/sessions/{id}/stream`, etc.) will return 401 silently after auth is added. Solution: short-lived signed query-string tokens for SSE endpoints (generate server-side, expire in 60s) or cookie-based auth. Do not attempt per-route polling fallback.

**Pitfall 3: Gunicorn default workers × in-memory SSE state**
Gunicorn defaults to `(2 * cpu_count) + 1` workers. With the current `ExecutionLogService._subscribers` and `ProcessManager._processes` stored as class-level dicts, each worker has isolated state. SSE subscribers see no events from executions running in other workers. Enforce `workers=1` in `gunicorn.conf.py` with a prominent comment. Add an assertion in startup to prevent misconfiguration.

**Pitfall 4: Gevent monkey patching breaks APScheduler**
`gevent.monkey.patch_all()` replaces `threading.Thread` with greenlets. APScheduler uses threading internally and may deadlock, double-fire, or silently skip jobs. Use `monkey.patch_all(thread=False)` if APScheduler compatibility is required, or use `gthread` workers as an alternative to gevent. Test scheduled trigger firing rates before deploying gevent workers.

**Pitfall 5: migrations.py partial failure leaves schema in unknown state**
SQLite `ALTER TABLE` may commit before the migration runner raises an exception, leaving schema ahead of the version counter. Back up `agented.db` before every migration run. Add `--dry-run` mode. Consider wrapping each migration in its own savepoint.

---

## Research Landscape Summary

LANDSCAPE.md was initialized as a stub with no survey content — this milestone is a production hardening effort for an existing platform, not a domain research project. The relevant "landscape" is established operational patterns for Flask + Vue.js production deployments.

**Established patterns (HIGH confidence):**
- Flask `before_request` auth middleware with allowlists — industry standard for API-first Flask apps
- Gunicorn + gevent workers for SSE + concurrent connections — documented in Flask and Gunicorn official guides
- Redis pub/sub for multi-process SSE fan-out — used by Flask-SSE library and multiple production Flask apps
- `@microsoft/fetch-event-source` for authenticated SSE from browser — the standard workaround for `EventSource` header limitation
- Caddy for zero-config TLS + reverse proxy on single-node deployments — growing adoption in 2025

**No competing approaches to evaluate** — this is a hardening milestone with well-documented correct patterns, not an experimental feature requiring method comparison. The only genuine trade-off is gevent vs. gthread workers (both valid; gevent preferred for green-thread concurrency, gthread safer for APScheduler compatibility).

---

## Implications for Roadmap

### Phase 1: Environment and WSGI Foundation
**Rationale:** Before any auth work, the server must be running on a production WSGI server with persistent configuration. The SECRET_KEY regeneration bug and Flask dev server are prerequisites to fix first — they block everything else and have near-zero implementation risk.
**Delivers:** Stable SECRET_KEY, `.env` file loading, Gunicorn + gevent config, `gunicorn.conf.py`, updated `just deploy` target, `.env.example` documentation.
**Type:** implement
**Features from FEATURES.md:** Stable SECRET_KEY, Production WSGI configuration, `.env.example`
**Pitfalls to avoid:** Gunicorn sync worker SSE timeout (Pitfall 3); multi-worker SSE state split (Pitfall 5) — enforce `workers=1` explicitly in the config file.

### Phase 2: API Authentication
**Rationale:** Auth is the most impactful security addition. It must be implemented after WSGI is stable and must address the SSE header limitation (EventSource) in the same phase — they are entangled. Auth without fixing SSE endpoints renders the execution log viewer broken.
**Delivers:** `backend/app/auth/middleware.py`, API key auth via `app.before_request`, bypass allowlist, frontend `apiFetch` header injection, SSE endpoint authentication via short-lived query-string tokens or `@microsoft/fetch-event-source`.
**Type:** implement
**Features from FEATURES.md:** API authentication (shared API key), CORS lockdown, Health endpoint hardening
**Pitfalls to avoid:** Auth misses webhook receiver (Pitfall 1); EventSource cannot send headers (Pitfall 2); `isolated_db` fixture breaks with auth middleware (Pitfall 6).
**Research flag:** Implementation details for SSE auth pattern (query-string tokens vs. cookies vs. fetch-event-source) benefit from a focused technical spike before writing code.

### Phase 3: Security Hardening
**Rationale:** After auth is in place, layering security headers and rate limiting is low-effort and high-value. These are one-decorator additions that require auth to be present first (rate limits on unauthenticated endpoints are meaningless).
**Delivers:** `flask-talisman` CSP/HSTS/X-Frame headers, `flask-limiter` rate limiting on webhook ingestion and admin routes, CORS explicit allowlist enforcement.
**Type:** implement
**Features from FEATURES.md:** CORS lockdown (enforcement), Security headers, Rate limiting
**Pitfalls to avoid:** None specific to this phase — low risk.

### Phase 4: Observability and Process Reliability
**Rationale:** Once the platform is secured, operational visibility (error tracking) and process reliability (restart-on-crash, structured logging) are the final production table stakes. These enable debugging production issues and ensure the service recovers from failures.
**Delivers:** Sentry SDK integration, structured JSON logging with request IDs, systemd unit file (or Docker Compose with `restart: unless-stopped`), DB-backed webhook deduplication replacing in-memory dict.
**Type:** implement
**Features from FEATURES.md:** Process supervisor, Structured logging with request IDs, DB-backed webhook deduplication, Error monitoring (Sentry)
**Pitfalls to avoid:** DB-backed dedup must go through `get_connection()` dynamically (not module-level constant) to work with `isolated_db` test fixture.

### Phase 5: Code Quality and Maintainability
**Rationale:** After the platform is production-safe, incremental code quality improvements reduce future maintenance cost without blocking users. The ExecutionService split has regression risk and must wait until integration tests cover `run_trigger` end-to-end.
**Delivers:** `ruff` in CI, migration file decomposition (`seeds.py` extracted from `migrations.py`), ExecutionService split (coordinator / renderer / runner / rate-limit-detector) with facade preserved, App.vue decomposition in frontend.
**Type:** implement
**Features from FEATURES.md:** N/A (internal quality, no user-visible change)
**Pitfalls to avoid:** ExecutionService refactor breaks in-flight state (Pitfall 9) — extract stateless helpers first, stateful components only after state is DB-persisted; do all refactoring during zero-execution maintenance windows.

### Phase Ordering Rationale

- Phase 1 must precede Phase 2: auth middleware in a production WSGI server requires the server to be configured first; SECRET_KEY stability is a prerequisite for any token-based auth
- Phase 2 must precede Phase 3: rate limiting on unauthenticated routes is security theater; auth gate is the meaningful enforcement layer
- Phases 3 and 4 are largely independent and could run concurrently if resources allow
- Phase 5 has no production-safety dependencies and can be interleaved with other phases, but the ExecutionService split specifically requires existing integration test coverage

### Research Flags

- **Phase 2 (Auth):** SSE authentication pattern warrants a technical spike. Three valid approaches (short-lived query-string tokens, cookie auth, `@microsoft/fetch-event-source`) have different security properties and frontend implementation costs. Choose before writing auth middleware.
- **Phase 5 (ExecutionService split):** Requires integration test baseline for `run_trigger` before any splitting begins. Assess test coverage before planning the phase in detail.
- **All phases:** Standard patterns apply throughout — no research-heavy methodology questions. The pitfalls are concrete and preventable with the documented approaches.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified via PyPI, official docs, Context7. Compatibility matrix provided with specific version pins. |
| Features | HIGH (table stakes) / MEDIUM (differentiators) | Table stakes derived directly from codebase gaps — very high confidence. Differentiator features based on industry survey of agent platform patterns. |
| Architecture | HIGH | Based on direct codebase inspection of `execution_service.py`, `migrations.py`, `__init__.py`, `connection.py`. Patterns verified against official Flask, Gunicorn, and Flask-SSE documentation. |
| Pitfalls | HIGH (codebase-verified) | All 10 pitfalls verified against actual source files with specific line references. Prevention strategies verified against external sources. |
| Research Landscape | N/A | LANDSCAPE.md is a stub — this is a hardening milestone with established correct patterns, not an exploratory research domain. No method comparison is needed. |

**Gaps to address during planning:**
- SSE auth pattern selection (query-string tokens vs. cookies vs. fetch-event-source) — needs a technical decision before Phase 2 planning
- APScheduler + gevent compatibility testing — should be validated in a spike before committing to gevent workers in Phase 1
- ExecutionService integration test coverage baseline — must be assessed before Phase 5 can be scoped
- Deployment target (systemd vs. Docker) — the PTY service uses `os.fork()` which has Docker UID mapping implications; confirm deployment environment before Phase 4

---

## Sources

### Primary (HIGH confidence)
- Flask `before_request` middleware — Flask official docs
- Flask-JWT-Extended v4.7.1 — readthedocs.io (verified); Context7 `/vimalloc/flask-jwt-extended`
- Gunicorn + gevent + SSE — Flask deploying guide; Gunicorn official docs; GitHub issues #1801, #677, #1186
- flask-talisman v1.1.0 — wntrblm fork GitHub (Nov 2025)
- flask-limiter v4.1.1 — readthedocs.io
- sentry-sdk v2.52.0 — PyPI (verified Jan 2026)
- python-dotenv v1.2.1 — GitHub releases (Oct 2025)
- SQLAlchemy v2.0.46 + Alembic v1.18.4 — sqlalchemy.org (confirmed Jan 2026)
- ruff v0.15.2 — PyPI
- SQLite WAL mode — sqlite.org official documentation
- EventSource header limitation — Browser Web API specification; `@microsoft/fetch-event-source` README
- Codebase direct inspection — `execution_service.py`, `execution_log_service.py`, `migrations.py`, `__init__.py`, `connection.py`, `conftest.py`

### Secondary (MEDIUM confidence)
- Caddy vs. Nginx 2025 — onidel.com
- Flask production hardening checklist (Apr 2025) — medium.com/@vicfcs
- SQLite in 2025 — nihardaily.com
- AI observability table stakes — softwareseni.com, vellum.ai
- Sharing data across Gunicorn workers — Medium (@jgleeee)
- gevent + APScheduler compatibility — gunicorn issue #1056
- Python tooling in 2025 (ruff adoption) — osquant.com
- Flask systemd service — blog.miguelgrinberg.com
- WAL production guidance — victoria.dev
- Flask RBAC + JWT patterns — Logto docs

---
*Research completed: 2026-02-25*
*Ready for roadmap: yes*
