# Directory and File Structure

**Analysis Date:** 2026-02-25

## Top-Level Layout

```
Agented/
├── backend/               # Flask API server
├── frontend/              # Vue 3 SPA
├── .planning/             # GRD planning docs, codebase analysis
├── .claude/               # Claude skills and execution reports
│   └── skills/
│       └── weekly-security-audit/reports/  # Trigger execution report output
├── docs/                  # Planning documents (legacy)
├── examples/              # Example playground apps
├── project_links/         # Symlinks to registered project paths
├── scripts/               # Bootstrap and setup scripts
│   └── setup.sh           # Full bootstrap (installs uv, node, npm)
├── justfile               # Task runner (dev, build, deploy, test commands)
├── AGENTS.md → CLAUDE.md  # Project instructions (CLAUDE.md is a symlink)
└── README.md
```

---

## Backend Structure

```
backend/
├── run.py                 # Flask dev server entry point (python run.py --debug)
├── pyproject.toml         # uv/pip project config, Black settings
├── agented.db             # SQLite database (created at runtime, gitignored)
├── .venv/                 # Python virtual environment (created by uv sync)
├── tests/                 # Pytest test suite
│   ├── conftest.py        # isolated_db fixture, test utilities
│   ├── test_*.py          # Unit tests per domain
│   └── integration/       # Integration tests
├── scripts/               # Backend utility scripts
└── app/                   # Application package
    ├── __init__.py        # create_app() factory — app wiring and startup
    ├── config.py          # Path constants: PROJECT_ROOT, DB_PATH, SYMLINK_DIR
    ├── database.py        # Legacy re-export shim (imports from app.db.*)
    ├── db/                # Database layer
    ├── models/            # Pydantic v2 request/response models
    ├── routes/            # API blueprint route handlers
    ├── services/          # Business logic services
    └── utils/             # Shared utilities
```

### `backend/app/db/` — Database Layer

All raw SQLite CRUD. No ORM.

```
app/db/
├── __init__.py            # Barrel re-export of all public DB functions
├── connection.py          # get_connection() context manager
├── schema.py              # create_fresh_schema() — all CREATE TABLE/INDEX statements
├── migrations.py          # init_db(), incremental migrations, seed functions
├── ids.py                 # Prefixed ID generators (generate_trigger_id, generate_agent_id, etc.)
├── agents.py              # Agent + conversation CRUD
├── backends.py            # AI backend accounts, fallback chains, agent sessions
├── budgets.py             # Token usage records, budget limits, cost tracking
├── commands.py            # Command CRUD
├── grd.py                 # GRD milestones, phases, plans, project sessions, sync state
├── hooks.py               # Hook CRUD
├── mcp_servers.py         # MCP server config and project assignments
├── messages.py            # Agent message bus (inbox/outbox)
├── monitoring.py          # Rate limit snapshots, monitoring config, pending retries
├── plugins.py             # Plugin + component + marketplace + sync state CRUD
├── products.py            # Product CRUD
├── projects.py            # Project + skills + team assignments + team edges CRUD
├── rotations.py           # Rotation events, product decisions, product milestones
├── rules.py               # Rule CRUD
├── settings.py            # Key-value settings store
├── sketches.py            # Sketch CRUD
├── skills.py              # User skill CRUD
├── super_agents.py        # Super agent + document + session CRUD
├── teams.py               # Team + member + agent assignment + edge CRUD
├── triggers.py            # Trigger + path + execution log + PR review CRUD
└── workflows.py           # Workflow + version + execution + node execution CRUD
```

### `backend/app/models/` — Pydantic Models

Request/response validation only. One file per domain.

