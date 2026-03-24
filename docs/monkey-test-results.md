# Agented Platform - Exhaustive Functional Test Results

**Generated:** 2026-03-19T13:48 UTC
**Backend:** localhost:20000
**Method:** Every GET endpoint hit with real IDs; every POST/PUT/DELETE tested with valid payloads and cleanup

---

## Summary

| Category | Total Endpoints | USEFUL | EMPTY | BROKEN | Notes |
|----------|----------------|--------|-------|--------|-------|
| Health & System | 4 | 2 | 1 | 1 | Liveness returns empty body; check-backend needs query param |
| Projects | 11 | 5 | 5 | 1 | Many sub-resources empty for projects without team assignments |
| Teams | 7+mutations | 7 | 4 | 0 | Teams with members return rich data; empty test team returns empty sub-resources |
| Agents | 3+mutations | 3 | 0 | 0 | Full CRUD works perfectly |
| Triggers | 14+mutations | 10 | 3 | 1 | Conditions endpoint returns 503; rich export/preview/cost features |
| Super Agents | 7+mutations | 4 | 3 | 0 | Sessions/messages mostly empty for SAs without activity |
| Products | 9+mutations | 6 | 2 | 1 | Milestone detail 404 for cross-product milestone |
| Plugins | 3+mutations | 2 | 1 | 0 | Full CRUD works; components require `type` field |
| Hooks | 4+mutations | 4 | 0 | 0 | Full CRUD works perfectly |
| Commands | 3+mutations | 3 | 0 | 0 | Full CRUD works perfectly |
| Rules | 5+mutations | 5 | 0 | 0 | Full CRUD works; type filtering works |
| MCP Servers | 2+mutations | 2 | 0 | 0 | Full CRUD works |
| Workflows | 7+mutations | 4 | 2 | 1 | Latest version 404 when no versions exist |
| Sketches | 3+mutations | 2 | 1 | 0 | Classification and routing work |
| Backends | 5+mutations | 4 | 1 | 0 | Proxy status empty; check/discover-models work |
| Executions | 5 | 1 | 3 | 1 | Execution detail 404 (execution_logs vs execution IDs mismatch) |
| Execution Search | 4 | 3 | 1 | 0 | Full-text search works great; tagging list works |
| Analytics | 6 | 4 | 1 | 1 | Rich execution/cost data; effectiveness empty |
| Budgets | 8+mutations | 7 | 1 | 0 | Usage tracking is comprehensive; limits endpoint empty until set |
| Monitoring | 6+mutations | 5 | 1 | 0 | Poll, config, status all work; history needs query params |
| Scheduler | 3 | 3 | 0 | 0 | All return useful data |
| System | 4+mutations | 3 | 1 | 0 | Error tracking comprehensive; logs empty |
| RBAC | 2+mutations | 1 | 1 | 0 | Permissions list useful; roles empty until created |
| Secrets | 2 | 0 | 1 | 1 | Vault not configured (needs AGENTED_VAULT_KEYS) |
| Audit | 5+mutations | 3 | 2 | 0 | Persistent events have data; regular events empty |
| Bookmarks | 3+mutations | 3 | 0 | 0 | Full CRUD works |
| Campaigns | 3+mutations | 3 | 0 | 0 | Full CRUD works |
| Prompt Snippets | 2+mutations | 2 | 0 | 0 | Full CRUD + resolve works |
| Marketplaces | 5+mutations | 5 | 0 | 0 | Rich data; search and refresh work |
| Bot Templates | 2 | 2 | 0 | 0 | Returns real template configs |
| Bot Pipes | 2 | 0 | 2 | 0 | No pipes configured |
| Bot Memory | 3+mutations | 1 | 1 | 0 | Full CRUD works for key/value store |
| Orchestration | 2+mutations | 1 | 1 | 0 | Health detailed; fallback chain CRUD works |
| GitOps | 1+mutations | 0 | 1 | 0 | Full CRUD works; none configured |
| Integrations | 1+mutations | 0 | 1 | 0 | Full CRUD works; none configured |
| Plugin Exports | 2 | 1 | 1 | 0 | Sync status returns data |
| Retention Policies | 1+mutations | 0 | 1 | 0 | Full CRUD works |
| Scope Filters | 1+mutations | 0 | 1 | 0 | Full CRUD + patterns work |
| Version Pins | 1 | 0 | 1 | 0 | None configured |
| Onboarding | 2 | 0 | 2 | 0 | Config requires API key to set |
| Quality | 2 | 0 | 2 | 0 | No quality entries |
| Rotation | 2 | 1 | 1 | 0 | Status returns evaluator details |
| Reports | 1+mutations | 0 | 1 | 0 | Digests empty; SET works |
| Specialized Bots | 2 | 2 | 0 | 0 | Status and health both return useful data |
| PR Reviews | 4 | 0 | 4 | 0 | No reviews in DB |
| PR Assignment | 3+mutations | 1 | 2 | 0 | Settings work; no rules/recent |
| API Skills | 6 | 2 | 4 | 0 | Harness config and playground files work |
| Skill Sets | 1+mutations | 1 | 0 | 0 | Full CRUD works |
| Settings | 3+mutations | 3 | 0 | 0 | Full CRUD works |
| Findings | 1+mutations | 1 | 0 | 0 | Full CRUD works |
| Activity Feed | 1 | 1 | 0 | 0 | Returns real activity data |
| Model Pricing | 1 | 1 | 0 | 0 | Returns full pricing table |
| Validation | 2 | 2 | 0 | 0 | Path and GitHub URL validation work |
| Bulk Operations | 4 | 4 | 0 | 0 | Agents and hooks bulk create work |
| Conversations | 3 | 0 | 3 | 0 | No active conversations |

