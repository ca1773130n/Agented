# Roadmap — v0.1.0 — Production Hardening Milestone

**Project:** Agented — Agentic Development Platform
**Milestone:** v0.1.0 — Production Hardening
**Created:** 2026-02-25
**Total v1 Requirements:** 21
**Phases:** 6
**Coverage:** 21/21

---

## Overview

Agented is feature-complete but not production-safe. This milestone starts by building the Web UI roadmapping feature to enable GRD project planning from the browser, then hardens the platform for internal deployment by addressing configuration, authentication, security, observability, and code quality in dependency order.

---

## Phase Structure

### Phase 1: Web UI Roadmapping Feature

**Goal:** Build full GRD project planning functionality into the web UI frontend — enabling users to create roadmaps, milestones, requirements, and phases through AI-assisted interaction in the browser, without requiring the CLI.

**Dependencies:** None (starting phase)

**Requirements:** (New feature — no existing REQ-IDs; requirements to be defined during phase planning)

**Success Criteria:**
1. User can initiate a new project roadmap from the web UI with AI-assisted questioning
2. User can create, view, and manage milestones and phases through the UI
3. User can define and edit requirements with traceability to phases
4. Roadmap visualization displays phase structure, dependencies, and progress
5. Research initiation (stack, features, architecture, pitfalls) can be triggered from the UI

**Verification Level:** proxy

---

### Phase 2: Environment and WSGI Foundation

**Goal:** The server runs on Gunicorn with gevent workers, loads all configuration from `.env`, and has a stable `SECRET_KEY` — making the system safe to configure and restart without breaking state.

**Dependencies:** Phase 1 (independent — can begin immediately after Phase 1 or in parallel)

**Requirements:** ENV-01, ENV-02, ENV-03, DEP-01, DEP-02, DEP-03, DEP-04

**Success Criteria:**
1. Server starts via `just deploy` using Gunicorn (not Flask dev server); `ps aux` shows `gunicorn` worker process, never `python run.py`
2. `SECRET_KEY` loaded from environment variable or persisted file; restarting the server with the same `.env` produces an identical key (verified by inspecting Flask app config before and after restart)
3. `.env.example` documents all environment variables with types, defaults, and descriptions; a fresh clone with only `.env.example` as a template reaches a runnable state
4. `gunicorn.conf.py` enforces `workers=1` and `worker_class=gevent`; the comment in the file explains the single-worker constraint in terms of in-memory SSE state
5. Systemd unit file (or equivalent process supervisor config) restarts the backend within 5 seconds of a crash (`kill -9 $(pgrep gunicorn)` followed by `ps aux` shows gunicorn restarted)

**Verification Level:** sanity

---

### Phase 3: API Authentication

**Goal:** Every admin and API route requires a valid API key; SSE streaming endpoints authenticate without requiring custom headers; CORS rejects all cross-origin requests unless the origin is explicitly listed.

**Dependencies:** Phase 2 (stable SECRET_KEY required for token signing; Gunicorn must be running before auth middleware is tested against real concurrent requests)

**Requirements:** AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05

**Success Criteria:**
1. `curl http://localhost:20000/admin/triggers` without an `X-API-Key` header returns HTTP 401; the same request with a valid key returns HTTP 200
2. The webhook receiver (`POST /`) and GitHub webhook (`/api/webhooks/github/`) respond to unauthenticated requests without returning 401 (bypass allowlist is correct)
3. The execution log SSE stream (`/admin/executions/{id}/stream`) delivers events to a browser tab after auth — confirmed by opening the execution detail page and watching live log lines appear during a test run
4. `curl -H "Origin: https://evil.example.com" http://localhost:20000/admin/triggers` returns no `Access-Control-Allow-Origin` header (CORS fail-closed when origin is not in allowlist)
5. Frontend `apiFetch()` includes `X-API-Key` on every request; no network request in browser DevTools shows a missing auth header for any admin or API call

**Verification Level:** proxy

---

### Phase 4: Security Hardening

**Goal:** All HTTP responses include security headers; webhook and admin routes are rate-limited; CORS enforcement is explicit and fail-closed.

**Dependencies:** Phase 3 (rate limiting on unauthenticated routes is security theater — the auth gate must exist first for rate limits to be meaningful)

**Requirements:** SEC-01, SEC-02, SEC-03

**Success Criteria:**
1. `curl -I http://localhost:20000/admin/triggers` (with valid API key) response includes `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options: DENY`, and `X-Content-Type-Options: nosniff` headers
2. Sending 20 requests to `POST /` (webhook endpoint) within 10 seconds from the same IP causes the 21st request to return HTTP 429
3. `GET /health/readiness` without an API key returns a response that contains no execution IDs, process PIDs, or startup warning strings (only `status: ok` and a timestamp)

**Verification Level:** proxy

---

### Phase 5: Observability and Process Reliability

**Goal:** Every log line carries a request ID; errors in production are captured in Sentry; webhook deduplication survives server restarts; the process supervisor is tested end-to-end.