```
app/models/
├── __init__.py
├── agent.py               # Agent, AgentConversation models
├── audit.py               # AuditEvent, Finding models
├── backend.py             # AIBackend, BackendAccount models
├── backend_cli.py         # CLI backend models
├── budget.py              # BudgetLimit, TokenUsage models
├── chat_state.py          # Chat state models
├── common.py              # PaginationQuery, shared models
├── grd.py                 # GrdMilestone, GrdPhase, GrdPlan, GrdSession models
├── marketplace.py         # Marketplace models
├── mcp_server.py          # MCP server models
├── monitoring.py          # MonitoringConfig, WindowSnapshot models
├── orchestration.py       # AccountHealth, FallbackChain models
├── plugin.py              # Plugin, PluginComponent models
├── pr_review.py           # PrReview, PrReviewStats models
├── product.py             # Product, ProductDecision models
├── project.py             # Project, ProjectInstallation models
├── rotation.py            # RotationSession, RotationEvent models
├── scheduler.py           # SchedulerSession models
├── setup.py               # SetupQuestion, SetupExecution models
├── sketch.py              # Sketch models
├── skill.py               # SkillInfo, UserSkill models
├── super_agent.py         # SuperAgent, SuperAgentSession models
├── team.py                # Team, TeamMember, TopologyConfig models
├── trigger.py             # Trigger, ProjectPath models
└── workflow.py            # Workflow, WorkflowVersion, WorkflowExecution models
```

### `backend/app/routes/` — API Route Handlers

44+ `APIBlueprint` modules. Each imports from `app.db` and `app.services`.

```
app/routes/
├── __init__.py            # register_blueprints() — registers all blueprints in order
├── agent_conversations.py # /admin/agent-conversations/*
├── agents.py              # /admin/agents/*
├── audit.py               # /admin/audit/*
├── backends.py            # /admin/backends/* (AI backend accounts)
├── budgets.py             # /admin/budgets/*
├── command_conversations.py # /admin/command-conversations/*
├── commands.py            # /admin/commands/*
├── executions.py          # /admin/executions/* + /admin/triggers/{id}/executions, SSE stream
├── github_webhook.py      # /github/webhook (GitHub PR/push events)
├── grd.py                 # /admin/grd/* (GRD planning API)
├── health.py              # /health/liveness, /health/readiness
├── hook_conversations.py  # /admin/hook-conversations/*
├── hooks.py               # /admin/hooks/*
├── marketplace.py         # /admin/marketplace/*
├── mcp_servers.py         # /admin/mcp-servers/* + /admin/projects/{id}/mcp-servers
├── monitoring.py          # /admin/monitoring/*
├── orchestration.py       # /admin/orchestration/*
├── plugin_conversations.py # /admin/plugin-conversations/*
├── plugin_exports.py      # /admin/plugin-exports/*
├── plugins.py             # /admin/plugins/*
├── pr_reviews.py          # /admin/pr-reviews/*
├── product_owner.py       # /admin/product-owner/*
├── products.py            # /admin/products/*
├── projects.py            # /admin/projects/*
├── rotation.py            # /admin/rotation/*
├── rule_conversations.py  # /admin/rule-conversations/*
├── rules.py               # /admin/rules/*
├── scheduler.py           # /admin/scheduler/*
├── settings.py            # /admin/settings/*
├── setup.py               # /admin/setup/*
├── sketches.py            # /admin/sketches/*
├── skill_conversations.py # /admin/skill-conversations/*
├── skills.py              # /admin/skills/*
├── spa.py                 # 404 catch-all → serves frontend/dist/index.html
├── super_agent_exports.py # /admin/super-agent-exports/*
├── super_agents.py        # /admin/super-agents/*
├── teams.py               # /admin/teams/*
├── triggers.py            # /admin/triggers/*
├── utility.py             # /admin/utility/* (path validation, backend checks)
├── webhook.py             # / (root webhook receiver for generic JSON webhooks)
└── workflows.py           # /admin/workflows/*
```

### `backend/app/services/` — Business Logic

90+ service classes. Import from `app.db` for data access.

**Execution core:**
```
services/
├── execution_service.py           # CLI command builder + subprocess runner (58k, largest file)
├── execution_log_service.py       # In-memory log buffers + SSE subscriber queues
├── orchestration_service.py       # Fallback chain routing + account rotation
├── process_manager.py             # Running process tracking + SIGTERM/SIGKILL
├── execution_type_handler.py      # Per-trigger execution type dispatch
```