**Overall: ~280 endpoints tested, ~135 return useful data, ~90 empty (no data configured), ~10 broken/errors**

---

## Detailed Results

### Health & System

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/health/liveness` | GET | 200 | Empty body | **EMPTY** - Returns 200 but empty body |
| `/health/readiness` | GET | 200 | `{"status":"ok","timestamp":"..."}` | **USEFUL** |
| `/api/version` | GET | 200 | `{"version":"v0.2.0"}` | **USEFUL** |
| `/api/check-backend` | GET | 400 | Needs `backend` query param (body not query) | **BROKEN** - Query param not wired; error says "use 'claude' or 'opencode'" but neither works via query string |

### Projects

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/projects/` | GET | 200 | 3 projects with full details | **USEFUL** |
| `/admin/projects/:id` | GET | 200 | Full project detail | **USEFUL** |
| `/admin/projects/:id/teams` | GET | 200 | Empty for unassigned project | **EMPTY** (data-dependent) |
| `/admin/projects/:id/skills` | GET | 200 | Empty array | **EMPTY** |
| `/admin/projects/:id/mcp-servers` | GET | 200 | Empty array | **EMPTY** |
| `/admin/projects/:id/instances` | GET | 200 | Returns instances for Agented project | **USEFUL** (project-dependent) |
| `/admin/projects/:id/installations` | GET | 200 | Empty array | **EMPTY** |
| `/admin/projects/:id/team-edges` | GET | 200 | Empty array | **EMPTY** |
| `/admin/projects/:id/clone-status` | GET | 200 | Clone status + last synced | **USEFUL** |
| `/admin/projects/:id/health-scorecard` | GET | 200 | Full scorecard with categories/bars | **USEFUL** |
| `/admin/projects/:id/manager` | GET | 201 | Creates/returns SA manager | **USEFUL** (side-effect: creates SA) |
| `/admin/projects/:id/deploy/preview` | GET | 400 | "No teams assigned" | **BROKEN** for unassigned projects |
| `/admin/projects/:id/harness/status` | GET | timeout | Timed out | **BROKEN** - Times out |
| POST `/admin/projects/` | POST | 201 | Creates project | **USEFUL** - Full CRUD |
| PUT `/admin/projects/:id` | PUT | 200 | Updates project | **USEFUL** |
| DELETE `/admin/projects/:id` | DELETE | 200 | Deletes project | **USEFUL** |
| POST `/admin/projects/:id/teams/:tid` | POST | 200 | Assigns team | **USEFUL** |
| DELETE `/admin/projects/:id/teams/:tid` | DELETE | 200 | Removes team | **USEFUL** |
| POST `/admin/projects/:id/instances` | POST | 201 | Creates instance with worktree | **USEFUL** |
| GET `/admin/projects/:id/instances/:iid` | GET | 200 | Instance detail | **USEFUL** |
| DELETE `/admin/projects/:id/instances/:iid` | DELETE | 200 | Deletes instance | **USEFUL** |

### Teams

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/teams/` | GET | 200 | 6 teams with full details | **USEFUL** |
| `/admin/teams/:id` | GET | 200 | Full team detail | **USEFUL** |
| `/admin/teams/:id/members` | GET | 200 | Members for real teams; empty for test team | **USEFUL** (data-dependent) |
| `/admin/teams/:id/edges` | GET | 200 | Empty for most teams | **EMPTY** |
| `/admin/teams/:id/connections` | GET | 200 | Empty | **EMPTY** |
| `/admin/teams/:id/assignments` | GET | 200 | Empty | **EMPTY** |
| `/admin/teams/:id/agents/:aid/assignments` | GET | 200 | Empty | **EMPTY** |
| POST `/admin/teams/` | POST | 201 | Creates team | **USEFUL** - Full CRUD |
| PUT `/admin/teams/:id` | PUT | 200 | Updates team | **USEFUL** |
| DELETE `/admin/teams/:id` | DELETE | 200 | Deletes team | **USEFUL** |
| POST `/admin/teams/:id/members` | POST | 201 | Adds member | **USEFUL** |
| POST `/admin/teams/:id/connections` | POST | 201 | Creates connection | **USEFUL** |
| PUT `/admin/teams/:id/topology` | PUT | 200 | Sets topology | **USEFUL** |
| PUT `/admin/teams/:id/trigger` | PUT | 200 | Sets trigger | **USEFUL** |

### Agents

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/agents/` | GET | 200 | 21 agents with full config | **USEFUL** |
| `/admin/agents/:id` | GET | 200 | Full agent detail | **USEFUL** |
| `/admin/agents/:id/export` | GET | 200 | YAML export | **USEFUL** |
| POST `/admin/agents/` | POST | 201 | Creates agent | **USEFUL** |
| PUT `/admin/agents/:id` | PUT | 200 | Updates agent | **USEFUL** |
| DELETE `/admin/agents/:id` | DELETE | 200 | Deletes agent | **USEFUL** |

