# Agented

## What This Is

Agented is a agentic development platform for Harness engineering that organizes teams, agents, and automation into a working structure. It provides a dashboard to define products, projects, and teams, then wire up AI agents, bots, skills, and webhooks to automate work — from PR reviews to security audits to scheduled tasks.

## Core Value

Enable engineering teams to orchestrate AI-powered automation (bots, agents, workflows) through a unified dashboard that handles triggering, execution, monitoring, and team coordination without requiring infrastructure expertise.

## Research Objectives

| # | Hypothesis | Status | Evidence |
|---|-----------|--------|----------|
| H1 | A unified dashboard for managing AI agents and bots reduces time-to-automation for engineering teams | Untested | - |
| H2 | Multi-provider fallback chains with account rotation maximize AI execution availability | Untested | - |
| H3 | DAG-based workflows can compose individual bots/agents into complex automation pipelines | Untested | - |
| H4 | Real-time SSE streaming provides sufficient observability for AI execution monitoring | Untested | - |

**Primary question:** Can a platform that abstracts AI CLI tools behind a management layer provide reliable, observable automation for engineering teams?

## Quality Targets

| Metric | Current | Target | Stretch | Notes |
|--------|---------|--------|---------|-------|
| Backend test pass rate | - | 100% | 100% | All pytest tests |
| Frontend build (vue-tsc) | - | 0 errors | 0 errors | Type-safe frontend |
| Frontend test pass rate | - | 100% | 100% | All vitest tests |
| API response time (p95) | - | <200ms | <100ms | CRUD operations |
| SSE latency | - | <500ms | <100ms | Log line to browser |
| Concurrent executions | - | 10 | 50 | Simultaneous bot runs |

**Baseline reference:** Current codebase state (brownfield)

## External References

### Key Papers

(None — this is an engineering platform, not a research project)

### Key Repositories

| Repo | Stars | What It Does | Status |
|------|-------|-------------|--------|
| Litestar | 5k+ | Backend web framework (since wave 80, replaced Flask) | In use |
| Vue 3 | 48k+ | Frontend SPA framework | In use |
| Pydantic v2 + msgspec | — | Request/response models on Litestar | In use |
| APScheduler | 6k+ | Background job scheduling | In use |

### Datasets

(Not applicable — platform project)

## Requirements

### Validated

- V **Trigger Management** — CRUD for webhook, GitHub, and scheduled triggers with prompt templates — existing
- V **Bot Execution** — Subprocess-based CLI execution of Claude, OpenCode, Gemini, Codex with stdout/stderr streaming — existing
- V **SSE Log Streaming** — Real-time execution log delivery to browser via Server-Sent Events — existing
- V **GitHub Webhook Integration** — HMAC-validated GitHub PR event processing with trigger matching — existing
- V **Scheduled Triggers** — APScheduler-based cron triggers with timezone support — existing
- V **Agent Management** — CRUD for AI agents with roles, goals, capabilities, and skills — existing
- V **Team Management** — Multi-agent team creation with topology visualization — existing
- V **Product/Project Organization** — Hierarchical product > project > team structure — existing
- V **Plugin System** — Plugin CRUD with skills, hooks, commands, and rules — existing
- V **Workflow Engine** — DAG-based workflow execution with topological sort — existing
- V **Account Rotation & Fallback** — Orchestrated execution across multiple AI backend accounts — existing
- V **Budget Enforcement** — Token usage tracking and budget limit enforcement — existing
- V **Rate Limit Monitoring** — Provider rate limit polling with threshold alerts — existing
- V **Super Agent Playground** — Interactive AI chat with state_delta SSE protocol — existing
- V **Execution History** — Execution log persistence and retrieval — existing
- V **Audit Logging** — Structured audit event logging — existing
- V **MCP Server Management** — Preset and custom MCP server configuration — existing
- V **GRD Planning UI** — Kanban board for GRD milestone/phase planning — existing
- V **Project Sessions** — PTY-based project terminal sessions — existing
- V **CLI Proxy (OAuth)** — CLIProxyAPI for Claude account OAuth token management — existing

### Active

