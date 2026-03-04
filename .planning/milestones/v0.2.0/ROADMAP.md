# Roadmap -- v0.2.0 Miscellaneous

**Created:** 2026-03-04
**Phases:** 10 (Phase 7 through Phase 16)
**Coverage:** 89/89 requirements mapped
**Depth:** Standard

---

## Overview

Milestone v0.2.0 delivers a broad set of enhancements across three priority tiers: product-ideation features that add entirely new capabilities (workflow builder, execution intelligence, bot templates, analytics, enterprise integrations, specialized bots), infrastructure hardening that makes the existing system more resilient and developer-friendly (execution resilience, API quality), and quality improvements that bring consistency and polish to the codebase and user experience (code standards, frontend UX).

Phases 7-12 are largely independent of each other and can be executed in any order. Phases 13-14 harden the platform and benefit from patterns established in feature phases. Phases 15-16 are cleanup/polish and can run in parallel at any time.

---

## Phases

### Phase 7: Workflow Automation & Pipeline Intelligence

**Goal:** Users can visually compose multi-step bot/agent pipelines with conditional logic, approval gates, fallback chains, and per-node resilience -- all from a drag-and-drop canvas.

**Dependencies:** None (builds on existing workflow engine and VueFlow canvas)

**Requirements:** WF-01, WF-02, WF-03, WF-04, WF-05, WF-06

**Verification Level:** proxy

**Plans:** 3 plans

Plans:
- [x] 07-01-PLAN.md -- Conditional logic, edge-aware branching, and approval gate backend engine
- [x] 07-02-PLAN.md -- Multi-model fallback agent nodes and comprehensive backend tests
- [x] 07-03-PLAN.md -- Frontend node types, canvas updates, and approval UX

**Success Criteria:**

1. A user can drag bot/agent nodes onto a canvas, connect them with edges, save the resulting DAG, and execute it end-to-end -- the pipeline runs each node in topological order and produces correct combined output
2. Conditional trigger rules evaluate PR attributes (line count, branch pattern, draft status) and correctly gate bot execution -- bots fire only when conditions match, verified with at least 5 distinct condition expressions
3. Approval gate nodes pause workflow execution and emit a notification; execution resumes only after explicit approve/reject action, with reject aborting downstream nodes
4. Multi-model fallback chains attempt providers in priority order -- when the primary provider returns a rate-limit error, the next provider is tried within 5 seconds, and cheap-vs-expensive routing selects model tier based on diff size threshold
5. Condition branch nodes route execution to different downstream paths based on previous node output, verified with at least 3 branching scenarios (pass/fail/skip)
6. Per-node retry policy retries a failed node up to the configured max_attempts with the specified backoff strategy, without restarting the entire DAG

---

### Phase 8: Execution Intelligence & Replay

**Goal:** Users can replay executions for A/B comparison, automatically feed bots only the relevant diff context, chunk large contexts intelligently, branch conversation histories, and collaboratively watch live runs.

**Dependencies:** None (builds on existing execution engine and SSE streaming)

**Requirements:** EXE-01, EXE-02, EXE-03, EXE-04, EXE-05

**Verification Level:** proxy

**Plans:** 5 plans

Plans:
- [ ] 08-01-PLAN.md -- Execution replay service + diff-aware context injection backend (EXE-01, EXE-02)
- [ ] 08-02-PLAN.md -- Smart chunking service + conversation branching backend (EXE-03, EXE-04)
- [ ] 08-03-PLAN.md -- Collaborative viewer service with presence and inline comments backend (EXE-05)
- [ ] 08-04-PLAN.md -- Replay comparison and diff viewer frontend components (EXE-01, EXE-02)
- [ ] 08-05-PLAN.md -- Presence, comments, chunk results, and branch navigator frontend components (EXE-03, EXE-04, EXE-05)

**Success Criteria:**