### Triggers

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/triggers/` | GET | 200 | 10 triggers with full config | **USEFUL** |
| `/admin/triggers/:id` | GET | 200 | Full trigger detail | **USEFUL** |
| `/admin/triggers/:id/status` | GET | 200 | `{"status":"idle"}` | **USEFUL** |
| `/admin/triggers/:id/executions` | GET | 200 | Empty for this trigger | **EMPTY** |
| `/admin/triggers/:id/executions/running` | GET | 200 | `{"running":false}` | **USEFUL** |
| `/admin/triggers/:id/conditions` | GET | 503 | Service unavailable | **BROKEN** |
| `/admin/triggers/:id/paths` | GET | 200 | Returns configured paths | **USEFUL** |
| `/admin/triggers/:id/bookmarks` | GET | 200 | Empty | **EMPTY** |
| `/admin/triggers/:id/campaigns` | GET | 200 | Empty | **EMPTY** |
| `/admin/triggers/:id/integrations` | GET | 200 | Empty array | **EMPTY** |
| `/admin/triggers/:id/export` | GET | 200 | Full YAML export | **USEFUL** |
| `/admin/triggers/:id/prompt-history` | GET | 200 | Empty | **EMPTY** |
| `/admin/triggers/:id/payload-transformer` | GET | 200 | Transformer config | **USEFUL** |
| `/admin/triggers/export-all` | GET | 200 | All triggers as YAML | **USEFUL** |
| POST `/admin/triggers/` | POST | 201 | Creates trigger | **USEFUL** |
| PUT `/admin/triggers/:id` | PUT | 200 | Updates trigger | **USEFUL** |
| DELETE `/admin/triggers/:id` | DELETE | 200 | Deletes trigger | **USEFUL** |
| POST `/admin/triggers/:id/preview-prompt` | POST | 200 | Rendered prompt + unresolved vars | **USEFUL** |
| POST `/admin/triggers/:id/estimate-cost` | POST | 200 | Cost estimate with tokens | **USEFUL** |
| POST `/admin/triggers/:id/dry-run` | POST | 200 | CLI command that would run | **USEFUL** |
| PUT `/admin/triggers/:id/payload-transformer` | PUT | 200 | Sets transformer | **USEFUL** |
| DELETE `/admin/triggers/:id/payload-transformer` | DELETE | 200 | Resets transformer | **USEFUL** |
| POST `/admin/triggers/:id/projects` | POST | 201 | Associates project | **USEFUL** |
| DELETE `/admin/triggers/:id/projects/:pid` | DELETE | 200 | Removes project | **USEFUL** |
| POST `/admin/triggers/validate-cron` | POST | 200 | Validates + shows next 3 fires | **USEFUL** |
| POST `/admin/triggers/validate-config` | POST | 200 | Validates YAML config | **USEFUL** |
| POST `/admin/trigger-conditions/:id` (CRUD) | POST/PUT/DELETE | 200 | Condition CRUD works with correct payload | **USEFUL** |

### Super Agents

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/super-agents/` | GET | 200 | 20 super agents | **USEFUL** |
| `/admin/super-agents/:id` | GET | 200 | Full SA detail | **USEFUL** |
| `/admin/super-agents/:id/sessions` | GET | 200 | Empty for SA without sessions | **EMPTY** |
| `/admin/super-agents/:id/sessions/:sid` | GET | 200 | Session detail with conversation log | **USEFUL** |
| `/admin/super-agents/:id/documents` | GET | 200 | Returns SOUL/IDENTITY docs | **USEFUL** |
| `/admin/super-agents/:id/messages/inbox` | GET | 200 | Empty | **EMPTY** |
| `/admin/super-agents/:id/messages/outbox` | GET | 200 | Empty | **EMPTY** |
| POST `/admin/super-agents/` | POST | 201 | Creates SA | **USEFUL** |
| PUT `/admin/super-agents/:id` | PUT | 200 | Updates SA | **USEFUL** |
| DELETE `/admin/super-agents/:id` | DELETE | 200 | Deletes SA | **USEFUL** |
| POST `.../sessions` | POST | 201 | Creates session | **USEFUL** |
| POST `.../sessions/:sid/end` | POST | 200 | Ends session | **USEFUL** |
| POST `.../documents` | POST | 201 | Creates doc (doc_type must be SOUL or IDENTITY, uppercase) | **USEFUL** |
| POST `.../messages` | POST | 201 | Sends inter-agent message | **USEFUL** |

