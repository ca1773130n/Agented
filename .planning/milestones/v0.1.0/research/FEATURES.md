# Feature Research

**Domain:** Agentic development platform — production hardening for internal engineering use
**Researched:** 2026-02-25
**Confidence:** HIGH (table stakes section), MEDIUM (differentiators), HIGH (anti-features)

---

## Context: What Already Exists

Agented already ships a comprehensive feature set:
- Trigger management (webhook, GitHub, schedule, manual)
- Bot execution via subprocess (Claude, OpenCode, Gemini, Codex CLIs)
- SSE log streaming (real-time execution logs to browser)
- Agent and team management with topology visualization
- Workflow engine (DAG, topological sort)
- Account rotation and fallback chain orchestration
- Budget enforcement and rate limit monitoring
- Super agent playground with state_delta SSE protocol
- Audit logging, execution history, project session management
- GRD planning UI (Kanban board)
- MCP server configuration management

**Gap being addressed:** The platform lacks production hardening — no auth, no deployment config, in-memory state, no structured error monitoring. This research maps what is table stakes vs. differentiating vs. actively harmful for the *next* milestone.

---

## Feature Landscape

### Table Stakes (Must Have — Platform Is Unusable in Production Without These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **API Authentication (API key or JWT)** | Every internal tool exposed beyond localhost must require credentials. Currently zero auth on all 44+ routes including admin/delete operations. | MEDIUM | `app.before_request` middleware checking a static API key from env var is lowest-friction start. Flask-JWT-Extended for multi-user. For single-team internal use, a shared API key is sufficient. |
| **CORS lockdown** | Currently defaults to `origins: "*"`. Any website can make requests to the API from a browser. | LOW | Set `CORS_ALLOWED_ORIGINS` to explicit list; fail-closed (no origins if env var unset). One-line env var fix. |
| **Stable SECRET_KEY** | Flask secret is re-generated every restart. Breaks session continuity, future cookie-based CSRF. | LOW | Require `SECRET_KEY` env var or write-once generation to disk. |
| **Production WSGI configuration (gunicorn + gevent)** | Flask dev server is single-threaded. SSE connections block the worker. Gunicorn with `gevent` workers is the minimal viable production config for SSE. | MEDIUM | `gunicorn --worker-class gevent --workers 1 --worker-connections 100` for single-machine. A `gunicorn.conf.py` and updated `just deploy` target. Gevent workers handle many concurrent SSE connections without blocking. |
| **Process supervisor / restart-on-crash** | `just deploy` runs `python run.py &` — process dies silently. No restart. | LOW–MEDIUM | systemd unit file (Linux) or launchd plist (macOS) for the Harness engineering context. Docker Compose with `restart: unless-stopped` is the universal solution. |
| **Structured logging with request IDs** | Currently logs to stdout with no structure. Debugging failures in production requires parseable log lines. | LOW | Python `logging` with JSON formatter (structlog or just json.dumps). Add `request_id` correlation to every log line via Flask `g`. No external dependency required. |
| **DB-backed webhook deduplication** | Current in-memory dedup dict is lost on restart. Webhook flood post-restart bypasses dedup. Dict also never pruned (memory leak). | LOW | Persist dedup keys (webhook hash + 60-second TTL) to SQLite. Single table, tiny cost. |
| **Prompt injection guardrails (minimal)** | Externally-sourced content (webhook `message_text`, GitHub PR titles/authors) is directly interpolated into AI prompts without sanitization. This is a documented High severity concern. | LOW–MEDIUM | At minimum: truncate `message_text` to reasonable length (e.g. 2000 chars), strip null bytes and known injection patterns. Document that full mitigation requires prompt structure separation (user content in quoted block). |
| **Environment variable documentation (.env.example)** | No `.env` file or example exists. Operators must read source to discover `AGENTED_DB_PATH`, `SECRET_KEY`, `CORS_ALLOWED_ORIGINS`, `GITHUB_WEBHOOK_SECRET`. | LOW | `.env.example` with all vars, types, defaults, and notes. Zero code change. |
| **Health endpoint hardening** | `/health/readiness` currently exposes execution IDs, process details, and startup warnings without auth. | LOW | Auth-gate health endpoint or strip sensitive fields from unauthenticated health response. |