1. Replaying an execution with identical inputs produces a new execution whose output can be viewed side-by-side with the original in a diff view -- output differences are highlighted at the line level
2. Diff-aware context injection extracts only changed files plus N lines of surrounding context from a PR, reducing prompt token count by at least 40% compared to full-file inclusion on a representative test PR
3. Smart chunking splits a large context (>100KB) into semantically meaningful chunks, runs the bot against each independently, and produces a merged/deduplicated result that contains no duplicate findings
4. Conversation branching forks from any message index in an existing transcript, preserving the original thread intact while creating a new branch -- both branches are independently navigable in the UI
5. Live collaborative viewer shows presence indicators for at least 2 simultaneous watchers of the same execution stream, and inline comments posted by one viewer appear in real-time for others

---

### Phase 9: Bot Authoring & Template Ecosystem

**Goal:** Users can discover and deploy pre-built bot templates, create new bots via natural language description, build a shared prompt snippet library, track prompt template history with rollback, and test webhook payloads before committing.

**Dependencies:** None (builds on existing bot CRUD and trigger system)

**Requirements:** TPL-01, TPL-02, TPL-03, TPL-04, TPL-05

**Verification Level:** proxy

**Plans:** 4 plans

Plans:
- [ ] 09-01-PLAN.md -- Bot template marketplace backend + NL bot creator service (TPL-01, TPL-02)
- [ ] 09-02-PLAN.md -- Prompt snippet library + version history enhancement + preview endpoint (TPL-03, TPL-04, TPL-05)
- [ ] 09-03-PLAN.md -- Frontend: template marketplace, NL creator, snippet library views + API clients
- [ ] 09-04-PLAN.md -- Frontend: version history + webhook test console components + backend tests

**Success Criteria:**

1. Template marketplace displays at least 5 curated bot configurations (PR reviewer, dependency updater, security scanner, changelog generator, test writer) and one-click deploy creates a fully configured, runnable bot
2. Natural language bot creator accepts a plain English description and generates a valid bot configuration including trigger rules, prompt template, and model selection -- the generated bot can execute successfully without manual editing
3. Prompt snippet library stores named snippets that are resolvable as variables in any bot prompt -- updating a snippet's content propagates to all bots referencing it on next execution
4. Prompt template version control tracks every edit with author, timestamp, and diff; the version history view shows at least 3 historical versions; one-click rollback restores a previous version and the bot uses the rolled-back prompt on next execution
5. Webhook payload test console accepts a custom JSON payload, renders the prompt template with that payload's variables, and displays the resulting CLI command -- no actual subprocess is spawned

---

### Phase 10: Analytics & Monitoring Dashboards ✅ (2026-03-05)

**Goal:** Users have full visibility into execution costs, bot effectiveness, trend analytics, health alerts, team impact reports, scheduling optimization, and per-bot budget enforcement.

**Dependencies:** None (builds on existing execution history and Chart.js monitoring)

**Requirements:** ANA-01, ANA-02, ANA-03, ANA-04, ANA-05, ANA-06, ANA-07

**Verification Level:** proxy

**Plans:** 5 plans

Plans:
- [x] 10-01-PLAN.md -- Analytics DB queries, service, and API routes (ANA-01, ANA-02, ANA-03)
- [x] 10-02-PLAN.md -- Health monitoring service and weekly team impact reports (ANA-04, ANA-05)
- [x] 10-03-PLAN.md -- Scheduling suggestions and budget enforcement extensions (ANA-06, ANA-07)
- [x] 10-04-PLAN.md -- Analytics frontend dashboards with Chart.js charts (ANA-01, ANA-02, ANA-03)
- [x] 10-05-PLAN.md -- Health, reports, and budget frontend views (ANA-04, ANA-05, ANA-06, ANA-07)

**Success Criteria:**

