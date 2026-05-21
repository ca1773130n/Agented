# Requirements Archive: v0.2.0 Miscellaneous

**Archived:** 2026-03-05
**Status:** SHIPPED

For current requirements, see `.planning/REQUIREMENTS.md`.

---

# Requirements

**Project:** Agented — Miscellaneous Milestone
**Created:** 2026-03-04
**Source:** Discovered work groups from /grd:evolve analysis (product-ideation, new-features, consistency, usability dimensions)

---

## v1 Requirements (v0.1.0 — Production Hardening)

> Carried forward from previous milestone. See `.planning/milestones/v0.1.0/` for details.

---

## v2 Requirements (v0.2.0 — Miscellaneous)

### Workflow Automation & Pipeline Intelligence (WF)

- [ ] **WF-01**: Visual drag-and-drop DAG builder canvas where users chain bots/agents into multi-step pipelines with connected nodes and edges
- [ ] **WF-02**: Conditional trigger logic rules — if/else conditions on PR attributes (line count, branch pattern, draft status) to control which bots fire
- [ ] **WF-03**: Human-in-the-loop approval gates — execution pauses at checkpoints and sends Slack/email notification; reviewer approves or rejects before proceeding
- [ ] **WF-04**: Multi-model fallback and routing chains — per-bot AI provider priority lists with automatic failover on rate-limit and smart routing (cheap model for small diffs, expensive for large)
- [ ] **WF-05**: Workflow DAG conditional branch nodes — `condition_node` type with expression field that routes execution based on previous node output
- [ ] **WF-06**: Per-node retry policy — `retry_policy: {max_attempts, backoff_strategy}` field on workflow nodes so transient failures don't abort the entire DAG

### Execution Intelligence & Replay (EXE)

- [ ] **EXE-01**: Execution replay with identical inputs and side-by-side output diff comparison for A/B testing prompt revisions and regression detection
- [ ] **EXE-02**: Diff-aware context injection — automatically extract only changed files and relevant surrounding context from PRs for bot prompts, reducing token cost and improving output quality
- [ ] **EXE-03**: Smart context window chunking — break large code contexts into semantically meaningful chunks, run bot against each, merge and deduplicate results
- [ ] **EXE-04**: Agent conversation branching — fork from any point in an execution transcript with a different follow-up prompt to explore alternatives without losing the original
- [ ] **EXE-05**: Live collaborative execution viewer — multiple team members watch the same live execution stream with presence indicators and inline commenting on log lines

### Bot Authoring & Template Ecosystem (TPL)

- [ ] **TPL-01**: Bot template marketplace — curated gallery of pre-built, one-click deployable bot configurations (PR reviewer, dependency updater, security scanner, changelog generator, test writer)
- [ ] **TPL-02**: Natural language bot creator — describe automation in plain English and AI generates complete bot configuration including trigger rules, prompt template, and model selection
- [ ] **TPL-03**: Reusable prompt snippet library — shared named snippets (e.g., 'standard security checklist', 'PEP-8 style guide') referenced by variable in any bot prompt, update once propagate everywhere
- [ ] **TPL-04**: Prompt template version control — git-like history for prompt templates with author, timestamp, diff view, and one-click rollback to any previous version
- [ ] **TPL-05**: Webhook payload test console — in-app panel to send custom or recorded payloads to any trigger, preview rendered prompt, and simulate execution without running the bot

### Analytics & Monitoring Dashboards (ANA)

- [ ] **ANA-01**: Execution cost and token usage dashboard — track estimated API token consumption and cost per bot, per team, and per project over time with trend charts and budget alerts
- [ ] **ANA-02**: Bot effectiveness feedback loop — track whether PR review suggestions were accepted (resolved, code changed) vs. ignored, show acceptance rate metric per bot over time
- [ ] **ANA-03**: Execution analytics trend dashboard — time-series charts showing execution volume, success/failure rates, average duration, and model usage across all bots and teams
- [ ] **ANA-04**: Bot health monitoring and alerting — detect when a bot fails >N times in a row, takes >3x average execution time, or hasn't fired unexpectedly long; send alerts via email/Slack/PagerDuty
- [ ] **ANA-05**: Weekly team automation impact report — scheduled digest per team with PRs reviewed, issues found, time saved estimate, top performing bots, and bots needing attention
- [ ] **ANA-06**: Smart scheduling suggestions — analyze repo activity patterns (commit frequency, PR volume by hour/day) and suggest optimal scheduled trigger times
- [ ] **ANA-07**: Per-bot execution budget and time limits — hard limits on max execution time, max tokens, and max monthly runs per bot with graceful cancellation and owner notification

### Enterprise Integrations & Governance (INT)