**Dependency chain for table stakes:**
```
SECRET_KEY (stable)
  → enables → Session-based auth in future
  → enables → CSRF protection

API Authentication
  → blocks → all admin routes without credentials
  → depends on → stable SECRET_KEY

Gunicorn + gevent workers
  → enables → concurrent SSE connections without blocking
  → depends on → process supervisor (to restart on crash)

DB-backed webhook dedup
  → depends on → SQLite (already in use, trivial addition)

CORS lockdown
  → depends on → API Authentication (auth without CORS lockdown is incomplete)
```

---

### Differentiators (Competitive Advantage for Engineering Teams)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **OpenTelemetry (OTEL) trace export** | Industry is converging on OTEL as the standard for agent telemetry. Agented already has structured audit logs and SSE streaming. Adding OTEL spans for execution lifecycle (trigger → prompt render → subprocess start → first token → completion) gives teams standard tooling (Jaeger, Grafana Tempo, Datadog). 89% of orgs with production agents have some form of observability. | HIGH | Requires `opentelemetry-sdk` + `opentelemetry-instrumentation-flask`. High value but high effort. Defer unless specifically requested. |
| **Execution replay / retry UI** | Execution history exists in DB. A "replay this execution" button (re-run same trigger with same params) reduces friction for debugging flaky AI runs. | MEDIUM | Already have execution record with trigger_id + prompt + context. Replay is `run_trigger(stored_params)` wired to a UI button. Differentiating for engineering workflows. |
| **Prompt injection audit trail** | Log what was substituted into each prompt field for each execution (truncated, with hash of full content). Enables forensic review of "why did the bot do that?" | LOW–MEDIUM | Extend `execution_logs` with a `prompt_context` JSON field. Low code cost, high diagnostic value. |
| **Rate limit / budget dashboard enhancements** | Already have `MonitoringService` and charts. Adding per-project and per-team budget views (not just global) and email/Slack notifications when thresholds are crossed. | MEDIUM | Notification integration requires choosing a channel (Slack webhook is simplest). Per-project budget already has DB structure (`budget_limits`). |
| **Workflow execution visualization (live)** | Workflow engine exists but there is no live progress view during execution. A real-time DAG view showing current node status (running/complete/error) during workflow execution would be a significant DX improvement. | HIGH | Requires SSE events from `WorkflowExecutionService` with node-level status. `WorkflowExecutionService._executions` already tracks node state in-memory. Wire to SSE endpoint + animate in VueFlow canvas. |
| **CLI tools health check on dashboard** | Users need to know whether `claude`, `opencode`, `gemini`, `codex` binaries are installed and authenticated before trying to run bots. Backend detection service already probes for these. Surface this prominently as a pre-flight checklist on the dashboard. | LOW | Frontend-only change. Call existing `/admin/backends` or detection endpoint. High UX value for new users. |
| **Webhook payload inspector** | A UI view showing recent raw inbound webhook payloads with field path highlighting (to validate `text_field_path` config). Reduces time to configure new webhook triggers. | MEDIUM | Store last N raw payloads per webhook trigger in DB (truncated). Display in trigger config UI. |
| **Execution concurrency control (per-trigger throttle)** | Currently no per-trigger rate limiting. A trigger can fire many simultaneous executions. A `max_concurrent` field per trigger (queue excess runs) prevents resource exhaustion. | MEDIUM | Requires a per-trigger semaphore or queue. Existing `ProcessManager` tracks processes but does not enforce per-trigger limits. |

**Dependency chain for differentiators:**
```
Execution replay
  → depends on → Execution history (already exists)
  → depends on → API Auth (replay is a privileged operation)

Workflow live visualization
  → depends on → WorkflowExecutionService SSE events (need to add)
  → depends on → VueFlow canvas (already in use)

Rate limit notifications
  → depends on → MonitoringService (already exists)
  → depends on → notification channel config (new)

OTEL trace export
  → depends on → structured logging (table stakes)
  → depends on → gunicorn setup (table stakes)
```

---