1. Cost dashboard displays estimated token consumption and cost per bot, per team, and per project with time-series trend charts -- cost data updates within 60 seconds of execution completion
2. Bot effectiveness metric tracks PR suggestion acceptance rate (resolved/changed vs. ignored) per bot over time -- acceptance rate is displayed as a percentage on the bot detail page
3. Execution analytics dashboard renders time-series charts for execution volume, success/failure ratio, average duration, and model usage breakdown -- charts update with real data from at least 10 historical executions
4. Health monitoring detects when a bot fails more than N consecutive times, exceeds 3x average execution time, or has not fired in an unexpectedly long interval, and delivers an alert (at minimum, displayed in-app; optionally via configured channel)
5. Weekly team impact report generates a digest containing PRs reviewed, issues found, estimated time saved, top performing bots, and bots needing attention -- report is viewable in the UI and optionally sent via configured notification channel
6. Smart scheduling suggestions analyze historical execution data and suggest optimal trigger times -- suggestions are displayed on the trigger configuration page
7. Per-bot budget enforcement caps execution time, token usage, and monthly run count -- a bot that hits its limit is gracefully cancelled mid-execution and the owner receives a notification

---

### Phase 11: Enterprise Integrations & Governance

**Goal:** The platform integrates with external collaboration tools (Slack, JIRA), supports configuration-as-code via GitOps, enforces role-based access control, maintains a full audit trail, provides encrypted secrets management, enables multi-repo campaigns, and supports execution bookmarking.

**Dependencies:** None (builds on existing audit logging and webhook infrastructure)

**Requirements:** INT-01, INT-02, INT-03, INT-04, INT-05, INT-06, INT-07, INT-08

**Verification Level:** proxy

**Plans:** 6 plans

Plans:
- [ ] 11-01-PLAN.md -- RBAC decorator with permission matrix and audit trail SQLite persistence
- [ ] 11-02-PLAN.md -- Encrypted secrets vault with Fernet encryption and audit logging
- [ ] 11-03-PLAN.md -- Bot config export/import as YAML/JSON and execution bookmarking
- [ ] 11-04-PLAN.md -- Integration adapter framework with Slack, Teams, JIRA, and Linear adapters
- [ ] 11-05-PLAN.md -- GitOps sync engine with git polling and auto-apply
- [ ] 11-06-PLAN.md -- Multi-repo campaign orchestration and post-execution notification hooks

**Success Criteria:**

1. Slack/Teams integration posts execution result summaries to configured channels within 30 seconds of completion, and a slash command (e.g., `/agented run security-audit on payments-service`) triggers bot execution and returns a confirmation
2. JIRA/Linear integration automatically creates structured tickets from bot findings with severity, context links, and description -- tickets appear in the configured project within 60 seconds of execution completion
3. Bot configuration export produces valid YAML/JSON that, when imported on a clean instance, recreates an identical bot; GitOps sync detects changes in a watched Git repository and applies them automatically
4. RBAC enforces 4 roles (Viewer, Operator, Editor, Admin) -- a Viewer cannot trigger executions, an Operator cannot edit bot configurations, and an Editor cannot manage team membership; verified with at least one permission check per role
5. Audit trail records every configuration change (bots, triggers, teams, agents) with who, what, when, and before/after state -- audit log is queryable by entity, actor, and date range
6. Secret vault stores credentials encrypted at rest, injects them as environment variables at execution time, and audit-logs every access -- credentials are never exposed in API responses or execution logs
7. Multi-repo campaign executes a single bot across at least 3 repositories simultaneously and presents findings in a consolidated view grouped by repository
8. Execution bookmarking pins runs with notes and tags to bot profile pages -- deep-links to specific log lines resolve correctly and are shareable

---

### Phase 12: Specialized Automation Bots

**Goal:** The platform ships pre-built specialized bots for common engineering automation needs: vulnerability triage, code tours, test coverage analysis, incident postmortems, changelog generation, PR summaries, and natural language log search.

**Dependencies:** None (builds on existing bot execution infrastructure; benefits from TPL-01 template marketplace if Phase 9 is completed first, but not required)