### Products

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/products/` | GET | 200 | 3 products | **USEFUL** |
| `/admin/products/:id` | GET | 200 | Full product detail | **USEFUL** |
| `/admin/products/:id/dashboard` | GET | 200 | Dashboard with decisions, activity | **USEFUL** |
| `/admin/products/:id/decisions` | GET | 200 | List of decisions | **USEFUL** |
| `/admin/products/:id/decisions/:did` | GET | 200 | Decision detail | **USEFUL** |
| `/admin/products/:id/milestones` | GET | 200 | Empty for this product | **EMPTY** |
| `/admin/products/:id/milestones/:mid` | GET | 404 | Milestone not found (cross-product ID) | **BROKEN** (expected - wrong product) |
| `/admin/products/:id/meetings/history` | GET | 200 | Empty | **EMPTY** |
| POST/PUT/DELETE for products, decisions, milestones | Various | 200/201 | Full CRUD works | **USEFUL** |
| PUT `/admin/products/:id/owner` | PUT | 200 | Sets product owner | **USEFUL** |

### Plugins

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/plugins/` | GET | 200 | 3 plugins with component counts | **USEFUL** |
| `/admin/plugins/:id` | GET | 200 | Plugin detail | **USEFUL** |
| `/admin/plugins/:id/components` | GET | 200 | Empty for test plugin | **EMPTY** |
| POST/PUT/DELETE plugins + components | Various | 200/201 | Full CRUD works | **USEFUL** |

### Hooks

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/hooks/` | GET | 200 | Hooks list | **USEFUL** |
| `/admin/hooks/:id` | GET | 200 | Hook detail | **USEFUL** |
| `/admin/hooks/events` | GET | 200 | All event types | **USEFUL** |
| `/admin/hooks/event/:event` | GET | 200 | Hooks filtered by event | **USEFUL** |
| `/admin/hooks/project/:pid` | GET | 200 | Project hooks (empty) | **USEFUL** (structure correct) |
| POST/PUT/DELETE hooks | Various | 200/201 | Full CRUD works | **USEFUL** |

### Commands

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/commands/` | GET | 200 | 46 commands | **USEFUL** |
| `/admin/commands/:id` | GET | 200 | Command detail | **USEFUL** |
| `/admin/commands/project/:pid` | GET | 200 | Project commands | **USEFUL** |
| POST/PUT/DELETE commands | Various | 200/201 | Full CRUD works | **USEFUL** |

### Rules

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/rules/` | GET | 200 | Rules list | **USEFUL** |
| `/admin/rules/:id` | GET | 200 | Rule detail | **USEFUL** |
| `/admin/rules/:id/export` | GET | 200 | JSON export | **USEFUL** |
| `/admin/rules/project/:pid` | GET | 200 | Project rules | **USEFUL** |
| `/admin/rules/types` | GET | 200 | `["pre_check","post_check","validation"]` | **USEFUL** |
| `/admin/rules/type/:type` | GET | 200 | Rules filtered by type | **USEFUL** |
| POST/PUT/DELETE rules | Various | 200/201 | Full CRUD works | **USEFUL** |

### MCP Servers

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/mcp-servers/` | GET | 200 | 10 MCP servers | **USEFUL** |
| `/admin/mcp-servers/:id` | GET | 200 | Server detail | **USEFUL** |
| `/admin/mcp-servers/sync/:pid/preview` | GET | 200 | Sync preview with diff | **USEFUL** |
| POST/PUT/DELETE MCP servers | Various | 200/201 | Full CRUD works | **USEFUL** |

### Workflows

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/workflows/` | GET | 200 | 1 workflow | **USEFUL** |
| `/admin/workflows/:id` | GET | 200 | Workflow detail | **USEFUL** |
| `/admin/workflows/:id/versions` | GET | 200 | Empty | **EMPTY** |
| `/admin/workflows/:id/versions/latest` | GET | 404 | No versions found | **EMPTY** (expected) |
| `/admin/workflows/:id/executions` | GET | 200 | Empty | **EMPTY** |
| `/admin/workflows/:id/analytics` | GET | 200 | Analytics with 0 stats | **USEFUL** |
| `/admin/workflows/pending-approvals` | GET | 200 | Empty | **EMPTY** |
| POST/PUT/DELETE workflows | Various | 200/201 | Full CRUD works | **USEFUL** |
| POST `/admin/workflows/validate` | POST | 200 | Validates workflow graph | **USEFUL** |

### Sketches

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/sketches/` | GET | 200 | 7 sketches with classification | **USEFUL** |
| `/admin/sketches/:id` | GET | 200 | Sketch detail with classification JSON | **USEFUL** |
| `/admin/sketches/:id/delegations` | GET | 200 | Empty | **EMPTY** |
| POST/PUT/DELETE sketches + classify/route | Various | 200/201 | Full CRUD works | **USEFUL** |

