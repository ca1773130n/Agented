# Project State — v0.1.0 — Production Hardening Milestone

**Project:** Agented — Agentic Development Platform
**Milestone:** v0.1.0 — Production Hardening
**Last Updated:** 2026-02-25

---

## Project Reference

**Core Value:** Enable engineering teams to orchestrate AI-powered automation through a unified dashboard — without requiring infrastructure expertise.

**Milestone Goal:** Harden the existing feature-complete platform for safe internal deployment: stable configuration, production WSGI runtime, API authentication, security headers, observability, and code quality.

**Current Focus:** Not started — roadmap created, awaiting phase planning.

---

## Current Position

**Active Phase:** None (pre-execution)
**Active Plan:** None
**Status:** Roadmap complete, ready for Phase 1 planning

**Progress:**
```
[          ] Phase 1: Web UI Roadmapping Feature
[          ] Phase 2: Environment and WSGI Foundation
[          ] Phase 3: API Authentication
[          ] Phase 4: Security Hardening
[          ] Phase 5: Observability and Process Reliability
[          ] Phase 6: Code Quality and Maintainability
```

Overall: 0/6 phases complete (0%)

---

## Performance Metrics

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Backend test pass rate | 100% | Unknown | Not measured |
| Frontend build (vue-tsc) | 0 errors | Unknown | Not measured |
| Frontend test pass rate | 100% | Unknown | Not measured |
| API response time (p95) | <200ms | Unknown | Not measured |
| SSE latency | <500ms | Unknown | Not measured |

---

## Deferred Validations

None — this milestone uses proxy verification throughout. No deferred (Level 3) validations requiring an Integration Phase.

---

## Accumulated Context

### Decisions Made

| Decision | Rationale | Phase |
|----------|-----------|-------|
| Merge ENV + DEP into Phase 1 | Config stability and WSGI runtime are prerequisites that must both be in place before auth can be implemented or tested | Phase 1 |
| AUTH-04 (SSE auth) in same phase as AUTH-01 | Browser EventSource cannot send custom headers; adding auth middleware without fixing SSE breaks execution log viewer silently | Phase 2 |
| Phases 3 and 4 independent after Phase 2 | SEC (flask-talisman, flask-limiter) and OBS (Sentry, structured logging) have no dependency on each other | Phases 3-4 |
| QUAL-03 after Phase 4 | ExecutionService split has regression risk; requires integration test coverage of run_trigger before splitting; structured logging from Phase 4 makes tracing easier | Phase 5 |
| workers=1 enforced in gunicorn.conf.py | In-memory SSE state (_subscribers, _log_buffers, _processes) is class-level; multiple workers produce split state and silent SSE failures | Phase 1 |
| Short-lived query-string tokens for SSE auth (recommended) | Three valid approaches exist; query-string tokens are simplest with no new frontend dependency; final selection at Phase 2 planning | Phase 2 |

### Critical Pitfalls (From Research)

1. **Auth misses webhook receiver** — `POST /` and `/api/webhooks/github/` must be on explicit bypass allowlist; use `app.before_request` not per-route decorators across 44+ blueprints
2. **EventSource cannot send auth headers** — SSE endpoints return 401 silently after auth unless fixed with query-string tokens, cookies, or `@microsoft/fetch-event-source`
3. **Gunicorn default workers × in-memory state** — default `(2 * cpu_count) + 1` workers will silently fragment SSE state; enforce `workers=1` with startup assertion
4. **Gevent monkey patching breaks APScheduler** — use `monkey.patch_all(thread=False)` or validate APScheduler job firing rates before deploying gevent

### Open Questions

- SSE auth pattern final selection: short-lived query-string tokens vs. cookie auth vs. `@microsoft/fetch-event-source` — decide at Phase 2 planning
- Deployment target: systemd unit file vs. Docker Compose — PTY service uses `os.fork()` which has Docker UID mapping implications; confirm before Phase 4
- Gevent + APScheduler compatibility: validate in Phase 1 spike before committing to gevent workers

### Roadmap Evolution

- Phase 6 added: Web UI Roadmapping Feature — full GRD project planning functionality in web UI frontend
- Phases reordered: Web UI Roadmapping moved to Phase 1; previous Phases 1-5 shifted to 2-6

### Todos

- [ ] Run baseline metrics (pytest, vue-tsc, test:run) before Phase 1 starts to establish starting state
- [ ] Confirm deployment environment (systemd vs. Docker) before Phase 4 planning

---

## Session Continuity

**Next action:** Plan Phase 1 (Web UI Roadmapping Feature) via `/grd:plan-phase 1`

**To resume:** Read ROADMAP.md and this STATE.md, then proceed to Phase 1 planning.

---
*Initialized: 2026-02-25*