**AI backends:**
```
├── backend_service.py             # AI backend CRUD + capability detection
├── backend_cli_service.py         # CLI invocation helpers per backend type
├── backend_detection_service.py   # Detects installed CLI tools
├── backend_test_service.py        # Tests backend connectivity
├── cliproxy_manager.py            # CLIProxyAPI lifecycle (OAuth proxy, 31k)
├── cliproxy_chat_service.py       # Chat via CLIProxyAPI
├── model_discovery_service.py     # Discovers available models per backend (33k)
├── provider_usage_client.py       # Calls provider rate limit / usage APIs (24k)
├── pty_service.py                 # PTY-based terminal sessions
```

**Teams and agents:**
```
├── team_execution_service.py      # Multi-agent team execution coordination (27k)
├── team_generation_service.py     # AI-generated team configurations
├── team_service.py                # Team CRUD operations
├── team_monitor_service.py        # Team execution monitoring
├── agent_service.py               # Agent management
├── agent_scheduler_service.py     # Schedules autonomous agent executions
├── agent_conversation_service.py  # Agent conversation management
├── agent_message_bus_service.py   # TTL-based inter-agent messaging
├── super_agent_session_service.py # Super agent session management
├── super_agent_export_service.py  # Super agent export/import
├── all_mode_service.py            # Multi-backend "All mode" aggregation
```

**Projects:**
```
├── project_session_manager.py     # PTY project sessions (25k)
├── project_workspace_service.py   # Git repo management
├── project_deploy_service.py      # Project deployment
├── project_install_service.py     # Project installation/bootstrap
├── project_chat_service.py        # Project-level AI chat
├── worktree_service.py            # Git worktree management
```

**Workflows:**
```
├── workflow_execution_service.py  # DAG execution engine (38k)
├── workflow_trigger_service.py    # Workflow trigger evaluation (31k)
```

**Skills and plugins:**
```
├── skill_discovery_service.py     # Filesystem skill discovery (20k)
├── skill_conversation_service.py  # Skill design conversations
├── skill_harness_service.py       # Skill harness integration
├── skill_marketplace_service.py   # Marketplace operations
├── skill_testing_service.py       # Skill test execution
├── skills_service.py              # Skill CRUD
├── skills_sh_service.py           # Shell skill invocation
├── plugin_conversation_service.py # Plugin design conversations
├── plugin_deploy_service.py       # Plugin deployment
├── plugin_export_service.py       # Plugin export/import
├── plugin_file_watcher.py         # Filesystem change monitoring
├── plugin_parser_service.py       # Plugin file parsing
├── plugin_persistence_service.py  # Plugin save/load
├── plugin_sync_service.py         # Plugin sync state
├── plugin_generation_service.py   # AI-generated plugin configs
├── plugin_import_service.py       # Plugin import
```

**GRD (planning):**
```
├── grd_cli_service.py             # GRD binary detection and CLI invocation
├── grd_sync_service.py            # Sync GRD data between filesystem and DB
```

**Background/monitoring:**
```
├── scheduler_service.py           # APScheduler wrapper
├── monitoring_service.py          # Rate limit monitoring (28k)
├── session_collection_service.py  # Claude session usage collector
├── session_cost_service.py        # Session cost calculation
├── session_usage_collector.py     # Usage data collection
├── ralph_monitor_service.py       # Ralph loop monitoring
├── rotation_evaluator.py          # Team rotation evaluation
├── rotation_service.py            # Rotation management
├── agent_scheduler_service.py     # Agent execution scheduling
```

**Infrastructure:**
```
├── audit_log_service.py           # Structured audit event logging
├── audit_service.py               # Audit history and analysis (27k)
├── budget_service.py              # Token budget enforcement
├── rate_limit_service.py          # Rate limit detection (pattern matching on stderr)
├── github_service.py              # GitHub API + repo cloning
├── harness_service.py             # Harness integration
├── harness_deploy_service.py      # Harness deployment
├── harness_loader_service.py      # Harness loading
├── mcp_sync_service.py            # MCP server sync
├── setup_service.py               # Initial setup wizard
├── setup_execution_service.py     # Setup execution runner
├── sync_persistence_service.py    # Sync state persistence
├── conversation_streaming.py      # Base conversation SSE streaming
├── base_conversation_service.py   # Shared conversation logic
├── base_generation_service.py     # Shared AI generation logic
├── chat_state_service.py          # Chat state management
├── layer_detection_service.py     # Agent layer detection
├── sketch_routing_service.py      # Sketch routing logic
├── product_owner_service.py       # Product owner operations
├── pr_review_service.py           # PR review automation
└── hook_conversation_service.py   # Hook design conversations
```