#### v0.2.0 — Miscellaneous
- [ ] Visual workflow builder and pipeline automation (DAG canvas, conditional triggers, approval gates)
- [ ] Execution intelligence and replay (output diff, context injection, smart chunking, branching)
- [ ] Bot authoring and template ecosystem (marketplace, NL creator, snippet library, version control)
- [ ] Analytics and monitoring dashboards (cost tracking, effectiveness, trends, health, impact reports)
- [ ] Enterprise integrations and governance (Slack/JIRA, RBAC, audit trail, secrets vault, GitOps)
- [ ] Specialized automation bots (vulnerability triage, code tours, test coverage, postmortem, changelog)
- [ ] Execution resilience and infrastructure (circuit breakers, retry, queue, persistence, cancellation)
- [ ] API hardening and developer experience (dry-run, error models, pagination, rate limiting, cron)
- [ ] Code consistency and standards (logging, error responses, return types, naming, frontend types)
- [ ] Frontend quality and user experience (loading states, error boundaries, shared composables, docs)

### Out of Scope

- Multi-tenant SaaS deployment — platform is designed for single-org internal use
- Custom LLM training/fine-tuning — leverages existing CLI tools
- Mobile app — web dashboard only

## Context

Agented is a brownfield project with a substantial existing codebase:
- **Backend:** Litestar served by gunicorn (UvicornWorker), Pydantic v2 + msgspec, raw SQLite, 90+ service classes. Flask was retired in wave 80 (v0.7.x window); Litestar is the canonical surface.
- **ai-accounts sidecar:** Separate Litestar process on :20001 owning OAuth identity for Claude / Codex / Gemini / OpenCode accounts.
- **Frontend:** Vue 3 + TypeScript SPA, Chart.js for monitoring, VueFlow for graph canvases.
- **Execution model:** Subprocess-based CLI invocation (`subprocess.Popen` + PTY fork). Per-session ring buffer + SSE fan-out.
- **Key design choices:** No ORM (raw SQL via `get_connection()`), no state management library (component-local state), in-memory log buffers with SSE fan-out.

The codebase has grown organically and has accumulated technical debt documented in `.planning/codebase/CONCERNS.md`. Several historical concerns are now resolved: per-user RBAC + ApiKey middleware shipped in the v0.6.x wave; the SuperAgent → goal_loop bridge (v0.7.91+) covers cross-session orchestration. Open concerns remain around in-memory state preventing horizontal scaling.

## Constraints

- **Tech stack**: Litestar backend (post-wave-80) + Vue 3 frontend — established, not changing
- **Database**: SQLite — current choice, migration to PostgreSQL is a future possibility
- **Execution**: Subprocess-based CLI tools — requires claude/opencode/gemini/codex installed on host
- **Platform**: macOS/Linux only — PTY service uses POSIX fork
- **Deployment**: Single-machine — in-memory state prevents horizontal scaling currently

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Raw SQLite, no ORM | Simplicity for rapid development | Good for now, revisit at scale |
| Subprocess CLI execution | Reuse existing AI CLI tools without API integration | Good — supports multiple providers |
| In-memory log streaming | Sub-millisecond SSE fan-out without infrastructure | Limits to single-process deployment |
| ApiKey + bearer-session auth (wave 80+) | Middleware-level gate; per-user user_id scoping on owned-entity routes | Good — closes the original "no auth" concern |
| Litestar over Flask (wave 80) | Native async, OpenAPI, msgspec validation; better SSE story than Flask | Good — full migration complete |
| No frontend state library | Simplicity for data-fetch-display pattern | Good for current scale |

## Current Milestone

**v0.7.98** (last shipped 2026-05-21 via PR #146 `refactor(v0.7.98): simplify v0.7.95-.97 wave`)

Shipping cadence has been PR-driven since v0.5.1 — no formal GRD roadmap; each
commit-message version tag corresponds to one merged PR. Per-version STATE.md
stubs at ``.planning/milestones/v0.7.N/STATE.md`` (94 files, backfilled via
PR #148). See ``.planning/MILESTONES.md`` for the chronological summary.

---
*Last updated: 2026-05-21 — version bump to v0.7.98 + GRD docs refreshed for the post-v0.5.0 PR-driven era*
