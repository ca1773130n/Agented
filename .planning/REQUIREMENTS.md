# Requirements

**Project:** Agented — Production Hardening Milestone
**Created:** 2026-02-25
**Source:** Research synthesis (auto mode)

---

## v1 Requirements

### Environment & Configuration (ENV)

- [ ] **ENV-01**: Server uses a stable SECRET_KEY from environment variable or persisted file, never auto-regenerated on restart
- [ ] **ENV-02**: All environment variables documented in `.env.example` with types, defaults, and descriptions
- [ ] **ENV-03**: Application loads configuration from `.env` file via python-dotenv on startup

### WSGI & Deployment (DEP)

- [ ] **DEP-01**: Backend runs on Gunicorn with gevent worker class (`workers=1`, `worker_class=gevent`) instead of Flask dev server
- [ ] **DEP-02**: `gunicorn.conf.py` configuration file with documented settings and `workers=1` constraint with rationale
- [ ] **DEP-03**: `just deploy` target updated to use Gunicorn instead of `python run.py &`
- [ ] **DEP-04**: Process supervisor configuration (systemd unit file) for automatic restart-on-crash

### Authentication (AUTH)

- [ ] **AUTH-01**: All `/admin/*` and `/api/*` routes require API key authentication via `app.before_request` middleware
- [ ] **AUTH-02**: Explicit bypass allowlist for unauthenticated routes: webhook receiver (`/`), GitHub webhook (`/api/webhooks/github/`), health (`/health/*`), docs (`/docs/*`, `/openapi/*`)
- [ ] **AUTH-03**: Frontend `apiFetch()` includes `X-API-Key` header on every request
- [ ] **AUTH-04**: SSE endpoints authenticated via short-lived query-string tokens or `@microsoft/fetch-event-source` replacing native `EventSource`
- [ ] **AUTH-05**: CORS lockdown — explicit `CORS_ALLOWED_ORIGINS` required; fail-closed (reject all cross-origin if unset)

### Security Hardening (SEC)

- [ ] **SEC-01**: Security headers via flask-talisman (CSP, HSTS, X-Frame-Options, X-Content-Type-Options)
- [ ] **SEC-02**: Rate limiting on webhook ingestion and admin routes via flask-limiter
- [ ] **SEC-03**: Health endpoint strips sensitive fields (execution IDs, process details, startup warnings) from unauthenticated responses

### Observability (OBS)

- [ ] **OBS-01**: Structured JSON logging with request ID correlation on every log line
- [ ] **OBS-02**: Sentry SDK integration for error tracking and performance monitoring
- [ ] **OBS-03**: DB-backed webhook deduplication replacing in-memory dict (persisted keys with TTL in SQLite)

### Code Quality (QUAL)

- [ ] **QUAL-01**: Migration seeds extracted from `migrations.py` into separate `seeds.py` file
- [ ] **QUAL-02**: Ruff configured in `pyproject.toml` as linter + formatter (replacing Black)
- [ ] **QUAL-03**: ExecutionService split into coordinator + stateless helpers (PromptRenderer, CommandBuilder)

---

## v2 Requirements (Deferred)

- [ ] **FEAT-01**: Prompt injection guardrails — truncation and sanitization of externally-sourced prompt content
- [ ] **FEAT-02**: CLI tools health check on dashboard — surface claude/opencode/gemini/codex binary status
- [ ] **FEAT-03**: Execution replay / retry UI — re-run stored trigger params from execution history
- [ ] **FEAT-04**: Webhook payload inspector — UI showing recent raw inbound payloads with field path highlighting

---

## Out of Scope

- **Multi-tenant user accounts + RBAC** — platform is single-org internal tooling; shared API key is sufficient
- **PostgreSQL migration** — raw SQL with no ORM makes this a full rewrite; SQLite WAL mode is adequate at current scale
- **Redis pub/sub for SSE** — only needed for `workers > 1`; single-worker gevent sidesteps this
- **Horizontal scaling / Kubernetes** — in-memory state prevents this; single-machine deployment is the target
- **CI/CD pipeline for Agented itself** — address after auth and deployment hardening
- **Plugin marketplace** — existing plugin CRUD is sufficient
- **Real-time collaborative editing** — last-write-wins is adequate for team-internal tool
- **OpenTelemetry trace export** — defer until structured logging is established

---

## Traceability

<!-- Updated by roadmapper -->

| REQ-ID | Phase | Status |
|--------|-------|--------|
| ENV-01 | - | Pending |
| ENV-02 | - | Pending |
| ENV-03 | - | Pending |
| DEP-01 | - | Pending |
| DEP-02 | - | Pending |
| DEP-03 | - | Pending |
| DEP-04 | - | Pending |
| AUTH-01 | - | Pending |
| AUTH-02 | - | Pending |
| AUTH-03 | - | Pending |
| AUTH-04 | - | Pending |
| AUTH-05 | - | Pending |
| SEC-01 | - | Pending |
| SEC-02 | - | Pending |
| SEC-03 | - | Pending |
| OBS-01 | - | Pending |
| OBS-02 | - | Pending |
| OBS-03 | - | Pending |
| QUAL-01 | - | Pending |
| QUAL-02 | - | Pending |
| QUAL-03 | - | Pending |

---
*Created: 2026-02-25 (auto mode — all table stakes included)*