### Anti-Features (Commonly Requested, Often Problematic — Deliberately Avoid)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Multi-tenant auth (user accounts, login flows, RBAC)** | Looks like the natural evolution of "add auth." Tempting when adding any auth. | Agented is explicitly single-org internal tooling. Full user management (registration, password reset, role management, session invalidation) would take 3–4x the time of a shared API key and solve a problem that does not exist for this use case. `Out of Scope` per PROJECT.md. | Shared API key via env var. Single secret for the whole engineering team. If role separation becomes genuinely needed, revisit. |
| **PostgreSQL migration** | SQLite has real limitations under concurrent write load. Developers who know production DBs want Postgres. | Raw SQLite with no ORM means a PostgreSQL migration is a full rewrite of the DB layer (53 migrations, 90+ service files with raw SQL). The concurrency problems (write contention) do not affect a single-machine deployment at current scale. SQLite 4.0 improvements also extend the useful range. | Defer. Use WAL mode (already enabled), connection timeout (already set), and keep write operations fast. Revisit when concurrent writes are measurably causing failures. |
| **Redis for pub/sub and SSE fan-out** | The standard pattern for multi-process SSE streaming. Redis pub/sub solves the in-memory state problem. | Adds operational complexity (Redis process, configuration, health monitoring). The in-memory state problem only manifests at `--workers > 1` in gunicorn. Constraining to `--workers 1 --worker-class gevent` sidesteps this entirely for single-machine use. | Gunicorn single-worker + gevent for concurrent connections. Add `assert workers == 1` guard in startup. Document the constraint. If horizontal scaling becomes a real requirement, Redis is the right path. |
| **CI/CD pipeline integration** | Natural ask for any platform used by engineers. Auto-deploy on push, run tests in pipeline. | Not Agented's responsibility — Agented *is* the CI/CD-adjacent automation tool. Building Agented's own CI/CD is an internal ops concern. Adding GitHub Actions workflows for Agented itself is low value vs. the effort of auth + deployment hardening. | Use `just build && cd backend && uv run pytest` locally. Add CI later when the auth and deployment concerns are resolved. |
| **Plugin marketplace / third-party extensions** | Platforms add marketplaces to grow ecosystems. Already has a skill marketplace stub. | Engineering effort to build, secure, and maintain a marketplace is enormous. The existing plugin/skill system (CRUD in DB) already provides customization. An external marketplace implies trust boundaries, sandboxing, and versioning that do not exist. | Enhance existing plugin CRUD. Allow skill import from URL (already partially exists in `skill_marketplace_service.py`). |
| **Full RBAC with resource-level permissions** | "Some users should only see their team's triggers" — reasonable engineering concern at scale. | For a single-team internal tool at Harness engineering scale, per-resource permissions add complexity without meaningful security benefit when the entire team already has access to the codebase and database. | API key auth with a single secret. If there is a genuine need to separate access (e.g., read-only for some team members), a second read-only API key is sufficient. |
| **Real-time collaborative editing (conflict resolution)** | Multiple engineers editing the same workflow or trigger config simultaneously. | Agented is not a collaborative editing platform. Conflicts are extremely rare for a team-internal tool. Adding CRDTs or OT is massive over-engineering. | Last-write-wins (current behavior). Add optimistic locking (ETag header) only if conflicts are reported as actual problems. |
| **Horizontal scaling / Kubernetes deployment** | Enterprise platforms run on K8s. Some engineers will request this. | In-memory state (log buffers, SSE subscribers, process manager) is fundamentally incompatible with horizontal scaling without a Redis layer first. K8s without solving the state externalization problem would silently break SSE and dedup. | Single-machine gunicorn deployment. Document the single-worker constraint explicitly. Horizontal scaling is a future milestone after Redis pub/sub is added. |

---

## Feature Dependencies

```
Table Stakes (must complete first):
  API Authentication
    ← requires ← stable SECRET_KEY
    ← enables → CORS lockdown (auth + CORS = complete access control)
    ← enables → Health endpoint hardening

  Production WSGI (gunicorn + gevent)
    ← enables → Concurrent SSE connections
    ← requires → Process supervisor

  Structured logging
    ← enables → OTEL trace export (differentiator)
    ← enables → Prompt injection audit trail (differentiator)

  DB-backed webhook dedup
    ← replaces → In-memory dedup (current, leaks)

Differentiators (build after table stakes):
  Execution replay UI
    ← requires → API Auth
    ← requires → Execution history (exists)

  Workflow live visualization
    ← requires → WorkflowExecutionService SSE events (new)

  Rate limit notifications
    ← requires → MonitoringService (exists)

  OTEL export
    ← requires → Structured logging (table stakes)
    ← requires → Gunicorn setup (table stakes)
```

---

## MVP Definition (for "Production Hardening" Milestone)

### Launch With (v1 — Production-Safe)