- [ ] **INT-01**: Slack/Teams bidirectional integration — receive execution result summaries in channels, trigger bots via slash command (e.g., '/agented run security-audit on payments-service')
- [ ] **INT-02**: JIRA/Linear auto-issue creation — when bots produce findings, automatically create structured tickets with severity, context, and links
- [ ] **INT-03**: Bot configuration import/export as YAML/JSON with optional GitOps sync from a Git repository so PR-based changes are the source of truth
- [ ] **INT-04**: Role-based access control — Viewer (read logs), Operator (run bots), Editor (create/edit bots), Admin (manage team/billing) with fine-grained permissions
- [ ] **INT-05**: Full audit trail tracking every configuration change to bots, triggers, teams, and agents — who changed what, when, and before/after state
- [ ] **INT-06**: Built-in encrypted secret and credential vault — store API keys, tokens, credentials with access controls, rotation reminders, and audit logs; injected as env vars at runtime
- [ ] **INT-07**: Multi-repo orchestration campaigns — run a single bot across multiple repositories simultaneously with consolidated findings in a single view
- [ ] **INT-08**: Execution context pinning and bookmarking — bookmark runs with notes and tags, pin to bot profile page, share deep-links to specific log lines

### Specialized Automation Bots (BOT)

- [ ] **BOT-01**: Dependency vulnerability triage bot — scheduled scan of package manifests, CVE cross-referencing, exploitability scoring, and prioritized ticket creation with fix recommendations
- [ ] **BOT-02**: New engineer code tour generator — triggered on first repo access, generates structured tour (entry points, key abstractions, data flow, gotchas) tailored to the specific repo
- [ ] **BOT-03**: Test coverage gap detector — on every PR, analyze changed code and identify untested functions/branches with specific test case suggestions
- [ ] **BOT-04**: Incident postmortem assistant — triggered from incident closure, pulls relevant logs, PRs, deployment history, and runbook, drafts structured postmortem document
- [ ] **BOT-05**: Automated changelog generation — scheduled or merge-triggered bot reads merged PRs, groups by type (feat/fix/breaking), generates formatted CHANGELOG entry or GitHub Release draft
- [ ] **BOT-06**: Auto-generated PR summaries — post concise, human-readable summary comment on every PR explaining what changed, why it matters, and what reviewers should focus on
- [ ] **BOT-07**: Natural language search across execution logs — search historical outputs using plain English queries (e.g., 'show me all PRs where the bot flagged SQL injection')

### Execution Resilience & Infrastructure (RES)

- [ ] **RES-01**: Circuit breaker for AI backend failures — fast-fail new requests when a backend is consistently unavailable, recover automatically when healthy
- [ ] **RES-02**: Configurable retry mechanism for transient execution failures (502, 503, network timeout) with pluggable backoff curves and max-retry caps
- [ ] **RES-03**: Execution queue with concurrency caps per bot — serialize or limit concurrent executions to prevent API rate limit exhaustion and resource starvation
- [ ] **RES-04**: Persistent retry queue (SQLite-backed) replacing in-memory threading.Timer — survives server restarts and is visible in admin UI
- [ ] **RES-05**: Pause/resume support for running executions — pause for maintenance or rate limit recovery without data loss
- [ ] **RES-06**: Running execution cancellation via API endpoint — cancel individual executions or bulk cancel by status/trigger filter
- [ ] **RES-07**: Webhook payload signature validation — verify HMAC signatures (SHA-256 default, configurable algorithm) with per-trigger webhook secrets
- [ ] **RES-08**: Persist execution state and history to database — replace in-memory 5-minute TTL tracking with durable records for historical analysis
- [ ] **RES-09**: Persist workflow execution history to database — enable history views, failure debugging, and execution pattern analytics

### API Hardening & Developer Experience (API)

- [ ] **API-01**: Dry-run mode for trigger dispatching, workflow validation, and bot configuration testing — render prompt and show CLI command without spawning subprocess
- [ ] **API-02**: Unified error response model — shared ErrorResponse Pydantic model with `code`, `message`, `details` fields across all endpoints
- [ ] **API-03**: Cursor/offset pagination on all list endpoints — prevent unbounded result sets as data grows
- [ ] **API-04**: Execution list search and filter — query params for status, trigger_id, date range, and text search over execution output
- [ ] **API-05**: Bulk create/update/delete endpoints for entities (agents, bots, plugins, skills)
- [ ] **API-06**: Rate limiting on all REST API endpoints via Flask-Limiter middleware
- [ ] **API-07**: Request ID propagation middleware — correlate webhook receipt, trigger match, execution start, and log lines as a single trace
- [ ] **API-08**: Pre-flight cost estimation endpoint — estimate token usage and cost before triggering an execution
- [ ] **API-09**: Workflow DAG validation at creation/update time — reject invalid graphs at the API boundary instead of deferring to execution
- [ ] **API-10**: Cron expression support for scheduled triggers — standard cron syntax for precise scheduling (e.g., 'every 15 minutes during business hours')