**Dependencies:** Phase 3 (structured logging with request IDs requires auth middleware to inject the request ID into context; auth must be in place before Sentry captures meaningful request context)

**Requirements:** OBS-01, OBS-02, OBS-03

**Success Criteria:**
1. Every application log line emitted during an API request includes a `request_id` field with a consistent value across all log lines for that request (verified by grepping the log file for a specific request's UUID)
2. Deliberately triggering an unhandled exception (e.g., calling a nonexistent route that raises) results in the error appearing in the Sentry dashboard within 60 seconds
3. Sending the same webhook payload twice within 10 seconds, then restarting the server, and sending the payload a third time — the third delivery is deduplicated (DB-backed, survives restart); without the restart, all three are deduplicated

**Verification Level:** proxy

---

### Phase 6: Code Quality and Maintainability

**Goal:** Migration seeding is separated from schema history; Ruff replaces Black as the linter/formatter; ExecutionService is split into coordinator plus stateless helpers with the public interface preserved.

**Dependencies:** Phase 5 (ExecutionService split requires integration test coverage of `run_trigger` to be safe; OBS phase adds structured logging that makes the split easier to trace; no production-safety dep, but logical after the platform is hardened)

**Requirements:** QUAL-01, QUAL-02, QUAL-03

**Success Criteria:**
1. `backend/app/db/seeds.py` exists and contains all seeding functions extracted from `migrations.py`; `migrations.py` contains only schema migration entries; `cd backend && uv run python -c "from app.db.seeds import seed_predefined_triggers"` executes without error
2. `cd backend && uv run ruff check .` exits with code 0; `cd backend && uv run ruff format --check .` exits with code 0; `pyproject.toml` defines Ruff config replacing any Black config
3. `PromptRenderer` and `CommandBuilder` classes exist as separate modules; `ExecutionService` facade imports and delegates to them; `cd backend && uv run pytest` passes at 100% with no changes to test call sites

**Verification Level:** proxy

---

## Progress

| Phase | Goal | Requirements | Verification | Status |
|-------|------|--------------|--------------|--------|
| 1 - Web UI Roadmapping Feature | GRD planning in browser | (TBD at planning) | proxy | Pending |
| 2 - Environment and WSGI Foundation | Stable config + Gunicorn runtime | ENV-01, ENV-02, ENV-03, DEP-01, DEP-02, DEP-03, DEP-04 | sanity | Pending |
| 3 - API Authentication | Auth gate + SSE auth + CORS lockdown | AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05 | proxy | Pending |
| 4 - Security Hardening | Security headers + rate limiting | SEC-01, SEC-02, SEC-03 | proxy | Pending |
| 5 - Observability and Process Reliability | Structured logging + Sentry + DB dedup | OBS-01, OBS-02, OBS-03 | proxy | Pending |
| 6 - Code Quality and Maintainability | Ruff + seeds.py + ExecutionService split | QUAL-01, QUAL-02, QUAL-03 | proxy | Pending |

---

## Dependency Graph

```
Phase 1 (Web UI Roadmapping)
Phase 2 (ENV+DEP)
    └── Phase 3 (AUTH)
            └── Phase 4 (SEC)
            └── Phase 5 (OBS)
                    └── Phase 6 (QUAL)
```

Phase 1 is independent — no dependencies on hardening phases. Phases 4 and 5 are independent of each other after Phase 3 and can run concurrently if needed.

---

## Coverage Map

| REQ-ID | Phase |
|--------|-------|
| ENV-01 | Phase 2 |
| ENV-02 | Phase 2 |
| ENV-03 | Phase 2 |
| DEP-01 | Phase 2 |
| DEP-02 | Phase 2 |
| DEP-03 | Phase 2 |
| DEP-04 | Phase 2 |
| AUTH-01 | Phase 3 |
| AUTH-02 | Phase 3 |
| AUTH-03 | Phase 3 |
| AUTH-04 | Phase 3 |
| AUTH-05 | Phase 3 |
| SEC-01 | Phase 4 |
| SEC-02 | Phase 4 |
| SEC-03 | Phase 4 |
| OBS-01 | Phase 5 |
| OBS-02 | Phase 5 |
| OBS-03 | Phase 5 |
| QUAL-01 | Phase 6 |
| QUAL-02 | Phase 6 |
| QUAL-03 | Phase 6 |

Mapped: 21/21. No orphaned requirements.

---

## Key Constraints (From Research)

- `workers=1` is mandatory in `gunicorn.conf.py` until Redis pub/sub replaces in-memory SSE state
- AUTH-04 (SSE auth) must be implemented in the same phase as AUTH-01 (API key middleware) — they are entangled; adding auth without fixing SSE breaks the execution log viewer silently
- QUAL-03 (ExecutionService split) requires integration test coverage of `run_trigger` before splitting begins — assess coverage at Phase 6 planning time
- Gevent monkey patching: use `monkey.patch_all(thread=False)` or validate APScheduler job firing rates before deploying gevent workers

---
*Created: 2026-02-25*
*Reordered: 2026-02-26 — Web UI Roadmapping moved to Phase 1*