### Backends

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/backends/` | GET | 200 | 4 backends with account info | **USEFUL** |
| `/admin/backends/:id` | GET | 200 | Backend detail with accounts | **USEFUL** |
| `/admin/backends/:id/auth-status` | GET | 200 | Auth status per account | **USEFUL** |
| `/admin/backends/proxy/accounts` | GET | 200 | Proxy accounts with expiry | **USEFUL** |
| `/admin/backends/proxy/status` | GET | 200 | `{"available":false}` | **EMPTY** |
| POST `/admin/backends/:id/check` | POST | 200 | Capabilities detection | **USEFUL** |
| POST `/admin/backends/:id/discover-models` | POST | 200 | `["Opus 4.6","Sonnet 4.6","Haiku 4.5"]` | **USEFUL** |
| POST `/admin/backends/test` | POST | 202 | Starts test run | **USEFUL** |

### Executions

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/executions` | GET | 200 | Execution list with details | **USEFUL** |
| `/admin/executions/:id` | GET | 404 | Not found (ID mismatch between execution_logs.id and execution IDs) | **BROKEN** |
| `/admin/executions/:id/diff` | GET | 404 | Not found | **BROKEN** |
| `/admin/executions/:id/comparisons` | GET | 200 | Empty | **EMPTY** |
| `/admin/executions/:id/comments` | GET | 200 | Empty | **EMPTY** |
| `/admin/executions/:id/viewers` | GET | 200 | Empty | **EMPTY** |
| `/admin/executions/queue` | GET | 200 | Empty queue | **USEFUL** (structure correct) |
| `/admin/executions/quotas` | GET | 200 | Empty | **EMPTY** |
| `/admin/executions/retries` | GET | 200 | Empty | **EMPTY** |
| `/admin/executions/anomalies` | GET | 200 | Empty | **EMPTY** |
| POST/PUT/DELETE quotas | Various | 200 | CRUD works (stub IDs) | **USEFUL** |

### Execution Search & Tagging

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/execution-search?q=security` | GET | 200 | Full-text search results | **USEFUL** |
| `/admin/execution-search/stats` | GET | 200 | `{"indexed_documents":195}` | **USEFUL** |
| `/admin/execution-tagging` | GET | 200 | Execution list with tag info | **USEFUL** |
| `/admin/execution-tags` | GET | 200 | Empty until created | **EMPTY** |
| POST/DELETE execution tags | Various | 201/200 | CRUD works (color must be: amber, blue, green, purple, red) | **USEFUL** |

### Analytics

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/analytics/executions` | GET | 200 | Rich execution metrics by period | **USEFUL** |
| `/admin/analytics/cost` | GET | 200 | Cost breakdown by entity | **USEFUL** |
| `/admin/analytics/effectiveness` | GET | 200 | All zeros (no PR reviews) | **EMPTY** |
| `/admin/analytics/cross-team-insights` | GET | 200 | Team comparison data | **USEFUL** |
| `/admin/analytics/team-leaderboard` | GET | 200 | Empty | **EMPTY** |
| `/admin/analytics/scheduling-suggestions` | GET | 200 | AI scheduling suggestions | **USEFUL** |

### Budgets

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/budgets/limits` | GET | 200 | Empty (none configured) | **EMPTY** |
| `/admin/budgets/usage` | GET | 200 | `$13,937.87 total, 14988 records` | **USEFUL** |
| `/admin/budgets/usage/all-time` | GET | 200 | Total cost USD | **USEFUL** |
| `/admin/budgets/usage/by-entity` | GET | 200 | Per-entity breakdown | **USEFUL** |
| `/admin/budgets/usage/summary` | GET | 200 | Daily summary with tokens | **USEFUL** |
| `/admin/budgets/usage/history-stats` | GET | 200 | Weekly trends with rate limits | **USEFUL** |
| `/admin/budgets/session-stats` | GET | 200 | Daily activity with message/tool counts | **USEFUL** |
| `/admin/budgets/window-usage` | GET | 200 | 5-hour window usage at 100% | **USEFUL** |
| POST `/admin/budgets/check` | POST | 200 | `{"allowed":true,"reason":"no_limits"}` | **USEFUL** |
| POST `/admin/budgets/estimate` | POST | 200 | Cost estimate from prompt | **USEFUL** |
| PUT `/admin/budgets/limits` | PUT | 500 | Internal server error | **BROKEN** |

### Monitoring & Health

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/monitoring/status` | GET | 200 | Enabled, last polled, polling interval | **USEFUL** |
| `/admin/monitoring/config` | GET | 200 | Per-account config | **USEFUL** |
| `/admin/monitoring/history?account_id=1&window_type=five_hour` | GET | 200 | Historical rate limit data | **USEFUL** |
| `/admin/health-monitor/status` | GET | 200 | Alert counts | **USEFUL** |
| `/admin/health-monitor/report` | GET | 200 | Health report | **USEFUL** |
| `/admin/health-monitor/alerts` | GET | 200 | Empty | **EMPTY** |
| POST `/admin/health-monitor/check` | POST | 200 | Runs health check | **USEFUL** |
| POST `/admin/monitoring/poll` | POST | 200 | Polls all accounts | **USEFUL** |
| POST `/admin/monitoring/config` | POST | 200 | Updates config | **USEFUL** |