### Code Consistency & Standards (CON)

- [ ] **CON-01**: Replace all print() calls with structured logger usage across backend services (51+ print calls in critical paths)
- [ ] **CON-02**: Standardize error response format to shared ErrorResponse model across all route handlers
- [ ] **CON-03**: Consistent return type annotations across all service and DB methods; standardize DB CRUD returns (create→str id, update→bool, delete→bool)
- [ ] **CON-04**: Enforce entity ID prefix convention with a central ID factory/validator; use secrets.choice() everywhere instead of random.choices()
- [ ] **CON-05**: Consistent exception handling patterns — documented severity levels, exc_info usage, and error context across all services
- [ ] **CON-06**: Standardize DB function naming (create_ prefix), service method styles (@classmethod vs instance), and async operation patterns
- [ ] **CON-07**: Replace magic numbers with named constants in centralized config module (timeouts, retry limits, alert thresholds, debounce values)
- [ ] **CON-08**: Consolidate frontend types — merge ConversationMessage/ChatMessage/Message into one canonical type; eliminate TypeScript `any` usage across 50+ interfaces
- [ ] **CON-09**: Standardize frontend composable patterns — shared useAsyncState composable, consistent error/loading lifecycle, deduplicate SSE setup code

### Frontend Quality & User Experience (UX)

- [ ] **UX-01**: Loading states, skeleton screens, and progress indicators for all async views and sidebar data loading
- [ ] **UX-02**: Vue error boundary component preventing full SPA crashes — show useful error message instead of blank screen
- [ ] **UX-03**: Shared useEventSource composable replacing duplicated SSE connection setup in useConversation and useAiChat
- [ ] **UX-04**: Centralized API error handler with consistent toast notifications — replace mix of silent console.warn and toasts
- [ ] **UX-05**: Per-section retry functionality for failed API loads — retry button tied to error state instead of requiring full page refresh
- [ ] **UX-06**: Actionable error messages — replace generic/raw exception text with user-friendly messages including error codes and suggested actions
- [ ] **UX-07**: OpenAPI documentation for all endpoint summaries, SSE protocol specs, prompt placeholder syntax, and workflow input format
- [ ] **UX-08**: Sidebar loading coordination — unified loading state across 7 concurrent async fetches with coordinated skeleton/progress display
- [ ] **UX-09**: Startup environment validation — fail fast with clear messages for missing/mistyped environment variables instead of silent runtime defaults

---

## Out of Scope

- **Multi-tenant SaaS deployment** — platform remains single-org internal tooling
- **Custom LLM training/fine-tuning** — leverages existing CLI tools
- **Mobile app** — web dashboard only
- **PostgreSQL migration** — SQLite WAL mode adequate at current scale
- **Kubernetes / horizontal scaling** — single-machine deployment target

---

## Traceability