**Requirements:** BOT-01, BOT-02, BOT-03, BOT-04, BOT-05, BOT-06, BOT-07

**Verification Level:** proxy

**Plans:** 3 plans

Plans:
- [ ] 12-01-PLAN.md -- Predefined trigger definitions (7 bots), FTS5 schema + sync triggers, ExecutionSearchService + API
- [ ] 12-02-PLAN.md -- Claude skill instruction files for all 7 bots + SpecializedBotService helpers
- [ ] 12-03-PLAN.md -- Specialized bot API routes, frontend API client, ExecutionSearchPage + navigation

**Success Criteria:**

1. Dependency vulnerability bot scans at least one package manifest (package.json, requirements.txt, or Cargo.toml), cross-references against CVE databases, scores exploitability, and produces a prioritized finding list with fix recommendations
2. Code tour generator produces a structured walkthrough (entry points, key abstractions, data flow, gotchas) for a target repository that a new engineer can follow -- output contains at least 5 distinct annotated sections
3. Test coverage gap detector analyzes a PR's changed files, identifies untested functions/branches, and posts specific test case suggestions as PR comments
4. Incident postmortem assistant, given an incident identifier, pulls relevant logs and PR context, and drafts a structured postmortem document with timeline, root cause, impact, and action items sections
5. Changelog bot reads merged PRs since last release, groups them by type (feat/fix/breaking), and generates a formatted CHANGELOG entry or GitHub Release draft
6. PR summary bot posts a concise comment on every PR explaining what changed, why it matters, and what reviewers should focus on -- comment appears within 60 seconds of PR creation/update
7. Natural language log search returns relevant execution results for plain English queries (e.g., "show me all PRs where the bot flagged SQL injection") with highlighted matching context

---

### Phase 13: Execution Resilience & Infrastructure

**Goal:** The execution engine is hardened with circuit breakers, configurable retries, execution queuing, persistent state, pause/resume, cancellation, webhook validation, and durable history -- eliminating the fragility of in-memory-only execution tracking.

**Dependencies:** None (hardens existing execution infrastructure; can run in parallel with product feature phases)

**Requirements:** RES-01, RES-02, RES-03, RES-04, RES-05, RES-06, RES-07, RES-08, RES-09

**Verification Level:** proxy

**Plans:** 4 plans

Plans:
- [ ] 13-01-PLAN.md -- Circuit breaker state machine and transient failure retry mechanism
- [ ] 13-02-PLAN.md -- SQLite-backed execution queue with per-trigger concurrency caps
- [ ] 13-03-PLAN.md -- Pause/resume via SIGSTOP/SIGCONT and bulk cancellation API
- [ ] 13-04-PLAN.md -- Unified webhook validation service and workflow execution analytics

**Success Criteria:**

1. Circuit breaker transitions to OPEN after N consecutive backend failures and fast-fails new requests for the configured cooldown period; it automatically recovers to CLOSED when the backend responds successfully
2. Retry mechanism retries transient failures (502, 503, timeout) up to the configured max-retry cap with the specified backoff curve -- a transient failure followed by a success produces a completed execution without user intervention
3. Execution queue enforces per-bot concurrency caps -- when cap is reached, new executions are queued and dispatched FIFO as capacity frees; queue depth is visible in the admin UI
4. Retry queue is backed by SQLite and survives server restart -- after restart, pending retries resume without data loss; retry queue is browsable in admin UI
5. Pause/resume halts a running execution cleanly and resumes from the paused state without data loss or duplicate output
6. Cancellation API terminates individual executions or bulk-cancels by filter -- cancelled executions are marked with terminal status within 5 seconds
7. Webhook signature validation rejects payloads with invalid HMAC signatures (SHA-256 default) and returns 403; valid signatures pass through to trigger matching
8. Execution state and history are persisted to SQLite -- execution records survive server restart and are queryable for historical analysis with no 5-minute TTL limitation
9. Workflow execution history is persisted to SQLite with per-node status, enabling failure debugging and execution pattern analytics via the admin UI