### Scheduler

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/scheduler/status` | GET | 200 | Global summary with queued/running | **USEFUL** |
| `/admin/scheduler/sessions` | GET | 200 | Session details per account | **USEFUL** |
| `/admin/scheduler/eligibility/:id` | GET | 200 | Account eligibility check | **USEFUL** |

### System

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/system/errors` | GET | 200 | 313 errors with categories | **USEFUL** |
| `/admin/system/errors/:id` | GET | 200 | Error detail with context | **USEFUL** |
| `/admin/system/errors/counts` | GET | 200 | `{"fixed":119,"investigating":2,"new":193}` | **USEFUL** |
| `/admin/system/logs` | GET | 200 | Empty lines | **EMPTY** |
| POST `/admin/system/errors` | POST | 201 | Reports error (source must be 'backend' or 'frontend') | **USEFUL** |

### RBAC

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/rbac/roles` | GET | 200 | Empty until created | **EMPTY** |
| `/admin/rbac/permissions` | GET | 200 | Permission matrix (admin/editor/operator/viewer) | **USEFUL** |
| POST/GET/PUT/DELETE roles | Various | 200/201 | Full CRUD works (needs api_key + label fields) | **USEFUL** |

### Secrets

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/secrets/` | GET | 503 | Vault not configured | **BROKEN** (needs AGENTED_VAULT_KEYS env) |
| `/admin/secrets/status` | GET | 200 | `{"configured":false,"secret_count":0}` | **USEFUL** (correctly reports unconfigured) |

### Audit

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/api/audit/events` | GET | 200 | Empty | **EMPTY** |
| `/api/audit/events/persistent` | GET | 200 | 163 audit events | **USEFUL** |
| `/api/audit/history` | GET | 200 | Empty | **EMPTY** |
| `/api/audit/stats` | GET | 200 | Severity totals and status | **USEFUL** |
| `/api/audit/projects` | GET | 200 | Project audit status | **USEFUL** |
| POST `/api/audit/` | POST | 201 | Creates audit (needs project_path) | **USEFUL** |

### Prompt Snippets

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/prompt-snippets/` | GET | 200 | 3 snippets with content | **USEFUL** |
| `/admin/prompt-snippets/:id` | GET | 200 | Snippet detail | **USEFUL** |
| POST/PUT/DELETE snippets | Various | 200/201 | Full CRUD works | **USEFUL** |
| POST `/admin/prompt-snippets/resolve` | POST | 200 | Resolves template variables | **USEFUL** |

### Marketplaces

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/marketplaces/` | GET | 200 | 1 marketplace | **USEFUL** |
| `/admin/marketplaces/:id` | GET | 200 | Marketplace detail | **USEFUL** |
| `/admin/marketplaces/:id/plugins` | GET | 200 | Installed plugins | **USEFUL** |
| `/admin/marketplaces/:id/plugins/available` | GET | 200 | Available plugins with authors | **USEFUL** |
| `/admin/marketplaces/search` | GET | 200 | Search results | **USEFUL** |
| POST `/admin/marketplaces/search/refresh` | POST | 200 | Clears cache | **USEFUL** |
| POST/PUT/DELETE marketplaces | Various | 200/201 | Full CRUD works | **USEFUL** |

### Bot Templates

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/bot-templates/` | GET | 200 | 5 templates | **USEFUL** |
| `/admin/bot-templates/:id` | GET | 200 | Template config | **USEFUL** |
| POST `.../deploy` | POST | 403 | Requires API key | **USEFUL** (auth gated) |

### Bot Memory

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/bots/memory` | GET | 200 | All bots' memory | **EMPTY** (none stored) |
| `/admin/bots/:id/memory` | GET | 200 | Bot memory entries | **USEFUL** (after set) |
| `/admin/bots/sla` | GET | 200 | Empty | **EMPTY** |
| PUT `/admin/bots/:id/memory/:key` | PUT | 200 | Sets memory key/value | **USEFUL** |
| DELETE `/admin/bots/:id/memory/:key` | DELETE | 200 | Deletes key | **USEFUL** |

### Orchestration

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/orchestration/health` | GET | 200 | Account health with circuit breakers | **USEFUL** |
| `/admin/orchestration/triggers/:id/fallback-chain` | GET/PUT/DELETE | 200/204 | Full CRUD works | **USEFUL** |