| REQ-ID | Phase | Status |
|--------|-------|--------|
| WF-01 | Phase 7 — Workflow Automation & Pipeline Intelligence | Pending |
| WF-02 | Phase 7 — Workflow Automation & Pipeline Intelligence | Pending |
| WF-03 | Phase 7 — Workflow Automation & Pipeline Intelligence | Pending |
| WF-04 | Phase 7 — Workflow Automation & Pipeline Intelligence | Pending |
| WF-05 | Phase 7 — Workflow Automation & Pipeline Intelligence | Pending |
| WF-06 | Phase 7 — Workflow Automation & Pipeline Intelligence | Pending |
| EXE-01 | Phase 8 — Execution Intelligence & Replay | Pending |
| EXE-02 | Phase 8 — Execution Intelligence & Replay | Pending |
| EXE-03 | Phase 8 — Execution Intelligence & Replay | Pending |
| EXE-04 | Phase 8 — Execution Intelligence & Replay | Pending |
| EXE-05 | Phase 8 — Execution Intelligence & Replay | Pending |
| TPL-01 | Phase 9 — Bot Authoring & Template Ecosystem | Pending |
| TPL-02 | Phase 9 — Bot Authoring & Template Ecosystem | Pending |
| TPL-03 | Phase 9 — Bot Authoring & Template Ecosystem | Pending |
| TPL-04 | Phase 9 — Bot Authoring & Template Ecosystem | Pending |
| TPL-05 | Phase 9 — Bot Authoring & Template Ecosystem | Pending |
| ANA-01 | Phase 10 — Analytics & Monitoring Dashboards | Pending |
| ANA-02 | Phase 10 — Analytics & Monitoring Dashboards | Pending |
| ANA-03 | Phase 10 — Analytics & Monitoring Dashboards | Pending |
| ANA-04 | Phase 10 — Analytics & Monitoring Dashboards | Pending |
| ANA-05 | Phase 10 — Analytics & Monitoring Dashboards | Pending |
| ANA-06 | Phase 10 — Analytics & Monitoring Dashboards | Pending |
| ANA-07 | Phase 10 — Analytics & Monitoring Dashboards | Pending |
| INT-01 | Phase 11 — Enterprise Integrations & Governance | Pending |
| INT-02 | Phase 11 — Enterprise Integrations & Governance | Pending |
| INT-03 | Phase 11 — Enterprise Integrations & Governance | Pending |
| INT-04 | Phase 11 — Enterprise Integrations & Governance | Pending |
| INT-05 | Phase 11 — Enterprise Integrations & Governance | Pending |
| INT-06 | Phase 11 — Enterprise Integrations & Governance | Pending |
| INT-07 | Phase 11 — Enterprise Integrations & Governance | Pending |
| INT-08 | Phase 11 — Enterprise Integrations & Governance | Pending |
| BOT-01 | Phase 12 — Specialized Automation Bots | Pending |
| BOT-02 | Phase 12 — Specialized Automation Bots | Pending |
| BOT-03 | Phase 12 — Specialized Automation Bots | Pending |
| BOT-04 | Phase 12 — Specialized Automation Bots | Pending |
| BOT-05 | Phase 12 — Specialized Automation Bots | Pending |
| BOT-06 | Phase 12 — Specialized Automation Bots | Pending |
| BOT-07 | Phase 12 — Specialized Automation Bots | Pending |
| RES-01 | Phase 13 — Execution Resilience & Infrastructure | Pending |
| RES-02 | Phase 13 — Execution Resilience & Infrastructure | Pending |
| RES-03 | Phase 13 — Execution Resilience & Infrastructure | Pending |
| RES-04 | Phase 13 — Execution Resilience & Infrastructure | Pending |
| RES-05 | Phase 13 — Execution Resilience & Infrastructure | Pending |
| RES-06 | Phase 13 — Execution Resilience & Infrastructure | Pending |
| RES-07 | Phase 13 — Execution Resilience & Infrastructure | Pending |
| RES-08 | Phase 13 — Execution Resilience & Infrastructure | Pending |
| RES-09 | Phase 13 — Execution Resilience & Infrastructure | Pending |
| API-01 | Phase 14 — API Hardening & Developer Experience | Pending |
| API-02 | Phase 14 — API Hardening & Developer Experience | Pending |
| API-03 | Phase 14 — API Hardening & Developer Experience | Pending |
| API-04 | Phase 14 — API Hardening & Developer Experience | Pending |
| API-05 | Phase 14 — API Hardening & Developer Experience | Pending |
| API-06 | Phase 14 — API Hardening & Developer Experience | Pending |
| API-07 | Phase 14 — API Hardening & Developer Experience | Pending |
| API-08 | Phase 14 — API Hardening & Developer Experience | Pending |
| API-09 | Phase 14 — API Hardening & Developer Experience | Pending |
| API-10 | Phase 14 — API Hardening & Developer Experience | Pending |
| CON-01 | Phase 15 — Code Consistency & Standards | Pending |
| CON-02 | Phase 15 — Code Consistency & Standards | Pending |
| CON-03 | Phase 15 — Code Consistency & Standards | Pending |
| CON-04 | Phase 15 — Code Consistency & Standards | Pending |
| CON-05 | Phase 15 — Code Consistency & Standards | Pending |
| CON-06 | Phase 15 — Code Consistency & Standards | Pending |
| CON-07 | Phase 15 — Code Consistency & Standards | Pending |
| CON-08 | Phase 15 — Code Consistency & Standards | Pending |
| CON-09 | Phase 15 — Code Consistency & Standards | Pending |
| UX-01 | Phase 16 — Frontend Quality & User Experience | Pending |
| UX-02 | Phase 16 — Frontend Quality & User Experience | Pending |
| UX-03 | Phase 16 — Frontend Quality & User Experience | Pending |
| UX-04 | Phase 16 — Frontend Quality & User Experience | Pending |
| UX-05 | Phase 16 — Frontend Quality & User Experience | Pending |
| UX-06 | Phase 16 — Frontend Quality & User Experience | Pending |
| UX-07 | Phase 16 — Frontend Quality & User Experience | Pending |
| UX-08 | Phase 16 — Frontend Quality & User Experience | Pending |
| UX-09 | Phase 16 — Frontend Quality & User Experience | Pending |

Mapped: 89/89. No orphaned requirements.

---
*Created: 2026-03-04 (autonomous mode — from evolve-discovered work groups)*
