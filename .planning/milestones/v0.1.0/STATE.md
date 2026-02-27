# Project State — v0.1.0 — Production Hardening Milestone

**Project:** Agented — Agentic Development Platform
**Milestone:** v0.1.0 — Production Hardening
**Last Updated:** 2026-02-27T19:30:00Z

---

## Project Reference

**Core Value:** Enable engineering teams to orchestrate AI-powered automation through a unified dashboard — without requiring infrastructure expertise.

**Milestone Goal:** Harden the existing feature-complete platform for safe internal deployment: stable configuration, production WSGI runtime, API authentication, security headers, observability, and code quality.

**Current Focus:** Phase 4 Plan 01 complete. Next: Phase 4 Plan 02 — Per-Blueprint Rate Limits.

---

## Current Position

**Active Phase:** Phase 4 — Security Hardening
**Active Plan:** 04-01 complete, 04-02 next
**Status:** Phase 3 merged, Phase 4 Plan 01 complete

**Progress:**
```
[==========] Phase 1: Web UI Roadmapping Feature (ALL 5 plans complete)
[==========] Phase 2: Environment and WSGI Foundation (COMPLETE — 2026-02-28)
[==========] Phase 3: API Authentication (merged — 2026-02-28)
[=====     ] Phase 4: Security Hardening (Plan 01 complete)
[          ] Phase 5: Observability and Process Reliability
[          ] Phase 6: Code Quality and Maintainability
```

Overall: 3/6 phases complete, Phase 4 in progress

---

## Performance Metrics

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Backend test pass rate | 100% | 911/911 (100%) | Passing |
| Frontend build (vue-tsc) | 0 errors | 0 errors | Passing |
| Frontend test pass rate | 100% | 344/344 (100%) | Passing |
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
| Reused renderMarkdown + useAutoScroll for session panel | Existing composables provide markdown rendering with highlight.js and smart auto-scroll; no need for streaming-markdown for initial implementation | Phase 1 Plan 03 |
| Session-completion sync runs before SSE broadcast | Prevents TOCTOU race where frontend refreshes before DB is updated; sync is synchronous and guarded by grd_init_status | Phase 1 Plan 04 |
| Auto-init uses polling (not callback) for PTY completion | PTY sessions have no callback mechanism; 2s poll with 10min timeout is simple and reliable | Phase 1 Plan 04 |
| Clone-wait uses background thread with DB polling | clone_async has no completion callback; background thread polls clone_status every 2s (4min timeout) | Phase 1 Plan 04 |
| GrdSettings uses settingsApi key-value store with grd.* prefix | Simpler than dedicated endpoint; leverages existing settings infrastructure | Phase 1 Plan 05 |
| Planning button placed left of Management per CONTEXT.md | Consistent with user journey: plan first, then manage | Phase 1 Plan 05 |
| Init status polling at 5s interval with watch lifecycle | Balances responsiveness with server load; auto-cleans on unmount | Phase 1 Plan 05 |
| Short-lived query-string tokens for SSE auth (recommended) | Three valid approaches exist; query-string tokens are simplest with no new frontend dependency; final selection at Phase 2 planning | Phase 2 |
| Accept default monkey.patch_all() from GeventWorker | Custom thread=False adds complexity; validate APScheduler compatibility in integration testing if issues arise | Phase 2 Plan 01 |
| .secret_key file in backend/ directory | Locality with run.py and app factory; .gitignore prevents committing | Phase 2 Plan 01 |
| Added 3 extra env vars to .env.example | CODEX_HOME, GEMINI_CLI_HOME, OPENCODE_HOME found in codebase audit; included for completeness | Phase 2 Plan 02 |
| RestartSec=3 in systemd unit | Within the 5-second restart constraint; matches research recommendation | Phase 2 Plan 02 |
| In-memory limiter storage (memory://) | Safe for workers=1 Gunicorn deployment; avoids Redis dependency for single-process architecture | Phase 4 Plan 01 |
| CSP allows 'unsafe-inline' for script-src/style-src | Required for Swagger UI at /docs; without it, docs page renders blank | Phase 4 Plan 01 |
| HSTS only over HTTPS (flask-talisman default) | Per RFC 6797; header sent when X-Forwarded-Proto: https detected from reverse proxy | Phase 4 Plan 01 |

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

**Next action:** Execute Phase 4 Plan 02 — Per-Blueprint Rate Limits.

**To resume:** Read ROADMAP.md and this STATE.md. Phase 4 Plan 01 complete — summary in `phases/04-security-hardening/04-01-SUMMARY.md`.

---
*Initialized: 2026-02-25*