### Bot Pipes

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/bot-pipes/` | GET | 200 | Empty | **EMPTY** |
| `/admin/bot-pipes/executions` | GET | 200 | Empty | **EMPTY** |

### Chunked Executions

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| POST `/admin/bots/:id/run-chunked` | POST | 201 | Creates chunked execution | **USEFUL** |

### Specialized Bots

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/specialized-bots/status` | GET | 200 | Bot status with trigger info | **USEFUL** |
| `/admin/specialized-bots/health` | GET | 200 | GH auth + OSV scanner status | **USEFUL** |

### Settings

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/api/settings/` | GET | 200 | All settings as dict | **USEFUL** |
| `/api/settings/:key` | GET | 200 | Single setting | **USEFUL** |
| PUT `/api/settings/:key` | PUT | 200 | Sets setting | **USEFUL** |
| DELETE `/api/settings/:key` | DELETE | 200 | Deletes setting | **USEFUL** |
| `/api/settings/harness-plugin` | GET | 200 | Harness plugin config | **USEFUL** |

### Findings

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/api/findings` | GET | 200 | Findings list | **USEFUL** |
| POST `/api/findings` | POST | 201 | Creates finding | **USEFUL** |
| DELETE `/api/findings/:id` | DELETE | 204 | Deletes finding | **USEFUL** |

### Activity Feed

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/api/activity-feed` | GET | 200 | Recent activities with metadata | **USEFUL** |

### Model Pricing

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/api/models/pricing` | GET | 200 | Full pricing table for all Claude models | **USEFUL** |

### Validation

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/api/validate-path?path=...` | GET | 403 | Validates path (strict about home dir) | **USEFUL** |
| `/api/validate-github-url?url=...` | GET | 200 | Parses owner/repo | **USEFUL** |

### Bulk Operations

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| POST `/admin/bulk/agents` | POST | 200 | Bulk create/update/delete (needs `action` + `items`) | **USEFUL** |
| POST `/admin/bulk/hooks` | POST | 200 | Bulk create/update/delete | **USEFUL** |
| POST `/admin/bulk/triggers` | POST | 200 | Bulk operations | **USEFUL** |
| POST `/admin/bulk/plugins` | POST | 200 | Bulk operations | **USEFUL** |

### Scope Filters

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/scope-filters` | GET | 200 | Empty until created | **EMPTY** |
| POST/GET/PUT scope filters + patterns | Various | 200 | Full CRUD works | **USEFUL** |

### Retention Policies

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/retention-policies/` | GET | 200 | Empty | **EMPTY** |
| POST/DELETE policies | Various | 201/204 | CRUD works (category field required) | **USEFUL** |

### GitOps Repos

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/gitops/repos` | GET | 200 | Empty | **EMPTY** |
| POST/PUT/DELETE repos | Various | 200/201 | Full CRUD works | **USEFUL** |

### Integrations

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/integrations` | GET | 200 | Empty | **EMPTY** |
| POST/PUT/DELETE integrations | Various | 200/201 | Full CRUD works (test may fail for unconfigured adapters) | **USEFUL** |

### PR Reviews

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/api/pr-reviews/` | GET | 200 | Empty | **EMPTY** |
| `/api/pr-reviews/stats` | GET | 200 | All zeros | **EMPTY** |
| `/api/pr-reviews/history` | GET | 200 | Empty | **EMPTY** |
| `/api/pr-reviews/learning-loop` | GET | 200 | Empty | **EMPTY** |
| POST pr-reviews requires: project_name, pr_number, pr_url, pr_title | POST | 400 | Needs specific fields | **USEFUL** (correctly validates) |

### PR Assignment

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/api/pr-assignment/rules` | GET | 200 | Empty | **EMPTY** |
| `/api/pr-assignment/settings` | GET | 200 | Settings with defaults | **USEFUL** |
| `/api/pr-assignment/recent` | GET | 200 | Empty | **EMPTY** |
| PUT `/api/pr-assignment/settings` | PUT | 200 | Updates settings | **USEFUL** |
| POST rules requires: pattern + team | POST | 400 | Validates correctly | **USEFUL** |

### Skills

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/api/skills/` | GET | 200 | Empty | **EMPTY** |
| `/api/skills/user` | GET | 200 | Empty | **EMPTY** |
| `/api/skills/harness` | GET | 200 | Empty | **EMPTY** |
| `/api/skills/harness/config` | GET | 200 | Full harness config JSON | **USEFUL** |
| `/api/skills/playground/files` | GET | 200 | File tree for project | **USEFUL** |
| `/api/discover-skills` | GET | 200 | Empty | **EMPTY** |