---

### Phase 14: API Hardening & Developer Experience

**Goal:** Every API endpoint has dry-run support where applicable, returns consistent error responses, supports pagination and filtering, offers bulk operations, enforces rate limits, propagates request IDs for tracing, provides cost estimation, validates workflow DAGs at submission, and supports standard cron expressions.

**Dependencies:** Benefits from Phase 13 error handling patterns (RES-01, RES-02) but not strictly required

**Requirements:** API-01, API-02, API-03, API-04, API-05, API-06, API-07, API-08, API-09, API-10

**Verification Level:** proxy

**Plans:** 4 plans

Plans:
- [ ] 14-01-PLAN.md -- Error response unification, rate limit 429 verification, request ID extension
- [ ] 14-02-PLAN.md -- Universal pagination on all list endpoints and execution filtering
- [ ] 14-03-PLAN.md -- Dry-run dispatch, cost estimation, and cron expression support
- [ ] 14-04-PLAN.md -- Bulk operations for entities and enhanced DAG validation

**Success Criteria:**

1. Dry-run mode for trigger dispatch renders the prompt and shows the CLI command without spawning a subprocess -- response includes rendered prompt, target CLI, and estimated token count
2. All error responses conform to a shared ErrorResponse model with `code`, `message`, and `details` fields -- no endpoint returns a bare string or unstructured error
3. All list endpoints support cursor or offset pagination with configurable page size -- requesting page 2 of a 25-item collection (page_size=10) returns items 11-20 with correct next/previous links
4. Execution list supports filtering by status, trigger_id, date range, and text search over output -- each filter narrows results correctly and filters compose (AND logic)
5. Bulk create/update/delete endpoints process at least 10 entities in a single request and return per-item success/failure status
6. Rate limiting returns 429 Too Many Requests when a client exceeds the configured threshold -- the response includes Retry-After header
7. Request ID middleware attaches a unique ID to every request and propagates it through webhook receipt, trigger match, execution start, and log lines -- grep for a request ID returns the full trace
8. Cost estimation endpoint returns estimated token count and cost for a proposed execution before it runs -- estimate is within 30% of actual for a representative prompt
9. Workflow DAG validation rejects cycles, missing node references, and invalid condition expressions at creation/update time with descriptive error messages
10. Cron expression support parses standard 5-field cron syntax and schedules triggers correctly -- "*/15 9-17 * * 1-5" fires every 15 minutes during business hours on weekdays

---

### Phase 15: Code Consistency & Standards

**Goal:** The backend codebase follows consistent patterns for logging, error handling, return types, ID generation, naming conventions, and configuration constants; the frontend has unified types and composable patterns.

**Dependencies:** None (independent cleanup; can run in parallel with Phase 16)

**Requirements:** CON-01, CON-02, CON-03, CON-04, CON-05, CON-06, CON-07, CON-08, CON-09

**Verification Level:** sanity

**Plans:** 3 plans

Plans:
- [ ] 15-01-PLAN.md -- Backend logging, config constants, and ID factory consolidation (CON-01, CON-04, CON-07)
- [ ] 15-02-PLAN.md -- Frontend type consolidation and useAsyncState composable (CON-08, CON-09)
- [ ] 15-03-PLAN.md -- Route ErrorResponse adoption, DB naming, type annotations, and exception handling (CON-02, CON-03, CON-05, CON-06)

**Success Criteria:**

