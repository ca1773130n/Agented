# Sidebar Audit — 2026-05-21

Source: `frontend/src/components/layout/AppSidebar.vue` walked top-to-bottom.
Each entry is the route name in the sidebar; the view file is the actual
component the route mounts (from `frontend/src/router/routes/*.ts`).

**Recency** is `git log -1` on the view file. **Inbound refs** is the count
of other `frontend/src/**` files (excluding `AppSidebar.vue` and `router/`)
that reference the route name as a string — a rough liveness proxy. "0
inbound" almost always means the only way to reach the page is the
sidebar.

---

## 1. Flat top-level

### Watch Tower (not a route)

- **What it is:** Section *label* only — `<SidebarSectionLabel label="Watch Tower" .../>` at the very top of the sidebar. It heads the Dashboards group and surfaces a "triggers" error retry slot. It is **not navigable** and has no view file.
- **Shows:** Nothing on click. The label sits above the Dashboards expandable group.
- **Enables:** Retry of the `triggers` sidebar load when failing.
- **Connects to:** Visually owns the Dashboards submenu and the `sketch-chat` flat link.
- **Last touched:** see AppSidebar.vue
- **Inbound refs:** N/A (label only)

### Sketch (route: `sketch-chat` → `views/SketchChatPage.vue`)

- **What it is:** Free-form ideation surface. "Sketch Ideation" — chat with Claude, then have the sketch automatically classified and routed to a SuperAgent or Team.
- **Shows:** Left pane is `AiChatPanel`; right side is a sketch classification/route preview.
- **Enables:** Capture a half-formed idea, then *push it into* the platform's real entities (SuperAgent or Team).
- **Connects to:** Outbound to SuperAgents and Teams; it is the "front door" for unstructured input.
- **Last touched:** 2026-05-10 (`f5518f5`) — safe date formatter sweep.
- **Inbound refs:** 3 (referenced from a small number of helpers).

### Settings (route: `settings` → `views/SettingsPage.vue`)

- **What it is:** App-wide user/operator settings page with tabs. One visible tab is "Add Marketplace" (the plugin/skill/MCP marketplace registry list lives here).
- **Shows:** Marketplace list and add-marketplace form; other tabs.
- **Enables:** `marketplaceApi.create`, `marketplaceApi.list`.
- **Connects to:** All marketplace-driven Explore pages (Explore Plugins / Skills / MCP Servers / SuperAgents) read the same marketplace registry that this page manages.
- **Last touched:** 2026-03-30 (`409d78b`) — onboarding/auth/monitoring sweep.
- **Inbound refs:** 1.

---

## 2. Dashboards submenu (under "Watch Tower")

### All Dashboards (route: `dashboards` → `views/DashboardsPage.vue`)

- **What it is:** "Command Center" landing — an index of every dashboard. Renders a tile per trigger from `triggerApi.list` plus tiles for each fixed dashboard.
- **Shows:** A grid of trigger cards + a static list of fixed dashboards.
- **Enables:** Drill into a per-trigger dashboard or any of the 12 fixed dashboards.
- **Connects to:** Every other "dashboard" entry; the per-trigger dashboards (dynamic) and Trigger History entries are produced from the same trigger list.
- **Last touched:** 2026-03-16 (`d8d737f`) — original IA pass.
- **Inbound refs:** 3.

### Security Scan (route: `security-dashboard` → `views/SecurityDashboard.vue`)

- **What it is:** Status of the **Security Scan** built-in trigger across all tracked projects. Built on `auditApi`.
- **Shows:** Current security status, finding stats, per-project breakdown, recent scan history.
- **Enables:** View stats; `triggerApi.setAutoResolve`; navigate into project audit detail.
- **Connects to:** Same data source as Security History (audit log) and Findings Triage Board.
- **Last touched:** 2026-03-16 (`d8d737f`).
- **Inbound refs:** 1.

### PR Review (route: `pr-review-dashboard` → `views/PrReviewDashboard.vue`)

