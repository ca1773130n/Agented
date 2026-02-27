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
| Flask | 69k+ | Backend web framework | In use |
| Vue 3 | 48k+ | Frontend SPA framework | In use |
| flask-openapi3 | 1k+ | OpenAPI spec generation for Flask | In use |
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

- [ ] Improve production readiness (deployment config, process management, log rotation)
- [ ] Address security concerns (authentication, authorization, CORS hardening)
- [ ] Improve code quality (reduce god modules, eliminate duplicate pricing, add DI)
- [ ] Enhance scalability (externalize in-memory state, connection pooling)
- [ ] Add comprehensive test coverage
- [ ] Improve frontend type safety (reduce `any` usage)

### Out of Scope

- Multi-tenant SaaS deployment — platform is designed for single-org internal use
- Custom LLM training/fine-tuning — leverages existing CLI tools
- Mobile app — web dashboard only

## Context

Agented is a brownfield project with a substantial existing codebase:
- **Backend:** Flask + flask-openapi3, raw SQLite, 90+ service classes, 44+ API blueprints
- **Frontend:** Vue 3 + TypeScript SPA, Chart.js for monitoring, VueFlow for graph canvases
- **Execution model:** Subprocess-based CLI invocation with threaded log streaming
- **Key design choices:** No ORM (raw SQL), no state management library (component-local state), in-memory log buffers with SSE fan-out

The codebase has grown organically and has accumulated technical debt documented in `.planning/codebase/CONCERNS.md`. The primary concerns are: no authentication, in-memory state incompatible with scaling, god modules, and no production deployment configuration.

## Constraints

- **Tech stack**: Flask backend + Vue 3 frontend — established, not changing
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
| No auth | Internal tool, local network only | Must address before any external exposure |
| flask-openapi3 over Flask | Auto-generated OpenAPI spec + Swagger UI + Pydantic validation | Good |
| No frontend state library | Simplicity for data-fetch-display pattern | Good for current scale |

---
*Last updated: 2026-02-25 after initialization (auto + YOLO mode)*