### `backend/app/utils/`

```
app/utils/
├── __init__.py
├── json_path.py           # get_nested_value() — dot-notation JSON field extraction
├── plugin_format.py       # Plugin file format parsing utilities
└── timezone.py            # get_local_timezone() helper
```

---

## Frontend Structure

```
frontend/
├── index.html             # Vite HTML entry point
├── vite.config.ts         # Build config + dev proxy to backend :20000
├── tsconfig.json          # TypeScript config
├── package.json           # npm dependencies
├── dist/                  # Production build output (gitignored)
├── e2e/                   # End-to-end tests (Playwright)
│   ├── fixtures/
│   ├── pages/
│   └── tests/
└── src/                   # Application source
    ├── main.ts            # App entry: createApp, use(router), mount('#app')
    ├── App.vue            # Root component: sidebar + router-view, toast system
    ├── style.css          # Global CSS reset
    ├── assets/            # Static assets (fonts, images)
    ├── components/        # Reusable Vue components (organized by domain)
    ├── composables/       # Vue 3 composable functions
    ├── layouts/           # Layout wrapper components
    ├── router/            # Vue Router configuration
    ├── services/          # API client layer
    ├── test/              # Vitest setup
    ├── types/             # Shared TypeScript types
    └── views/             # Page-level view components
        └── __tests__/     # View component tests
```

### `frontend/src/router/`

```
router/
├── index.ts               # createRouter with createWebHistory, registerGuards
├── guards.ts              # beforeEach: title, entity validation, 5-min cache, fail-open
└── routes/
    ├── agents.ts          # /agents, /agents/:agentId, /agents/new
    ├── dashboard.ts       # /, /security, /scheduling, /service-health, /usage, etc.
    ├── mcpServers.ts      # /mcp-servers, /mcp-servers/:mcpServerId
    ├── misc.ts            # /audit/:auditId, /executions, /sketches, /setup
    ├── plugins.ts         # /plugins, /plugins/:pluginId
    ├── products.ts        # /products, /products/:productId
    ├── projects.ts        # /projects, /projects/:projectId
    ├── settings.ts        # /settings
    ├── skills.ts          # /skills, /skills/:skillId
    ├── superAgents.ts     # /super-agents, /super-agents/:superAgentId
    ├── teams.ts           # /teams, /teams/:teamId
    ├── triggers.ts        # /triggers/:triggerId, /pr-reviews
    └── workflows.ts       # /workflows, /workflows/:workflowId
```

### `frontend/src/services/api/`

```
services/api/
├── client.ts              # apiFetch() with timeout, retry, ApiError class
├── types.ts               # All TypeScript types (~37k lines)
├── index.ts               # Barrel re-export of all API objects and types
├── agents.ts              # agentApi, agentConversationApi
├── backends.ts            # backendApi
├── budgets.ts             # budgetApi
├── commands.ts            # commandApi, commandConversationApi
├── grd.ts                 # grdApi (milestones, phases, plans, sessions)
├── hooks.ts               # hookApi, hookConversationApi
├── marketplace.ts         # marketplaceApi
├── mcp-servers.ts         # mcpServerApi
├── monitoring.ts          # monitoringApi
├── orchestration.ts       # orchestrationApi
├── plugins.ts             # pluginApi, pluginExportApi, pluginConversationApi
├── products.ts            # productApi
├── projects.ts            # projectApi
├── rotation.ts            # rotationApi
├── rules.ts               # ruleApi, ruleConversationApi
├── scheduler.ts           # schedulerApi
├── sketches.ts            # sketchApi
├── skills.ts              # skillsApi, userSkillsApi, skillsShApi, harnessApi, skillConversationApi
├── super-agents.ts        # superAgentApi, superAgentDocumentApi, superAgentSessionApi, agentMessageApi
├── system.ts              # healthApi, versionApi, utilityApi, settingsApi, setupApi
├── teams.ts               # teamApi
├── triggers.ts            # triggerApi, auditApi, resolveApi, executionApi, prReviewApi
└── workflows.ts           # workflowApi, workflowExecutionApi
```