1. Zero print() calls remain in backend service code -- all output goes through structured logger with appropriate log levels; verified by grep across all .py files in app/
2. All route handlers return errors using the shared ErrorResponse model -- no endpoint returns ad-hoc error dictionaries or bare strings
3. All service and DB methods have return type annotations; DB CRUD follows the convention: create returns str (ID), update returns bool, delete returns bool
4. All entity IDs are generated by a central ID factory using secrets.choice() -- no direct random.choices() calls exist; ID prefix convention is enforced by the factory
5. Exception handling follows documented severity levels with consistent exc_info usage and structured error context across all services
6. DB functions use create_ prefix consistently; service methods use @classmethod or instance methods consistently (not mixed); async patterns are standardized
7. All magic numbers (timeouts, retry limits, alert thresholds, debounce values) are replaced with named constants from a centralized config module
8. Frontend has one canonical message type (no ConversationMessage/ChatMessage/Message duplication); TypeScript `any` usage is reduced to zero across component and service files
9. Frontend composables follow a shared useAsyncState pattern with consistent error/loading lifecycle; SSE setup code exists in one place (no duplication)

---

### Phase 16: Frontend Quality & User Experience

**Goal:** Every async view has loading/error states, the SPA cannot crash from component errors, SSE connections are managed by a shared composable, API errors surface as consistent toast notifications, and developer documentation covers all protocols and formats.

**Dependencies:** None (independent polish; can run in parallel with Phase 15)

**Requirements:** UX-01, UX-02, UX-03, UX-04, UX-05, UX-06, UX-07, UX-08, UX-09

**Verification Level:** sanity

**Plans:** 5 plans

Plans:
- [ ] 16-01-PLAN.md -- ErrorBoundary component, centralized API error handler, and sidebar loading coordination (UX-02, UX-04, UX-06, UX-08)
- [ ] 16-02-PLAN.md -- Shared useEventSource composable and SSE consumer refactoring (UX-03)
- [ ] 16-03-PLAN.md -- Environment validation plugin and OpenAPI documentation completion (UX-07, UX-09)
- [ ] 16-04-PLAN.md -- Unit tests for ErrorBoundary, error-handler, useEventSource, and App error handling (UX-01, UX-05)
- [ ] 16-05-PLAN.md -- Loading state rollout across all async views with handleApiError integration (UX-01)

**Success Criteria:**

1. All async views display skeleton screens or loading indicators during data fetch -- no view shows blank content during loading; sidebar shows coordinated loading state across its 7 concurrent fetches
2. Vue error boundary component catches rendering errors in child components and displays a user-friendly error message with recovery option -- a deliberately thrown error in a child does not crash the entire SPA
3. A single useEventSource composable replaces all duplicated SSE connection setup code in useConversation and useAiChat -- both consumers use the shared composable
4. Centralized API error handler intercepts all fetch failures and displays consistent toast notifications with error code and suggested action -- no silent console.warn on user-visible errors
5. Per-section retry buttons appear on failed API loads and re-fetch only the failed section without requiring a full page refresh
6. Error messages displayed to users include error codes and actionable suggestions (e.g., "Bot not found (ERR-404). Check the bot ID or return to the bots list.") -- no raw exception text is shown
7. OpenAPI documentation covers all endpoint summaries, SSE protocol specs (event types, payload format), prompt placeholder syntax, and workflow input format -- accessible at /docs
8. Sidebar loading state is coordinated -- a unified loading indicator covers all 7 sidebar fetches, transitioning to content only when all have resolved or individually errored
9. Application startup validates required environment variables and fails fast with clear error messages identifying the missing/invalid variable -- no silent fallback to defaults for critical config

---

## Progress

| Phase | Name | Requirements | Status | Verification |
|-------|------|-------------|--------|--------------|
| 7 | Workflow Automation & Pipeline Intelligence | WF-01..WF-06 (6) | Complete (2026-03-04) | proxy |
| 8 | Execution Intelligence & Replay | EXE-01..EXE-05 (5) | Pending | proxy |
| 9 | Bot Authoring & Template Ecosystem | TPL-01..TPL-05 (5) | Pending | proxy |
| 10 | Analytics & Monitoring Dashboards | ANA-01..ANA-07 (7) | Pending | proxy |
| 11 | Enterprise Integrations & Governance | INT-01..INT-08 (8) | Pending | proxy |
| 12 | Specialized Automation Bots | BOT-01..BOT-07 (7) | Pending | proxy |
| 13 | Execution Resilience & Infrastructure | RES-01..RES-09 (9) | Pending | proxy |
| 14 | API Hardening & Developer Experience | API-01..API-10 (10) | Pending | proxy |
| 15 | Code Consistency & Standards | CON-01..CON-09 (9) | Pending | sanity |
| 16 | Frontend Quality & User Experience | UX-01..UX-09 (9) | Pending | sanity |

