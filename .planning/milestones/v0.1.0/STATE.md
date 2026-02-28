# Project State — v0.1.0 — Production Hardening Milestone

**Project:** Agented — Agentic Development Platform
**Milestone:** v0.1.0 — Production Hardening
**Last Updated:** 2026-02-28T03:08:00Z

---

## Project Reference

**Core Value:** Enable engineering teams to orchestrate AI-powered automation through a unified dashboard — without requiring infrastructure expertise.

**Milestone Goal:** Harden the existing feature-complete platform for safe internal deployment: stable configuration, production WSGI runtime, API authentication, security headers, observability, and code quality.

**Current Focus:** All 6 phases complete. Milestone v0.1.0 done.

---

## Current Position

**Active Phase:** COMPLETE
**Active Plan:** None
**Status:** All phases complete. Milestone v0.1.0 done.

**Progress:**
```
[==========] Phase 1: Web UI Roadmapping Feature (ALL 5 plans complete)
[==========] Phase 2: Environment and WSGI Foundation (COMPLETE — 2026-02-28)
[==========] Phase 3: API Authentication (merged — 2026-02-28)
[==========] Phase 4: Security Hardening (COMPLETE — 2026-02-28)
[==========] Phase 5: Observability and Process Reliability (COMPLETE — 2026-02-28)
[==========] Phase 6: Code Quality and Maintainability (COMPLETE — 2026-02-28)
```

Overall: 6/6 phases complete

---

## Performance Metrics

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Backend test pass rate | 100% | 906/906 (100%) | Passing |
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
| Rate limits applied before blueprint registration | Flask-limiter official pattern; post-registration limits may silently fail | Phase 4 Plan 02 |
| Admin rate limit at 120/minute | Accommodates SPA loads, AJAX, and SSE reconnects; tighter limits break frontend | Phase 4 Plan 02 |
| Health readiness uses self-contained auth check | Independent of Phase 3 middleware chain; same AGENTED_API_KEY env var | Phase 4 Plan 02 |
| Unauthenticated readiness returns fixed "ok" | Prevents information leakage about degraded components to external probers | Phase 4 Plan 02 |
| RequestIdFilter on handler, not root logger | Python logging filters on loggers skip propagated child events; handler-level filters capture all records | Phase 5 Plan 01 |
| Gunicorn accesslog=None | Request lifecycle now logged by middleware in JSON format; prevents garbled mixed-format output | Phase 5 Plan 01 |
| request_id_var cleared in teardown_request | Defense-in-depth against greenlet context leakage even though contextvars should be per-greenlet | Phase 5 Plan 01 |
| Migration v47 instead of v55 for webhook_dedup_keys | Last migration was v46; sequential ordering maintained | Phase 5 Plan 03 |
| DB-backed dedup added as new functionality (no in-memory dict to replace) | In-memory _webhook_dedup dict did not exist in codebase; implemented DB-only dedup from scratch | Phase 5 Plan 03 |
| Sentry init at module level in run.py (not in create_app or post_fork) | With preload_app=False, run.py loads fresh per worker after monkey patching; module-level init is correct per Sentry docs | Phase 5 Plan 02 |
| SSE transaction filter matches /stream and /sessions/ | Long-lived SSE connections create multi-minute Sentry transactions that distort metrics and waste quota | Phase 5 Plan 02 |
| send_default_pii=False for Sentry | Privacy-first default; no user IPs or cookies sent to third-party error tracker | Phase 5 Plan 02 |
| seeds.py imports from .triggers (canonical source) | Avoids duplicating PREDEFINED_TRIGGERS; imports from triggers.py where they are canonically defined | Phase 6 Plan 01 |
| migrations.py constants left in place | Migration functions reference them directly; cross-module imports would violate migration isolation | Phase 6 Plan 01 |
| Removed Black entirely (no fallback) | Ruff formatter is Black-compatible for 99.9% of cases; keeping both tools would be redundant | Phase 6 Plan 02 |
| per-file-ignores for __init__.py (F401/F403) | Barrel files use wildcard imports and re-exports by design; suppressing prevents false positives | Phase 6 Plan 02 |
| fixable = ["ALL"] in ruff.lint | Enables auto-fix for all fixable categories including import sorting | Phase 6 Plan 02 |
| Facade pattern on build_command | Tests mock ExecutionService.build_command; keeping the method as thin delegate preserves all mock paths without test modifications | Phase 6 Plan 03 |
| warn_unresolved as new functionality | _KNOWN_PLACEHOLDERS did not exist in current codebase; implemented as correctness enhancement | Phase 6 Plan 03 |
| Security audit threat report stays in run_trigger | Side effects (file I/O via save_threat_report) cannot be extracted to stateless helper | Phase 6 Plan 03 |

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

**Next action:** Milestone v0.1.0 complete. All 6 phases done.

**To resume:** Read ROADMAP.md and this STATE.md. All phases complete — summaries in `phases/` subdirectories.

**Last session:** 2026-02-28T03:08:00Z
**Stopped at:** Completed 06-03-PLAN.md (ExecutionService Extract Class refactoring) -- final plan of milestone

---
*Initialized: 2026-02-25*