- [ ] **API authentication (shared API key)** — platform is unsafe without it
- [ ] **CORS lockdown** — complement to auth; wildcard CORS is actively dangerous
- [ ] **Stable SECRET_KEY** — prerequisite for any session/cookie-based security
- [ ] **Gunicorn + gevent worker config** — SSE breaks under Flask dev server at load
- [ ] **Process supervisor** — server must restart-on-crash automatically
- [ ] **Structured logging with request IDs** — minimum viable debugging in production
- [ ] **DB-backed webhook dedup** — current implementation leaks and resets on restart
- [ ] **.env.example** — operators cannot configure without documentation

### Add After Initial Hardening (v1.x)

- [ ] **Prompt injection guardrails (truncation + sanitization)** — reduces documented High severity risk; can iterate
- [ ] **Health endpoint hardening** — auth-gate or strip sensitive fields
- [ ] **CLI tools health check on dashboard** — high UX value, low code cost
- [ ] **Execution replay / retry UI** — high DX value for debugging

### Future Consideration (v2+)

- [ ] **Webhook payload inspector** — useful but not blocking production use
- [ ] **Execution concurrency control (per-trigger throttle)** — implement when resource exhaustion is observed
- [ ] **Workflow live visualization** — high complexity, high value; after execution replay is validated
- [ ] **OTEL trace export** — after structured logging is established and team has a backend to send to
- [ ] **Rate limit / budget notifications** — after core hardening is stable

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| API authentication (shared API key) | HIGH | LOW | P1 |
| CORS lockdown | HIGH | LOW | P1 |
| Stable SECRET_KEY | HIGH | LOW | P1 |
| Gunicorn + gevent config | HIGH | LOW | P1 |
| Process supervisor (systemd/launchd/Docker) | HIGH | LOW | P1 |
| Structured logging + request IDs | HIGH | LOW | P1 |
| DB-backed webhook dedup | MEDIUM | LOW | P1 |
| .env.example | MEDIUM | LOW | P1 |
| Prompt injection guardrails | HIGH | MEDIUM | P2 |
| Health endpoint hardening | MEDIUM | LOW | P2 |
| CLI tools health check on dashboard | HIGH | LOW | P2 |
| Execution replay UI | HIGH | MEDIUM | P2 |
| Webhook payload inspector | MEDIUM | MEDIUM | P3 |
| Execution concurrency control | MEDIUM | MEDIUM | P3 |
| Workflow live visualization | HIGH | HIGH | P3 |
| OTEL trace export | MEDIUM | HIGH | P3 |
| Rate limit notifications | MEDIUM | MEDIUM | P3 |

---

## Sources

- [Top AI Agent Orchestration Platforms in 2026 — Redis](https://redis.io/blog/ai-agent-orchestration-platforms/)
- [Why Observability is Table Stakes for Multi-Agent Systems — SoftwareSeni](https://www.softwareseni.com/why-observability-is-table-stakes-for-multi-agent-systems-in-production-environments/)
- [A practical guide for AI observability for agents (2025) — Vellum](https://www.vellum.ai/blog/understanding-your-agents-behavior-in-production)
- [Best practices for AI agent security in 2025 — Glean](https://www.glean.com/perspectives/best-practices-for-ai-agent-security-in-2025/)
- [Webhook Best Practices: Production-Ready Implementation Guide — InventiveHQ](https://inventivehq.com/blog/webhook-best-practices-guide)
- [Webhooks at Scale: Best Practices and Lessons Learned — Hookdeck](https://hookdeck.com/blog/webhooks-at-scale)
- [Gunicorn — Flask Documentation (3.1.x)](https://flask.palletsprojects.com/en/stable/deploying/gunicorn/)
- [Running a Flask Application as a Service with Systemd — miguelgrinberg.com](https://blog.miguelgrinberg.com/post/running-a-flask-application-as-a-service-with-systemd)
- [Protect your Flask API with RBAC and JWT validation — Logto docs](https://docs.logto.io/api-protection/python/flask)
- [7 Common IDP Implementation Pitfalls — Fairwinds](https://www.fairwinds.com/blog/how-to-avoid-7-idp-implementation-pitfalls)
- [SQLite in 2025: Why This "Simple" DB Powers Major Apps — Nihar Daily](https://www.nihardaily.com/92-the-future-of-sqlite-trends-developers-must-know)
- [Enterprise AI in 2026: Scaling AI Agents with Autonomy, Orchestration, and Accountability — Cloud Wars](https://cloudwars.com/ai/enterprise-ai-in-2026-scaling-ai-agents-with-autonomy-orchestration-and-accountability/)

---

*Feature research for: AI agentic development platform — production hardening*
*Researched: 2026-02-25*