- **What it is:** Overview of pull requests across all tracked projects (the **PR Review** built-in trigger's dashboard).
- **Shows:** PR stats, recent reviews, per-project breakdown.
- **Enables:** `prReviewApi.list/getHistory/getStats`, `triggerApi.run`.
- **Connects to:** PR Auto-Assignment, PR Review Learning Loop, GitHub Actions, GitHub PR Annotation.
- **Last touched:** 2026-03-19 (`bba509e`) — TS-error sweep, not real change.
- **Inbound refs:** 1.

### Token Usage (route: `token-usage` → `views/TokenUsageDashboard.vue`)

- **What it is:** Cost/usage dashboard — rate-limit warnings, cost trend chart, per-agent/team/trigger spend, account rotation hints. **Touched in v0.7.93** to surface accounts missing OAuth credentials.
- **Shows:** Cost trends, session stats, all-time spend, per-entity breakdown, rotation status.
- **Enables:** `budgetApi.deleteLimit`, set budget limits, view spend by dimension.
- **Connects to:** Usage submenu (`usage-history`) is a leaner per-period view of the same `budgetApi` data; Team Budgets / Execution Quotas are the policy side of the same domain; AI Backends (the OAuth credential issue surfaces here too).
- **Last touched:** 2026-05-19 (`b2c7e90`) — *actively maintained*.
- **Inbound refs:** 1.

### Scheduling (route: `rotation-dashboard` → `views/SchedulingDashboard.vue`)

- **What it is:** Scheduler / account rotation view — shows scheduler sessions and rotation history.
- **Shows:** Summary cards, scheduler sessions, rotation history.
- **Enables:** `rotationApi.getHistory/getStatus`, `schedulerApi.getStatus`.
- **Connects to:** On-Call Escalation (also rotationApi); Smart Schedule Optimizer (schedulerApi); per-trigger schedule config.
- **Last touched:** 2026-03-16 (`d8d737f`).
- **Inbound refs:** 1.

### Analytics (route: `analytics-dashboard` → `views/AnalyticsDashboard.vue`)

- **What it is:** Cross-cutting analytics: cost analytics + bot effectiveness + execution analytics.
- **Shows:** "Run some bots to see analytics here." empty state otherwise; three combined charts.
- **Enables:** `analyticsApi.fetchCostAnalytics / fetchEffectiveness / fetchExecutionAnalytics`.
- **Connects to:** Bot Performance Benchmarks (`analyticsApi.fetchEffectiveness` again), Changelog Generator (`fetchExecutionAnalytics`), Prompt A/B Testing.
- **Last touched:** 2026-05-01 (`b413554`) — fetch-failure surfacing.
- **Inbound refs:** 0 — *only entry is the sidebar.*

### Health Monitor (route: `health-dashboard` → `views/BotHealthDashboard.vue`)

- **What it is:** **Org-wide** health dashboard — status summary, health alerts, acknowledgement, manual health check.
- **Shows:** Status summary cards, alerts list.
- **Enables:** `analyticsApi.fetchHealthStatus/fetchHealthAlerts/acknowledgeAlert/runHealthCheck`.
- **Connects to:** Bot Health (per-bot rollup, similar name — **two surfaces, one concept**).
- **Last touched:** 2026-05-01 (`b413554`).
- **Inbound refs:** 0.

### Bot Health (route: `bot-health` → `views/BotHealthPage.vue`)

- **What it is:** **Per-bot** success-rate / latency / status rollup (v0.7.0 addition). Separate API (`botHealthApi.list`) from Health Monitor.
- **Shows:** A row per bot with success rate, latency, status.
- **Enables:** Read-only rollup.
- **Connects to:** Overlaps conceptually with Health Monitor; both live under Dashboards.
- **Last touched:** 2026-05-06 (`2e97fee`).
- **Inbound refs:** 0.

### Impact Report (route: `team-impact-report` → `views/TeamImpactReport.vue`)

- **What it is:** Weekly impact report per team — built on `analyticsApi.fetchWeeklyReport`.
- **Shows:** Period selector, weekly metrics.
- **Enables:** Read-only.
- **Connects to:** Cross-Team Insights, Team Leaderboard — all roll up team performance.
- **Last touched:** 2026-03-19 (`bba509e`) — TS sweep.
- **Inbound refs:** 0.

### Cross-Team Insights (route: `cross-team-insights` → `views/CrossTeamInsightsDashboard.vue`)

- **What it is:** Org-level cross-team rollup — team summaries, org-wide findings, top risky repos.
- **Shows:** Org stats, team comparison, risky-repo list.
- **Enables:** `analyticsApi.fetchCrossTeamInsights` (read-only).
- **Connects to:** Same conceptual family as Team Impact Report and Team Leaderboard.
- **Last touched:** 2026-03-16 (`d8d737f`).
- **Inbound refs:** 0.

### Execution Queue (route: `execution-queue-dashboard` → `views/ExecutionQueueDashboard.vue`)

- **What it is:** Live queue of executions — cancel, cancel-by-trigger, queue stats.
- **Shows:** Queue status per trigger, in-flight executions.
- **Enables:** `executionApi.cancel`, `cancelQueueForTrigger`, `getQueueStatus`.
- **Connects to:** Live Execution Terminal, Execution Search, Execution Replay & Diff — all execution-domain.
- **Last touched:** 2026-03-19 (`bba509e`) — TS sweep.
- **Inbound refs:** 0.

### Anomaly Detection (route: `execution-anomaly-detection` → `views/ExecutionAnomalyDetection.vue`)

- **What it is:** Static anomaly detection page. *No API calls in script setup.*
- **Shows:** Hard-coded stats / sample UI.
- **Enables:** Nothing — appears to be a placeholder/concept view.
- **Connects to:** Execution domain visually, but no live data wiring.
- **Last touched:** 2026-03-19 (`bba509e`) — TS sweep.
- **Inbound refs:** 0. **Smells stale.**

### ROI Leaderboard (route: `team-leaderboard` → `views/TeamLeaderboard.vue`)

- **What it is:** "Team Automation Leaderboard" — ranks teams. *No API calls in script setup.*
- **Shows:** A leaderboard.
- **Enables:** Nothing dynamic at the moment.
- **Connects to:** Cross-Team Insights, Impact Report.
- **Last touched:** 2026-05-11 (`8943ead`) — TS-error unblock sweep, not feature work.
- **Inbound refs:** 0. **Smells stale.**

### Per-trigger dashboards (dynamic) (route: `trigger-dashboard` → `views/GenericTriggerDashboard.vue`)

- **What it is:** One auto-rendered sidebar entry per user-created trigger (from `props.customTriggers`). Each row routes to `trigger-dashboard` with `:triggerId`.
- **Shows:** The standard trigger dashboard for that specific trigger.
- **Enables:** Run, view history, configure — whatever the generic dashboard offers.
- **Connects to:** Trigger History submenu mirrors the same `customTriggers` list (`trigger-history`).
- **Last touched:** (component) — generic.
- **Inbound refs:** N — driven by data, not static refs.

---

## 3. Sketch — see §1

---

## 4. Organization

### Products (route: `products` → `views/ProductsPage.vue`)

- **What it is:** CRUD page for **Products** — top-level groupings of projects. Modal-driven create.
- **Shows:** Product cards (description, owning team).
- **Enables:** `productApi.create/delete/list`, link to team.
- **Connects to:** **Product Dashboard** (per-product) and **Product Settings** (per-product) — reachable from the row's gear icons (not in the sidebar enumeration). Projects belong to Products.
- **Last touched:** 2026-05-10 (`47c341d`).
- **Inbound refs:** 10.

### Per-product entries (dynamic) — sidebar shows each Product as a row

- Row click → `product-dashboard` (`views/ProductDashboard.vue`) — assignable projects, modals to add unassigned projects.
- Gear → `product-settings` (`views/ProductSettingsPage.vue`) — choose responsible team.

### Projects (route: `projects` → `views/ProjectsPage.vue`)

- **What it is:** CRUD page for **Projects** — the unit of work. Each project can be assigned to a Product and a primary Team, has a GitHub repo, owns Triggers, owns SuperAgent **Instances**, and has Planning artifacts.
- **Shows:** Project cards.
- **Enables:** `projectApi.create/delete/list`, link to product/team.
- **Connects to:** Project Dashboard, Project Settings, **Project Planning** (`project-planning`), **Project Instance Playground** (`project-instance-playground` — actually mounts `SuperAgentPlayground.vue`), Triggers (filtered by project).
- **Last touched:** 2026-05-11 (`8943ead`).
- **Inbound refs:** 11.

### Per-project entries (dynamic)

For each project, the sidebar renders **four** affordances:
1. Project name → `project-dashboard`.
2. People icon → toggles instance list (SuperAgent sessions bound to this project, fetched via `projectInstancesCache`).
3. Book icon → `project-planning` — planning artifacts page.
4. Gear → `project-settings`.

When the instance list is expanded, each instance routes to `project-instance-playground` with `:projectId`/`:instanceId`. **This is the canonical "SuperAgent attached to a project" surface** and is the same component as `super-agent-playground`.

### Teams (route: `teams` → `views/TeamsPage.vue`)

- **What it is:** CRUD for **Teams**. Teams are groups of Agents, can be assigned to Products/Projects, and lead by an Agent.
- **Shows:** Team cards, "Review Generated Team Configuration" overlay (the team builder can auto-generate configs).
- **Enables:** `teamApi.create/delete`, `teamApi.addAssignment/addMember`, also creates Agents inline (`agentApi.create`).
- **Connects to:** Team Dashboard / Team Settings / Team Builder; assignments to Products/Projects.
- **Last touched:** 2026-05-11 (`8943ead`).
- **Inbound refs:** 19 — **the most-linked-to org entity.**

---

## 5. Agents (subagents)

### All Agents (route: `agents` → `views/AgentsPage.vue`)

- **What it is:** CRUD list of **Agents** — these are the *subagent* concept (per the user's distinction): single-shot, used as Team members, configured per project/team.
- **Shows:** Agent cards.
- **Enables:** `agentApi.list/create/update/delete/run` — note: `.run` means agents can be one-shot invoked.
- **Connects to:** Teams (Agents are Team members), Conversation History Viewer (`agentApi.list` + `agentConversationApi.get`), Bot Dependency Graph.
- **Last touched:** 2026-05-10 (`70b0fbb`).
- **Inbound refs:** 12.

### Create Agent (route: `agent-create` → `views/AgentCreateWizard.vue`)

- **What it is:** Chat-driven wizard for agent design. "Keep chatting — once Claude has the agent's name, purpose, and behavior locked in, this button activates."
- **Shows:** Chat panel + create button.
- **Enables:** Wizard-style creation; same backend as Agents page.
- **Connects to:** Agents page (post-create).
- **Last touched:** 2026-05-18 (`42a6d03`) — *actively maintained, bug-class sweep.*
- **Inbound refs:** 1.

---

## 6. SuperAgents (persistent-session agents)

### All SuperAgents (route: `super-agents` → `views/SuperAgentsPage.vue`)

- **What it is:** CRUD for **SuperAgents** — persistent, project-bound agents that own long-running sessions (the project-instance concept). API includes `activityStatus` — these have a live/idle state.
- **Shows:** SA cards (description, activity status).
- **Enables:** `superAgentApi.create/update/delete`, activity status polling.
- **Connects to:** Per-project instances in the sidebar route here as `project-instance-playground` (same view as `super-agent-playground`); **Super-Agent Inspector** (`super-agent-inspector`) for an Ouroboros/run-rollup view; Sketch can route into SA.
- **Last touched:** 2026-05-19 (`d73847b`) — *actively maintained, SA Ouroboros bridge work.*
- **Inbound refs:** 3.

### Explore SuperAgents (route: `explore-super-agents` → `views/ExploreSuperAgents.vue`)

- **What it is:** Marketplace search for shareable SuperAgents.
- **Shows:** `marketplaceApi.search` results.
- **Enables:** Search-only at present.
- **Connects to:** Same marketplace registry that Settings manages and that Explore Plugins / Skills / MCP Servers also use.
- **Last touched:** 2026-03-06 (`b2cba61`).
- **Inbound refs:** 1. **Stale.**

---

## 7. Forge

### Workflows (route: `workflows` → `views/WorkflowsPage.vue`)

- **What it is:** CRUD for Workflows.
- **Shows:** Workflow cards.
- **Enables:** `workflowApi.create/list/update/delete`.
- **Connects to:** Workflow Playground (creates workflow versions).
- **Last touched:** 2026-05-09 (`c6a6d18`).
- **Inbound refs:** 3.

### Workflow Playground (route: `workflow-playground` → `views/WorkflowPlaygroundPage.vue`)

- **What it is:** "AI Workflow Designer" — chat-driven workflow design that spawns SuperAgent sessions to assemble a workflow, then saves a version.
- **Shows:** Designer canvas, SA chat panel.
- **Enables:** `superAgentSessionApi.chatStream`, `workflowApi.create/createVersion`.
- **Connects to:** Workflows, SuperAgents (uses SA sessions as its execution substrate). **This is the only page in Forge that uses SA infrastructure.**
- **Last touched:** 2026-05-10 (`bc70bbc`).
- **Inbound refs:** 0.

### Plugins (route: `plugins` → `views/PluginsPage.vue`)

- **What it is:** CRUD for Plugins (Claude Code plugins). Each plugin bundles skills/commands/hooks/rules/MCP-server entries.
- **Shows:** Plugin cards.
- **Enables:** `pluginApi.create/list/update/delete`, marketplace fetch.
- **Connects to:** Plugin Design, Explore Plugins, Plugin Detail, Harness Integration.
- **Last touched:** 2026-05-10 (`70b0fbb`).
- **Inbound refs:** 9.

### Plugin Design (route: `plugin-design` → `views/PluginDesignPage.vue`)

- **What it is:** Chat-driven plugin design wizard. "Keep chatting — once Claude has the plugin's name, purpose, and at least one component (skill / command / hook / rule), this button activates."
- **Shows:** Chat + create button.
- **Enables:** Wizard creation.
- **Connects to:** Same pattern as `command-design`, `hook-design`, `rule-design`, `skill-create`, `agent-create`.
- **Last touched:** 2026-05-18 (`42a6d03`).
- **Inbound refs:** 1.

### Explore Plugins (route: `explore-plugins` → `views/ExplorePlugins.vue`)

- **What it is:** Marketplace browser for plugins; also manages **marketplace registries** (`marketplaceApi.create/delete/list/refreshCache`).
- **Shows:** Search results, registry list.
- **Enables:** Install from marketplace, register a marketplace.
- **Connects to:** Shares the marketplace registry concept with `explore-skills`, `explore-mcp-servers`, `explore-super-agents`, and Settings → Add Marketplace tab. **Four sibling pages all rebuild the same registry UI.**
- **Last touched:** 2026-03-20 (`6461fd5`).
- **Inbound refs:** 1.

### Harness Integration (route: `harness-integration` → `views/HarnessIntegration.vue`)

- **What it is:** View of installed harness (Claude Code) config — wired skills/commands/hooks/rules/plugins/agents.
- **Shows:** `harnessApi.getConfig/getSkills`.
- **Enables:** Read-only review of what's currently wired.
- **Connects to:** All of skills/commands/hooks/rules/plugins/agents.
- **Last touched:** 2026-03-19 (`bba509e`) — TS sweep.
- **Inbound refs:** 0. **Stale.**

### MCP Servers (route: `mcp-servers` → `views/McpServersPage.vue`)

- **What it is:** CRUD for **MCP Servers** (Model Context Protocol servers).
- **Shows:** Server cards.
- **Enables:** `mcpServerApi.create/list/delete`.
- **Connects to:** Explore MCP Servers; per-server detail (`mcp-server-detail`).
- **Last touched:** 2026-05-11 (`3de444a`).
- **Inbound refs:** 2.

### Explore MCP Servers (route: `explore-mcp-servers` → `views/ExploreMcpServers.vue`)

- **What it is:** Marketplace browser for MCP servers + registry management (same shape as Explore Plugins).
- **Shows:** Search results, registries.
- **Enables:** Install / register.
- **Connects to:** MCP Servers, marketplace family.
- **Last touched:** 2026-03-16 (`d8d737f`).
- **Inbound refs:** 0. **Stale.**

### Skills — Playground (route: `skills-playground` → `views/SkillsPlayground.vue`)

- **What it is:** Sandbox to test skills (`skillsApi.test/streamTest/stopTest`).
- **Shows:** Skill selection panel, test runner.
- **Enables:** Test, stream, stop a skill run.
- **Connects to:** My Skills (user-owned), Explore Skills (marketplace), Skill Create.
- **Last touched:** 2026-03-19 (`bba509e`) — TS sweep.
- **Inbound refs:** 0.

### Skills — Create (route: `skill-create` → `views/SkillCreateWizard.vue`)

- **What it is:** Chat-driven skill design wizard.
- **Shows:** Chat + create button.
- **Enables:** Wizard creation.
- **Connects to:** My Skills, Skill Detail.
- **Last touched:** 2026-05-17 (`51e097c`) — *actively maintained.*
- **Inbound refs:** 0.

### Skills — My Skills (route: `my-skills` → `views/MySkills.vue`)

- **What it is:** User-owned skills (`userSkillsApi.list/add/update/delete`).
- **Shows:** Skill cards, add-skill modal.
- **Enables:** Add a skill (from registry), update, delete.
- **Connects to:** Skills Playground, Explore Skills, Skill Detail.
- **Last touched:** 2026-05-10 (`70b0fbb`).
- **Inbound refs:** 3.

### Skills — Explore (route: `explore-skills` → `views/ExploreSkills.vue`)

- **What it is:** Marketplace browser for skills + registry management (same shape).
- **Shows:** Search results, registries.
- **Enables:** Install via `skillsShApi.install`.
- **Connects to:** Marketplace family.
- **Last touched:** 2026-03-16 (`d8d737f`).
- **Inbound refs:** 0.

### Commands (route: `commands` → `views/CommandsPage.vue`)

- **What it is:** CRUD for slash-commands (`commandApi.create/list/update/delete`).
- **Shows:** Command cards with filters.
- **Enables:** Create / edit / delete commands.
- **Connects to:** Command Design (wizard); Harness Integration.
- **Last touched:** 2026-05-11 (`bb9d456`).
- **Inbound refs:** 6.

### Command Design (route: `command-design` → `views/CommandDesignPage.vue`)

- **What it is:** Chat-or-form wizard for command design (defaults to chat as of v0.7.90).
- **Shows:** Form mode or chat mode; same pattern as hook/rule/plugin/skill/agent design.
- **Enables:** Wizard creation / edit.
- **Connects to:** Commands.
- **Last touched:** 2026-05-19 (`c549c03`).
- **Inbound refs:** 1.

### Hooks (route: `hooks` → `views/HooksPage.vue`)

- **What it is:** CRUD for hooks (`hookApi.create/list/update/delete`).
- **Shows:** Hook cards with filters.
- **Enables:** Create / edit / delete.
- **Connects to:** Hook Design wizard; Harness Integration.
- **Last touched:** 2026-05-11 (`3de444a`).
- **Inbound refs:** 7.

### Hook Design (route: `hook-design` → `views/HookDesignPage.vue`)

- **What it is:** Chat-or-form wizard for hook design (defaults to chat as of v0.7.90).
- **Last touched:** 2026-05-19 (`c549c03`).
- **Inbound refs:** 1.

### Rules (route: `rules` → `views/RulesPage.vue`)

- **What it is:** CRUD for rules (validation/governance rules — `ruleApi.create/list/update/delete`).
- **Shows:** Rule cards with filters.
- **Enables:** Create / edit / delete.
- **Connects to:** Rule Design wizard; Harness Integration.
- **Last touched:** 2026-05-11 (`3de444a`).
- **Inbound refs:** 3.

### Rule Design (route: `rule-design` → `views/RuleDesignPage.vue`)

- **What it is:** Chat-or-form wizard for rule design (defaults to chat as of v0.7.90).
- **Last touched:** 2026-05-19 (`c549c03`).
- **Inbound refs:** 1.

---

## 8. Triggers (flat link, currently under Forge)

### Triggers (route: `triggers` → `views/TriggerManagement.vue`)

- **What it is:** **Trigger management** — the page that owns trigger CRUD. Triggers are scoped to projects and teams (`projectApi.list`, `teamApi.list`) and are the *delivery mechanism* for the platform per CLAUDE.md.
- **Shows:** Trigger list, project/team scoping.
- **Enables:** `triggerApi.list/get/update/delete` (create lives elsewhere — likely modal or another flow).
- **Connects to:** **Massive reach** — referenced by 10+ pages (Multi-Repo Fan-Out, Inline Prompt Editor, Visual Cron Wizard, Conditional Trigger Rules, PR Auto-Assignment, GitHub Actions, Bot Recommendation Engine, etc — all are *aspects* of triggers). Also feeds the per-trigger dashboards and per-trigger Trigger History.
- **Last touched:** 2026-04-12 (`a7b0b81`).
- **Inbound refs:** 10.

---

## 9. Integrations submenu

### Slack Notifications (route: `slack-notifications` → `views/SlackNotificationsPage.vue`)

- **What it is:** Slack notification integration CRUD (`integrationApi.create/list/update/test`).
- **Inbound refs:** 0.
- **Last touched:** 2026-03-19 — TS sweep.

### PR Auto-Assignment (route: `pr-auto-assignment` → `views/PrAutoAssignmentPage.vue`)

- **What it is:** Ownership rules for auto-assigning PR reviewers (`prAssignmentApi.*`). Logically a PR-Review-trigger configuration, not a generic integration.
- **Inbound refs:** 0.
- **Last touched:** 2026-03-16.

### Integration Ticketing (route: `integration-ticketing` → `views/IntegrationTicketing.vue`)

- **What it is:** JIRA/Linear-style ticketing integration CRUD (`integrationApi.create/list/update`).
- **Inbound refs:** 0.

### Multi-Provider Fallback (route: `multi-provider-fallback` → `views/MultiProviderFallback.vue`)

- **What it is:** Per-trigger fallback chain across LLM providers (`orchestrationApi.*`, `triggerApi.list`). **Not really an integration** — it's trigger orchestration config.
- **Inbound refs:** 0.

### Multi-Repo Fan-Out (route: `multi-repo-fan-out` → `views/MultiRepoFanOut.vue`)

- **What it is:** Fan a trigger out to many GitHub repos (`triggerApi.addGitHubRepo/addPath/...`). **Trigger config**, not an integration.
- **Inbound refs:** 0.

### GitHub Actions (route: `github-actions` → `views/GitHubActionsPage.vue`)

- **What it is:** Generate YAML to embed Agented bot analysis in CI/CD pipelines.
- **Inbound refs:** 0.

### On-Call Escalation (route: `on-call-escalation` → `views/OnCallEscalation.vue`)

- **What it is:** Account rotation on-call view (`rotationApi.getHistory/getStatus`). **Same data as Scheduling dashboard.**
- **Inbound refs:** 0.

### PR Review Learning Loop (route: `pr-review-learning-loop` → `views/PrReviewLearningLoopPage.vue`)

- **What it is:** Signals + refinement suggestions for the PR Review bot (`prReviewApi.getLearningLoop`). **A facet of PR Review**, not an integration.
- **Inbound refs:** 0.

### Notification Channels (route: `notification-channels` → `views/TeamsNotificationChannelsPage.vue`)

- **What it is:** Per-team notification channel CRUD (`integrationApi.*`, `teamApi.list`). **Overlaps Slack Notifications** in concept.
- **Inbound refs:** 0.

---

## 10. Automation Tools submenu (16 items)

All items below have **inbound refs: 0** — the sidebar is the only path to them. Listing concisely.

| Route | View | What it is | APIs |
|---|---|---|---|
| `bot-recommendation-engine` | BotRecommendationEngine.vue | Suggests trigger config based on effectiveness. | `analyticsApi.fetchEffectiveness`, `triggerApi.list/update` |
| `bot-clone-fork` | BotCloneForkPage.vue | Clone/fork an existing trigger across teams. | `teamApi.list`, `triggerApi.create/list` |
| `bot-dependency-graph` | BotDependencyGraph.vue | Graph of agent ↔ team ↔ trigger relationships. | `agentApi.list`, `teamApi.list`, `triggerApi.list` |
| `changelog-generator` | ChangelogGenerator.vue | Generate a changelog from execution analytics. | `analyticsApi.fetchExecutionAnalytics`, `executionApi.listAll` |
| `incident-response-playbooks` | IncidentResponsePlaybooksPage.vue | Deploy bot templates as incident playbooks. | `botTemplateApi.*` |
| `dependency-impact-bot` | DependencyImpactBot.vue | Per-trigger recent-runs summary scoped to dep changes. | `executionApi.listForBot`, `triggerApi.list` |
| `cross-team-bot-sharing` | CrossTeamBotSharing.vue | Share a bot across teams. | `teamApi.list`, `triggerApi.list` |
| `inline-prompt-editor` | InlinePromptEditor.vue | Edit a trigger's prompt inline. | `triggerApi.get/list/update` |
| `prompt-ab-testing` | PromptABTesting.vue | A/B test two trigger prompts. | `analyticsApi.fetchExecutionAnalytics`, `triggerApi.create/list/update` |
| `structured-output` | StructuredOutputPage.vue | Define a JSON schema bot outputs must conform to. | *(static)* |
| `visual-cron-wizard` | VisualCronWizard.vue | Visual cron builder for a trigger. | `triggerApi.list/update` |
| `conditional-trigger-rules` | ConditionalTriggerRulesPage.vue | When-to-fire rules per trigger. | `triggerConditionsApi.*` |
| `bot-runbooks` | BotRunbooksPage.vue | Static runbooks per bot. | *(no API)* |
| `repo-scope-filters` | RepoScopeFiltersPage.vue | File-path scope filters. | `scopeFiltersApi.*` |
| `bot-performance-benchmarks` | BotPerformanceBenchmarksPage.vue | Benchmark dashboard. | `analyticsApi.fetchEffectiveness`, `fetchExecutionAnalytics` |
| `smart-schedule-optimizer` | SmartScheduleOptimizerPage.vue | Schedule optimizer view. | `schedulerApi.*` |
| `execution-tagging` | ExecutionTaggingPage.vue | Tag executions and CRUD tags. | `executionTaggingApi.*` |

**Common observation:** ~13 of these 17 are *trigger-aspect* pages built on `triggerApi` or `analyticsApi`. They overlap with each other, with Triggers, and with Analytics/Dashboards.

**Recency:** All last touched 2026-03-16…2026-03-20 (the original wave of Automation Tools features) except `bot-clone-fork` and `cross-team-bot-sharing` (2026-05-10 — dead-route fix sweep). **Most look stale.**

---

## 11. Bot Templates (flat link)

### Bot Templates (route: `bot-templates` → `views/BotTemplateMarketplace.vue`)

- **What it is:** Marketplace of pre-built bot configurations + a "Create Bot from Description" NL form. Deploys templates as new triggers.
- **Shows:** Template gallery.
- **Enables:** `botTemplateApi.list/deploy`, `triggerApi.create`.
- **Connects to:** Triggers (deploys to), Incident Response Playbooks (uses same `botTemplateApi`).
- **Last touched:** 2026-03-05 (`302bd87`) — original add.
- **Inbound refs:** 0. **Stale.**

### Prompt Snippets (route: `prompt-snippets` → `views/PromptSnippetLibrary.vue`)

- **What it is:** "Reusable prompt fragments that can be included in any bot template." CRUD on snippets.
- **Shows:** Snippet list + edit/create modal.
- **Enables:** `promptSnippetApi.create/list/update/delete`.
- **Connects to:** Bot Templates (target consumer), Inline Prompt Editor (sibling concept).
- **Last touched:** 2026-05-10 (`cfe3da5`) — Escape-to-close modal sweep.
- **Inbound refs:** 0.

---

## 12. History

### Triggers (route: `security-history` → `views/AuditHistory.vue`, plus per-trigger `trigger-history`)

- **What it is:** Trigger run history. The **Security Scan** built-in trigger has a hard-coded `security-history` route that re-uses the **AuditHistory.vue** view (same component as `audit-history`). Per-custom-trigger entries route to `trigger-history` → `views/GenericTriggerHistory.vue`.
- **Shows:** Filterable history list, project filter (`auditApi.getHistory/getProjects`).
- **Enables:** Drill into a specific run.
- **Connects to:** Audit Log (literally the same view), Security Dashboard, Findings Triage Board, Audit Detail.
- **Last touched:** 2026-05-10 (`f5518f5`).
- **Inbound refs:** 1 (security-history), 1 (audit-history).

### Audit Log (route: `audit-history` → `views/AuditHistory.vue`)

- **What it is:** **Same component** as security-history above. Two routes, one view. The sidebar calls it "Audit Log" and the History → Triggers calls it "Security Scan".
- **Enables:** Same as above.
- **Inbound refs:** 1.

### Replay & Diff (route: `execution-replay-diff` → `views/ExecutionReplayDiff.vue`)

- **What it is:** Re-run an execution and diff it against a previous run.
- **Shows:** Executions list, replay creation, comparisons, diff viewer.
- **Enables:** `replayApi.create/getDiff/getComparisons`, `executionApi.listAll`.
- **Connects to:** Execution Search, Live Execution Terminal, Execution Timeline (execution-domain cluster).
- **Last touched:** 2026-03-19 (`bba509e`) — TS sweep.
- **Inbound refs:** 1.

### Webhook Recorder (route: `webhook-recorder` → `views/WebhookRecorder.vue`)

- **What it is:** Record and replay webhook deliveries. Reads executions and triggers.
- **Shows:** Execution list, trigger list.
- **Enables:** `triggerApi.run` (replay).
- **Connects to:** Triggers domain.
- **Last touched:** 2026-03-19 (`bba509e`).
- **Inbound refs:** 0.

### Annotations (route: `execution-annotation` → `views/ExecutionAnnotation.vue`)

- **What it is:** Add human annotations to past executions. Only `executionApi.listAll` in script setup — likely thin.
- **Shows:** Execution list with annotation UI.
- **Last touched:** 2026-03-19 (`bba509e`).
- **Inbound refs:** 0.

---

## 13. Execution Search (flat link, just below History)

### Execution Search (route: `execution-search` → `views/ExecutionSearchPage.vue`)

- **What it is:** Search across execution logs (`specializedBotApi.searchLogs`).
- **Shows:** Search results.
- **Enables:** Full-text execution search.
- **Connects to:** Execution domain (replay, queue, timeline, file-diff, time-travel-debugger — many sibling pages exist but only this one is in the sidebar).
- **Last touched:** 2026-03-19 (`bba509e`).
- **Inbound refs:** 0.

---

## 14. Usage submenu

### Token Usage (route: `usage-history` → `views/UsageHistoryPage.vue`)

- **What it is:** Period-bucketed budget history (`budgetApi.getHistoryStats`). **NOT the same as `token-usage` dashboard** — that one is live/active; this one is historical buckets.
- **Shows:** Weekly/monthly breakdown.
- **Enables:** Read-only.
- **Connects to:** Token Usage dashboard, Team Budgets, Execution Quotas.
- **Last touched:** 2026-03-19 (`bba509e`).
- **Inbound refs:** 0. **Strong overlap with `token-usage`.**

---

## 15. System: AI Backends

### AI Backends (route: `ai-backends` → `views/AIBackendsPage.vue`)

- **What it is:** Backend management — list backends, install CLI, proxy-login, test prompt. The sidebar also lists one entry per backend (dynamic, routes to `backend-detail`).
- **Shows:** Backend cards, install/proxy actions.
- **Enables:** `backendManagementApi.check/installCli/proxyLogin`.
- **Connects to:** ai-accounts sidecar; Token Usage (the OAuth-missing surfacing is shared); per-backend `backend-detail`.
- **Last touched:** 2026-05-19 (`b2c7e90`) — *actively maintained.*
- **Inbound refs:** 0 in `frontend/src` (sidebar-only).

### Per-backend (dynamic, `backend-detail` → `views/BackendDetailPage.vue`)

One row per detected backend. Route includes `:backendId`.

---

## 16. Platform submenu (13 items)

All inbound refs: 0 (sidebar-only paths). Compact table:

| Route | View | What it is |
|---|---|---|
| `secrets-vault` | SecretsVault.vue | Vault for secrets (`secretsApi.create/delete/getStatus/list/reveal`). |
| `rbac-settings` | RbacSettingsPage.vue | Role-based access control + permission matrix (`rbacApi.*`). |
| `sso-settings` | SsoSettingsPage.vue | SSO / SAML config (`settingsApi.get/set`). |
| `team-budgets` | TeamBudgetsPage.vue | Per-team monthly execution limits + alert thresholds. *No API calls in script setup — static so far.* |
| `execution-quota-controls` | ExecutionQuotaControls.vue | Quota rules. *No API calls in script setup.* |
| `report-digests` | ReportDigestsPage.vue | Schedule AI-generated summaries to email/Slack. *No API calls in script setup.* |
| `mobile-execution-monitor` | MobileExecutionMonitor.vue | Mobile-first execution monitor. *No API calls in script setup.* |
| `bot-sla-uptime` | BotSlaUptimePage.vue | Bot SLA & uptime — alert when scheduled bot misses run. *No API calls in script setup.* |
| `api-keys` | ApiKeysPage.vue | API keys — but uses `rbacApi.createRole/deleteRole/listRoles` (?!). The view is named API Keys but reuses RBAC role API. |
| `findings-triage-board` | FindingsTriageBoardPage.vue | Kanban-ish triage of `findingsApi.list/update`. Couples tightly to Security Scan domain. |
| `skill-version-pinning` | SkillVersionPinningPage.vue | Pin skill versions (`versionPinsApi.*`). |
| `conversation-history-viewer` | ConversationHistoryViewer.vue | View an agent's conversation history (`agentApi.list`, `agentConversationApi.get`). |
| `system-errors` | SystemErrorsPage.vue | App errors list. *No API calls in script setup (presumably consumes a store).* |

**Mixed bag:** real platform admin (Secrets, RBAC, SSO, API Keys), trigger/quota concerns that duplicate Token Usage, several static placeholders (Team Budgets, Execution Quotas, Report Digests, Bot SLA, Mobile Monitor), and **two non-platform pages**: Findings Triage (security domain) and Conversation History Viewer (agents domain).

---

## Cross-cutting observations

These are observations from the data, not IA proposals.

### A. Genuine duplicates (same view file or same backend, multiple sidebar rows)

- `security-history` and `audit-history` mount the **same** `AuditHistory.vue`. They appear in two different sidebar sections ("History → Triggers → Security Scan" and "History → Audit Log").
- `project-instance-playground` and `super-agent-playground` mount the **same** `SuperAgentPlayground.vue`. The former is project-scoped, the latter SA-scoped. Same component, two URL spaces.
- `token-usage` (live dashboard) and `usage-history` (period buckets) are two surfaces over the **same `budgetApi`**.
- `health-dashboard` (org-wide via `analyticsApi`) and `bot-health` (per-bot via `botHealthApi`) — different APIs, but the user-facing concept ("how healthy are my bots?") is one. Both live under Dashboards.
- Four "Explore X" pages (`explore-plugins`, `explore-skills`, `explore-mcp-servers`, `explore-super-agents`) all rebuild the same marketplace-registry UI. Settings → Add Marketplace is a fifth copy.
- `scheduling` (Scheduling Dashboard) and `on-call-escalation` both read `rotationApi.getHistory/getStatus` — same data, two pages.

### B. Pages that are really facets of "Trigger"

The **Triggers** entity has roughly 17 dedicated sidebar destinations spread across Forge/Integrations/Automation Tools/History/Dashboards:

- Trigger CRUD: `triggers`, `bot-clone-fork`, `cross-team-bot-sharing`, `bot-templates`, `incident-response-playbooks`.
- Trigger config: `inline-prompt-editor`, `visual-cron-wizard`, `conditional-trigger-rules`, `multi-provider-fallback`, `multi-repo-fan-out`, `repo-scope-filters`, `structured-output`, `prompt-ab-testing`, `pr-auto-assignment`.
- Trigger ops: `webhook-recorder`, `dependency-impact-bot`, `bot-recommendation-engine`.
- Trigger introspection: `bot-dependency-graph`, `bot-performance-benchmarks`, `bot-runbooks`, `execution-tagging`, `changelog-generator`.
- Trigger dashboards: per-trigger dashboard (dynamic), `security-dashboard`, `pr-review-dashboard`, plus History submenu.

Triggers are de facto the platform's central abstraction in this UI; the IA does not currently reflect that.

### C. "Integrations" is a misnomer

Of the 9 Integrations entries, only 3 are real integrations (Slack, Ticketing, Notification Channels — and the latter two overlap). The other 6 are PR-Review-trigger facets (PR Auto-Assignment, PR Review Learning Loop, GitHub Actions), rotation-domain (On-Call Escalation), or trigger orchestration (Multi-Provider Fallback, Multi-Repo Fan-Out).

### D. Wizards are a cross-cutting pattern

Six pages follow the same "chat-driven design wizard" pattern with very similar copy:

- `agent-create`, `skill-create`, `command-design`, `hook-design`, `rule-design`, `plugin-design`.

All were touched in the v0.7.79–v0.7.90 wave. They sit under their respective forge entities, not as a coherent "Design" surface.

### E. Active vs stale (rough triage)

**Actively maintained (touched May 2026):**
- SuperAgents page (`d73847b`, Ouroboros work), Token Usage (`b2c7e90`), AI Backends (`b2c7e90`), Agent/Skill/Command/Hook/Rule wizards, Plugin Design wizard, Sketch (formatter sweep), several Forge CRUD pages (modal-close, double-submit sweeps).

**Last touched March 2026 (mostly the original IA pass, TS-error sweep only since):**
- Most of Automation Tools, most of Integrations, Webhook Recorder, Annotations, Execution Search, Execution Replay & Diff, Analytics Dashboard, Health Monitor, Anomaly Detection, ROI Leaderboard, Bot Templates, Findings Triage Board, Skill Version Pinning, Conversation History Viewer, Harness Integration, Explore MCP Servers, Explore Skills, SSO, Secrets Vault, several Platform admin pages.

The pattern is clear: post-March all energy went into SuperAgents, the design wizards, modal/UX hardening, and Token Usage / AI Backends. The bulk of Automation Tools and Integrations has not been touched substantively since v0.5.x.

### F. Pages with **no `triggerApi`/`agentApi`/`teamApi` calls** in script setup (static / placeholder smell)

- `team-leaderboard` (no API calls)
- `execution-anomaly-detection` (no API calls)
- `team-budgets`, `execution-quota-controls`, `report-digests`, `mobile-execution-monitor`, `bot-sla-uptime`, `system-errors`, `structured-output`, `bot-runbooks` (no API calls — empty-state-only).

### G. Hierarchy & domain map (as observed, not proposed)

```
Products ── owns ──► Projects ── owns ──► Triggers
                       │                    │
                       ├─ planning page     ├─ history, dashboards, configs, ...
                       └─ SA Instances ◄────┘ (executions)
                                                 │
                       Teams ── members ──► Agents (subagents)
                       Teams ── lead by ──► Agent
                       Teams ── responsible-for ──► Products/Projects

SuperAgents ── attached-to ──► Projects (as Instances)
SuperAgents ── used-by ──► Workflow Playground (the only Forge consumer)

Forge entities (Plugins, MCP Servers, Skills, Commands, Hooks, Rules) ──► Harness config (Harness Integration)
Forge entities ◄── marketplaces ◄── Settings → Add Marketplace
                                ◄── Explore Plugins / Skills / MCP Servers / SuperAgents

Triggers ── analyzed-by ──► Analytics / Dashboards / Token Usage
Triggers ── configured-by ──► (most of Automation Tools + most of Integrations)
Triggers ── delivered-via ──► Webhook Recorder, Slack, Ticketing, GitHub Actions

AI Backends + ai-accounts sidecar ──► identity for everything that calls an LLM
```

### H. Per-trigger dashboards and per-trigger histories

These are dynamic: `customTriggers` from props produces one sidebar row per trigger under Dashboards (→ `trigger-dashboard`) and another under History → Triggers (→ `trigger-history`). They are **the only navigation entries that scale with user-created entities**. Per-project and per-backend rows also exist (Projects shows per-project rows with instance expansion; AI Backends shows per-backend rows). Per-product, per-team, per-agent, per-SuperAgent rows do **not** appear in the sidebar — those entities are reached only via their list page.