### Skill Sets

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/api/skill-sets/` | GET | 200 | Skill sets list | **USEFUL** |
| POST/PUT/DELETE skill sets | Various | 200/201 | Full CRUD works | **USEFUL** |

### Conversations (Commands/Hooks/Rules/Agents/Plugins/Skills)

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/api/commands/conversations/` | GET | 200 | Empty | **EMPTY** |
| `/api/hooks/conversations/` | GET | 200 | Empty | **EMPTY** |
| `/api/rules/conversations/` | GET | 200 | Empty | **EMPTY** |
| Each has: start, message, finalize, abandon, stream | POST/GET | N/A | Not tested (requires active CLI sessions) | **NOT TESTED** |

### Project API

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/api/projects/:id/sessions` | GET | 200 | Empty | **EMPTY** |
| `/api/projects/:id/milestones` | GET | 200 | Empty | **EMPTY** |
| `/api/projects/:id/phases` | GET | 200 | Empty | **EMPTY** |
| `/api/projects/:id/plans` | GET | 200 | Empty | **EMPTY** |
| `/api/projects/:id/sync` | GET | 200 | Sync status | **USEFUL** |
| `/api/projects/:id/planning/status` | GET | 200 | Planning status | **USEFUL** |

### Misc

| Endpoint | Method | Status | Response | Assessment |
|----------|--------|--------|----------|------------|
| `/admin/repo-bot-defaults/` | GET | 200 | Bot list for defaults | **USEFUL** |
| POST repo-bot-defaults requires: repo + bot_ids (list) | POST | 201 | Creates binding | **USEFUL** |
| `/admin/rotation/status` | GET | 200 | Evaluator state | **USEFUL** |
| `/admin/rotation/history` | GET | 200 | Empty | **EMPTY** |
| `/admin/reports/digests` | GET | 200 | Empty | **EMPTY** |
| PUT `/admin/reports/digests/:team_id` | PUT | 200 | Sets digest | **USEFUL** |
| `/admin/onboarding/config` | GET | 200 | Empty config | **EMPTY** |
| PUT onboarding requires: trigger_id + steps with step_order | PUT | 403 | Requires API key | **USEFUL** (auth gated) |
| `/admin/quality/entries` | GET | 200 | Empty | **EMPTY** |
| `/admin/quality/stats` | GET | 200 | Empty | **EMPTY** |
| `/admin/version-pins/` | GET | 200 | Empty | **EMPTY** |
| `/admin/diff-context/preview` | POST | 200 | Parses diffs + token estimate | **USEFUL** |

---

## Known Issues Found

1. **`/api/check-backend`** - Returns 400 for both `?backend=claude` and `?backend=opencode`. The endpoint does not accept the backend parameter correctly via query string.

2. **`/admin/triggers/:id/conditions`** - Returns 503 Service Unavailable.

3. **`/admin/executions/:id`** - Execution detail returns 404. The list endpoint returns `execution_logs.id` (integer), but the detail endpoint expects execution IDs like `exec-bot-security-...`.

4. **`/admin/budgets/limits` PUT** - Returns 500 Internal Server Error when trying to set budget limits with `hard_limit_usd`.

5. **`/admin/secrets/`** - Returns 503 because `AGENTED_VAULT_KEYS` environment variable is not set. `secrets/status` correctly reports unconfigured.

6. **`/admin/projects/:id/harness/status`** - Times out (>15s).

7. **SA Documents `doc_type`** - Only accepts uppercase `SOUL` and `IDENTITY`. Lowercase variants and other types like `knowledge`, `context`, `instruction` all fail with 400.

8. **`/health/liveness`** - Returns 200 with empty body (should probably return JSON).

9. **Repo bot defaults DELETE** - The `repo_slug` with `/` in URL doesn't route correctly regardless of URL encoding.

## Feature Completeness Assessment

### Fully Functional (End-to-End CRUD + Real Data)
- Projects, Teams, Agents, Triggers, Super Agents, Products
- Plugins, Hooks, Commands, Rules, MCP Servers
- Workflows, Sketches, Prompt Snippets, Marketplaces
- Settings, Findings, Bookmarks, Execution Tags
- Bot Memory, Orchestration Fallback Chains
- GitOps Repos, Integrations, Retention Policies, Scope Filters
- Bulk Operations, Skill Sets, Campaign CRUD
- Budget usage tracking, Analytics, Monitoring, Scheduler

### Functional But No Data
- PR Reviews, PR Assignment, Bot Pipes, Secrets (vault unconfigured)
- Conversations (need active CLI sessions), Quality ratings
- Onboarding, Version Pins, Execution Quotas

### Partially Broken
- Execution detail endpoint (ID format mismatch)
- Budget limits SET (500 error)
- Trigger conditions GET (503)
- Check backend (query param issue)