### `frontend/src/composables/`

```
composables/
├── useAiChat.ts           # Super agent SSE chat (state_delta protocol, reconnect watchdog)
├── useAllMode.ts          # Multi-backend "All mode" response aggregation
├── useAutoScroll.ts       # Auto-scroll to bottom in chat containers
├── useCanvasLayout.ts     # Canvas layout calculations
├── useConversation.ts     # Generic AI design conversation (hook/command/rule/plugin)
├── useDataPage.ts         # Generic data page loading pattern
├── useFocusTrap.ts        # Keyboard focus trap for modals
├── useListFilter.ts       # List filtering with text search
├── useMarkdown.ts         # Markdown rendering composable
├── useOrgCanvas.ts        # Organization hierarchy canvas
├── usePagination.ts       # Generic pagination
├── useProcessGroups.ts    # Tool call / reasoning group rendering
├── useProjectSession.ts   # PTY project session lifecycle + SSE streaming
├── useSidebarCollapse.ts  # Sidebar mobile/collapse state (localStorage)
├── useSketchChat.ts       # Sketch AI chat
├── useStreamingGeneration.ts # Streaming text generation
├── useStreamingParser.ts  # SSE stream parser
├── useTeamCanvas.ts       # Team topology canvas interactions (17k)
├── useToast.ts            # inject('showToast') helper
├── useTokenFormatting.ts  # Format token counts for display
├── useTopologyValidation.ts # Team topology constraint validation
├── useUnsavedGuard.ts     # Warn on unsaved changes before navigation
├── useWebMcpTool.ts       # WebMCP tool registration
├── useWorkflowCanvas.ts   # Workflow DAG canvas interactions
├── useWorkflowExecution.ts # Workflow execution state + SSE
└── useWorkflowValidation.ts # Workflow graph validation
```

### `frontend/src/layouts/`

```
layouts/
├── DefaultLayout.vue      # Standard padded content layout
├── EntityLayout.vue       # Loading/error state wrapper; exposes {entity, reload} slot
└── FullBleedLayout.vue    # No-padding layout for canvas/workflow views
```

### `frontend/src/components/`

```
components/
├── layout/
│   └── AppSidebar.vue     # Primary navigation sidebar (46k — handles all nav)
├── base/                  # Reusable UI primitives
│   ├── BaseModal.vue
│   ├── BaseButton.vue
│   ├── BaseInput.vue
│   └── ... (17 files total)
├── ai/                    # AI chat panel
│   ├── AiChatPanel.vue
│   └── ... (11 files total)
├── canvas/                # Graph/canvas components
│   ├── OrgCanvas.vue
│   ├── TeamCanvas.vue
│   └── ... (12 files total)
├── grd/                   # GRD planning UI
│   ├── KanbanBoard.vue
│   ├── KanbanColumn.vue
│   └── MilestoneOverview.vue
├── monitoring/            # Usage/monitoring charts
│   ├── CombinedUsageChart.vue
│   ├── RemainingTimeChart.vue
│   └── ... (16 files total)
├── triggers/              # Trigger/bot components
├── teams/                 # Team management
├── plugins/               # Plugin components
├── projects/              # Project components
├── product/               # Product dashboard components
├── workflow/              # Workflow node components
│   └── nodes/             # Per-node-type components
├── super-agents/          # Super agent session components
├── sessions/              # Session log/history components
├── security/              # Security audit components
├── settings/              # Settings components
└── sketches/              # Sketch components
```

### `frontend/src/views/`

One `.vue` file per page route (64 total). Key views:

| File | Route | Purpose |
|------|-------|---------|
| `DashboardsPage.vue` | `/` | Main dashboard |
| `TeamsPage.vue` | `/teams` | Team list and management |
| `TeamDashboard.vue` | `/teams/:teamId` | Team detail with execution status |
| `AgentsPage.vue` | `/agents` | Agent list |
| `AgentDesignPage.vue` | `/agents/:agentId` | Agent design conversations |
| `ProjectsPage.vue` | `/projects` | Project list |
| `ProjectManagementPage.vue` | `/projects/:projectId` | Project sessions + GRD |
| `ProjectDashboard.vue` | `/projects/:projectId/dashboard` | Project status |
| `WorkflowBuilderPage.vue` | `/workflows/new` | DAG workflow editor |
| `WorkflowPlaygroundPage.vue` | `/workflows/:workflowId` | Workflow execution |
| `TokenUsageDashboard.vue` | `/usage` | Token spend charts |
| `SecurityDashboard.vue` | `/security` | Security audit status |
| `ExecutionHistory.vue` | `/executions` | All execution logs |
| `BackendDetailPage.vue` | `/backends/:backendId` | AI backend configuration |
| `SuperAgentPlayground.vue` | `/super-agents/:superAgentId` | AI chat interface |
| `HarnessIntegration.vue` | `/projects/:projectId/harness` | Harness plugin integration |
| `PluginDetailPage.vue` | `/plugins/:pluginId` | Plugin detail/edit |
| `SkillsPlayground.vue` | `/skills/playground` | Skill testing |
| `SettingsPage.vue` | `/settings` | Global settings |

---

## Configuration Files

| File | Purpose |
|------|---------|
| `justfile` | Task runner (setup, dev, build, deploy, kill, test) |
| `backend/pyproject.toml` | Python package config, Black settings (`line-length=100`, `target-version=py310`) |
| `backend/app/config.py` | `DB_PATH` (env: `AGENTED_DB_PATH`), `PROJECT_ROOT`, `SYMLINK_DIR` |
| `frontend/vite.config.ts` | Vite build config, dev proxy (`/api/*`, `/admin/*`, `/health/*` → `:20000`) |
| `frontend/tsconfig.json` | TypeScript strict mode config |
| `frontend/package.json` | npm dependencies, scripts (`dev`, `build`, `test`, `test:run`) |
| `.planning/config.json` | GRD configuration |

---

## Key Entry Points

| Scenario | Entry Point |
|----------|-------------|
| Start backend dev server | `backend/run.py` (via `just dev-backend` → `uv run python run.py --debug`) |
| Start frontend dev server | `frontend/src/main.ts` (via `just dev-frontend` → `npm run dev`) |
| Flask app factory | `backend/app/__init__.py` → `create_app()` |
| All route registration | `backend/app/routes/__init__.py` → `register_blueprints()` |
| All DB function exports | `backend/app/db/__init__.py` |
| Frontend app root | `frontend/src/App.vue` |
| Frontend router | `frontend/src/router/index.ts` |
| Frontend API client | `frontend/src/services/api/index.ts` |
| Webhook receiver | `backend/app/routes/webhook.py` |
| GitHub webhook receiver | `backend/app/routes/github_webhook.py` |
| Bot execution | `backend/app/services/execution_service.py` → `ExecutionService.run_trigger()` |

---

## Where to Place New Code

**New API endpoint:** Create `backend/app/routes/{domain}.py` with `APIBlueprint`, register in `backend/app/routes/__init__.py`.

**New database table:** Add `CREATE TABLE` to `backend/app/db/schema.py`, add migration to `backend/app/db/migrations.py`, create `backend/app/db/{domain}.py` with CRUD functions, add re-exports to `backend/app/db/__init__.py`.

**New service:** Create `backend/app/services/{domain}_service.py`. Import from `app.db` for data access, not from routes.

**New Pydantic model:** Add to existing `backend/app/models/{domain}.py` or create new file for new domains.

**New frontend page:** Create `frontend/src/views/{PageName}.vue`, add route entry in appropriate `frontend/src/router/routes/{domain}.ts`.

**New API client module:** Create `frontend/src/services/api/{domain}.ts`, re-export from `frontend/src/services/api/index.ts`.

**New composable:** Create `frontend/src/composables/use{Name}.ts`.

**New reusable component:** Place in `frontend/src/components/{category}/` matching closest existing category.

---

*Structure analysis: 2026-02-25*