**Total:** 10 phases, 89 requirements, 10% complete (1/10 phases)

---

## Coverage Map

```
WF-01  -> Phase 7     WF-02  -> Phase 7     WF-03  -> Phase 7
WF-04  -> Phase 7     WF-05  -> Phase 7     WF-06  -> Phase 7
EXE-01 -> Phase 8     EXE-02 -> Phase 8     EXE-03 -> Phase 8
EXE-04 -> Phase 8     EXE-05 -> Phase 8
TPL-01 -> Phase 9     TPL-02 -> Phase 9     TPL-03 -> Phase 9
TPL-04 -> Phase 9     TPL-05 -> Phase 9
ANA-01 -> Phase 10    ANA-02 -> Phase 10    ANA-03 -> Phase 10
ANA-04 -> Phase 10    ANA-05 -> Phase 10    ANA-06 -> Phase 10
ANA-07 -> Phase 10
INT-01 -> Phase 11    INT-02 -> Phase 11    INT-03 -> Phase 11
INT-04 -> Phase 11    INT-05 -> Phase 11    INT-06 -> Phase 11
INT-07 -> Phase 11    INT-08 -> Phase 11
BOT-01 -> Phase 12    BOT-02 -> Phase 12    BOT-03 -> Phase 12
BOT-04 -> Phase 12    BOT-05 -> Phase 12    BOT-06 -> Phase 12
BOT-07 -> Phase 12
RES-01 -> Phase 13    RES-02 -> Phase 13    RES-03 -> Phase 13
RES-04 -> Phase 13    RES-05 -> Phase 13    RES-06 -> Phase 13
RES-07 -> Phase 13    RES-08 -> Phase 13    RES-09 -> Phase 13
API-01 -> Phase 14    API-02 -> Phase 14    API-03 -> Phase 14
API-04 -> Phase 14    API-05 -> Phase 14    API-06 -> Phase 14
API-07 -> Phase 14    API-08 -> Phase 14    API-09 -> Phase 14
API-10 -> Phase 14
CON-01 -> Phase 15    CON-02 -> Phase 15    CON-03 -> Phase 15
CON-04 -> Phase 15    CON-05 -> Phase 15    CON-06 -> Phase 15
CON-07 -> Phase 15    CON-08 -> Phase 15    CON-09 -> Phase 15
UX-01  -> Phase 16    UX-02  -> Phase 16    UX-03  -> Phase 16
UX-04  -> Phase 16    UX-05  -> Phase 16    UX-06  -> Phase 16
UX-07  -> Phase 16    UX-08  -> Phase 16    UX-09  -> Phase 16

Mapped: 89/89. No orphaned requirements.
```

---

## Dependency Graph

```
Priority Tier 1 (Product-Ideation Features):
  Phase 7  --|
  Phase 8  --|
  Phase 9  --|--> All independent, can execute in any order
  Phase 10 --|
  Phase 11 --|
  Phase 12 --|    (Phase 12 benefits from Phase 9 TPL-01 but not required)

Priority Tier 2 (Infrastructure):
  Phase 13 --> Can run in parallel with Tier 1
  Phase 14 --> Benefits from Phase 13 error patterns (soft dependency)

Priority Tier 3 (Quality):
  Phase 15 --|
  Phase 16 --|--> Independent of each other, can run in parallel
```

---
*Generated: 2026-03-04*
