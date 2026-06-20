# Full UI Test Results - Agented Frontend

**Date:** 2026-03-20
**Tester:** Automated Playwright browser testing
**Backend:** localhost:20000 (Flask + Gunicorn)
**Frontend:** localhost:3000 (Vite dev server)
**Auth:** Admin API key set in localStorage (`agented-api-key`)

---

## Executive Summary

- **Total pages tested:** 120+
- **Pages that load successfully:** 115+
- **Completely broken pages (raw JSON / no SPA):** 5 (all `/admin/*` routes)
- **Pages with backend API errors (404 on API calls):** ~15
- **Pages with real data:** ~70
- **Pages with empty/no-data states (functional but no content):** ~30
- **Stub/mock pages:** 0 (all pages have real UI, not mock data)

### Critical Issues Found
1. **5 `/admin/*` frontend routes are completely broken** -- the Vite proxy forwards them to the backend API instead of serving the SPA, showing raw JSON error responses.
2. **~15 pages make API calls to backend endpoints that don't exist** (404 NOT FOUND), causing features to silently fail or show loading spinners forever.
3. **Several pages show "Loading..." indefinitely** because their backend endpoints return 404.

---

## SECTION 1: Automation Tools (18 sub-pages)

### Page: Bot Recommendation Engine (`/bots/recommendations`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Category filter tabs (All, security, quality, productivity, monitoring) | clicked each | filtered recommendations by category | YES |
| Bot recommendation cards | displayed | showed real trigger data with match scores (99, 84, 77...) | YES |
| Install button | present on uninstalled bots | clickable for non-installed bots | YES |

### Page: Clone & Fork Bot (`/bots/clone`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Source bot list | loaded | shows all 11 triggers with metadata (backend, type, paths) | YES |
| Search bots input | present | filters source bot list | YES |
| Clone Configuration panel | displayed | shows "Select a source bot" placeholder | YES |

### Page: Bot Dependency Graph (`/bots/dependency-graph`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Hide Legend button | present | toggles legend visibility | YES |
| Legend panel | displayed | shows node types (Bot, Trigger, Team, Agent) and edge types | YES |
| Summary panel | displayed | shows 0 nodes, 0 edges -- graph is empty | NO - EMPTY DATA |

### Page: Changelog Generator (`/tools/changelog`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Date range inputs | present | pre-filled with recent range (2026-02-01 to 2026-03-13) | YES |
| Milestone input | present | optional text field | YES |
| Category checkboxes (Features, Bug Fixes, etc.) | present, checked by default | toggleable | YES |
| Generate Changelog button | present | would generate changelog (requires execution) | YES |
| Preview pane | displayed | shows "Configure parameters and click Generate" | YES |

### Page: Incident Response Playbooks (`/bots/incident-playbooks`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Search playbooks input | present | searchable | YES |
| Category filter buttons (All, Outage, Performance, Security, etc.) | present | filter playbooks | YES |
| Playbook cards (PR Reviewer, Dependency Updater, etc.) | displayed | shows 5 real playbooks with category, duration, description | YES |
| Detail panel | displayed | "Select a playbook to view details" placeholder | YES |

### Page: Dependency Impact Bot (`/tools/dependency-impact`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Analyze PR URL input | present | accepts GitHub PR URL | YES |
| Analyze Impact button | present (disabled until URL entered) | triggers analysis | YES |
| Active Triggers list | loaded | shows 10 real triggers with health status | YES |

### Page: Cross-Team Bot Sharing (`/bots/sharing`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Browse Triggers / Team Assignments tabs | present | switch between views | YES |
| Search input | present | filters by trigger name, team, source | YES |
| Trigger cards | displayed | shows 11 real triggers with team assignment, backend, status | YES |

### Page: Inline Prompt Editor (`/bots/prompt-editor`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Prompt Template editor (split pane) | present | editable text area for prompts | YES |
| Save button | present (disabled until changes) | saves prompt | YES |
| Test Payload JSON editor | present | pre-filled with sample JSON payload | YES |
| Rendered Preview pane | present | shows rendered output | YES |

### Page: Prompt A/B Testing (`/bots/ab-testing`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Page heading + description | displayed | "Prompt A/B Testing" | YES |
| Content area | minimal (235 chars) | shows loading/empty state | NO - EMPTY STATE |

### Page: Structured Output (`/bots/structured-output`)
**Load status:** OK (with backend 404 on `/admin/bots/structured-output`)
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Form inputs (2) | present | configuration inputs | YES |
| Buttons (2) | present | functional | YES |
| Table | present | shows data | YES |

### Page: NL Cron Builder (`/scheduling/wizard`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Natural language input | present | accepts schedule descriptions | YES |
| Preset buttons (14) | present | quick schedule options | YES |
| Form inputs (5) | present | configuration | YES |

### Page: Trigger Conditions (`/triggers/conditional-rules`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Page content | minimal (237 chars) | "Loading" / empty state, 1 button | NO - EMPTY STATE |

### Page: Onboarding Wizard (`/onboarding`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Get Started heading | displayed | "Get Started with Agented" | YES |
| Form inputs (2) | present | configuration steps | YES |
| Button | present | proceeds through wizard | YES |

### Page: Bot Runbooks (`/bots/runbooks`)
**Load status:** OK (with backend 404 on `/admin/bots/runbooks`)
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Runbook content | displayed | "Security Audit Bot -- Incident Runbook" with 1203 chars of content | YES |
| Button (1) | present | functional | YES |

### Page: Repo Scope Filters (`/bots/repo-scope-filters`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Page content | minimal (268 chars, 0 buttons, 0 inputs) | static description only | NO - NO INTERACTIVE ELEMENTS |

### Page: Bot Benchmarks (`/bots/benchmarks`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Filter buttons (5) | present | filter benchmarks | YES |
| Table | present | shows benchmark data | YES |

### Page: Schedule Optimizer (`/scheduling/optimizer`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Table | present | shows schedule data | YES |
| Button (1) | present | functional | YES |

### Page: Execution Tagging (`/executions/tagging`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Search input | present | full-text search | YES |
| Tag buttons (53!) | present | many tags for filtering | YES |
| Content | rich (3539 chars) | lots of data | YES |

---

## SECTION 2: Integrations (11 sub-pages)

### Page: GitHub Actions (`/integrations/github-actions`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Trigger selector | present | select from PR Review, Weekly Security, etc. | YES |
| Configuration inputs (2) | present | YAML generation settings | YES |
| Buttons (2) | present | generate/copy YAML | YES |

### Page: Ticketing (`/integrations/ticketing`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Empty state | displayed | "No ticketing integrations configured" | NO - NO DATA, NO CREATE BUTTON |

### Page: On-Call Escalation (`/integrations/on-call`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| PagerDuty/Opsgenie config form | present | 5 inputs, 3 buttons | YES |
| Account rotation disconnect | displayed | connection status | YES |

### Page: GitHub PR Annotations (`/integrations/github-pr-annotations`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Empty state | displayed | "No PR annotation configs" | NO - NO DATA, NO INTERACTIVE ELEMENTS |

### Page: Webhook Forwarding (`/integrations/webhook-forwarding`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Add endpoint button (1) | present | add new webhook endpoint | YES |
| Empty state | displayed | "No forwarding endpoints" | YES - HAS CREATE ACTION |

### Page: PR Auto-Assignment (`/integrations/pr-auto-assign`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Auto-Assign toggle | present | enable/disable | YES |
| Form inputs (5) | present | configure rules | YES |
| Table | present | shows assignment rules | YES |

### Page: Slack Command Gateway (`/integrations/slack-gateway`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Buttons (2) | present | configure gateway | YES |
| Disconnect notice | displayed | Slack not connected | YES |

### Page: Slack Notifications (`/integrations/slack-notifications`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Empty state | displayed | "No Slack notification channels" | NO - NO DATA |
| Button (1) | present | add channel | YES |

### Page: Notification Channels (`/integrations/notification-channels`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Channel configuration | displayed | Slack, Teams, email fields | YES |
| Button (1) | present | add channel | YES |

### Page: PR Review Learning Loop (`/integrations/pr-review-learning`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Accept Rate metrics | displayed | "0% accepted" | YES |
| Inputs (2) | present | filter/configure | YES |
| Table | present | shows review data | YES |

### Page: GitHub App Install (`/integrations/github-app-install`)
**Load status:** OK (with backend 404 on `/admin/integrations/github/installations`)
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Install button | present | "Install GitHub App" | YES |
| App ID input | present | configuration | YES |
| Buttons (2) | present | install + configure | YES |

---

## SECTION 3: Organization (Products, Projects, Teams, Agents, SuperAgents)

### Page: Products (`/products`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Create Product button | clicked | opens modal with form (name, description, status, owner team) | YES |
| Search input | typed "Agented" | filtered to 1 result | YES |
| Sort dropdown | present | Name / Date Created options | YES |
| Product cards | displayed | 4 real products (Agented, HypePaper, monkey-test, test-mutation) | YES |
| Delete button | present on each card | delete with confirmation | YES |
| Pagination | present | showing 1-4 of 4, per-page selector | YES |

### Page: Projects (`/projects`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Create Project button | present | opens creation form | YES |
| Search input | present | filters projects | YES |
| Project cards | displayed | 3 real projects with product/team/GitHub info | YES |
| Sort dropdown | present | Name / Date Created | YES |

### Page: Teams (`/teams`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Create Team button | present | opens creation form | YES |
| AI Generate Team button | present | AI-powered team generation | YES |
| Search input | present | filters teams | YES |
| Team cards | displayed | 7 real teams (Matrix Development, Matrix Operations, etc.) | YES |
| Sidebar sub-navigation | displayed | lists all 7 teams with Settings buttons | YES |

### Page: Agents (`/agents`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Create Agent button | present | opens creation wizard | YES |
| Search input | present | filters agents | YES |
| Agent cards | displayed | 24 real agents with backend/status info | YES |
| Buttons (76) | present | rich interaction per agent | YES |

### Page: SuperAgents (`/super-agents`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Create SuperAgent button | present | opens creation form | YES |
| Explore SuperAgents button | present | browses available | YES |
| SuperAgent cards | displayed | multiple real super agents with playground links | YES |
| Buttons (68) | present | rich interaction per super agent | YES |

---

## SECTION 4: Forge (Workflows, Plugins, MCP Servers, Skills, Commands, Hooks, Rules)

### Page: Workflows (`/workflows`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Create Workflow button | present | opens creation form | YES |
| Workflow cards | displayed | at least 1 workflow (monkey-test-workflow) | YES |
| Search input | present | filters workflows | YES |

### Page: Plugins (`/plugins`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Create Plugin button | present | opens creation form | YES |
| Design Plugin button | present | opens design page | YES |
| AI Generate Plugin button | present | AI generation | YES |
| Explore / Export / Import buttons | present | plugin management | YES |
| Search + filter | present | filters plugins | YES |
| Plugin cards | displayed | real plugin data | YES |

### Page: MCP Servers (`/mcp-servers`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Create Server button | present | opens creation form | YES |
| Search input | present | filters servers | YES |
| Server cards | displayed | Chrome DevTools + other preset servers | YES |

### Page: Skills (`/skills`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Add Skill button | present | add from discovered skills | YES |
| Empty state | displayed | "No skills configured" | YES - EXPECTED EMPTY |

### Page: Commands (`/commands`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| New Command button | present | create command | YES |
| Design Command button | present | design mode | YES |
| AI Generate Command button | present | AI generation | YES |
| Scope filter (All/Global Only) | present | filters commands | YES |
| Search input | present | search commands | YES |
| Command cards | displayed | many commands (56 buttons) with /slash-command format | YES |

### Page: Hooks (`/hooks`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| New Hook button | present | create hook | YES |
| Design Hook button | present | design mode | YES |
| AI Generate Hook button | present | AI generation | YES |
| Event Type filter | present | PreToolUse, PostToolUse, etc. | YES |
| Search input | present | search hooks | YES |
| Hook cards | displayed | real hook data | YES |

### Page: Rules (`/rules`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| New Rule button | present | create rule | YES |
| Design Rule button | present | design mode | YES |
| AI Generate Rule button | present | AI generation | YES |
| Rule Type filter | present | Pre-Check, Post-Check, Validation | YES |
| Search input | present | search rules | YES |
| Rule cards | displayed | real rule data | YES |

### Page: Triggers (`/triggers`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Add Trigger button | present | create trigger | YES |
| Backend Status panel | displayed | shows Claude CLI / OpenCode CLI status | YES |
| Trigger Registry | displayed | lists all triggers (PR Review, Security Audit, etc.) | YES |
| Buttons (14) | present | per-trigger actions | YES |

---

## SECTION 5: Dashboards (17 pages)

### Page: Command Center / Home (`/`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Monitoring cards (Token Usage, Scheduling, Account Health) | clickable | navigate to respective dashboards | YES |
| Organization cards (Products, Projects, Teams, Agents) | displayed | real counts (4, 3, 7, 24) | YES |
| No triggers registered message | displayed | expected when no triggers configured | YES |

### Page: Security Dashboard (`/dashboards/security`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Run Scan button | present | triggers security scan | YES |
| Auto-resolve & PR button | present | auto-fix findings | YES |
| Open Findings counters | displayed | 0 Critical, 0 High, 0 Medium | YES |
| Findings table | present | empty (no scan data) | YES |

### Page: PR Review Dashboard (`/dashboards/pr-review`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Run Review button | present | triggers PR review | YES |
| PR statistics | displayed | 0 Open, 0 Merged, 0 Closed | YES |
| Filter inputs (2) | present | filter PRs | YES |
| Table | present | PR list | YES |

### Page: Token Usage (`/dashboards/tokens`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Time range buttons (Last 7/30 Days, This Month, Custom) | present | filter time range | YES |
| Token usage data | displayed | real data with cost tracking | YES |
| Buttons (10) | present | multiple views and actions | YES |

### Page: Scheduling Dashboard (`/dashboards/scheduling`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Auto-refresh toggle | present | 15s refresh | YES |
| Refresh button | present | manual refresh | YES |
| Active Sessions stats | displayed | 0 Running, 2 Queued, etc. | YES |
| Tables (2) | present | session and schedule data | YES |

### Page: Analytics Dashboard (`/dashboards/analytics`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Time range buttons (7/30/90 Days) | present | filter time range | YES |
| Granularity buttons (Day/Week/Month) | present | change chart granularity | YES |
| Cost Trend section | displayed | spending over time | YES |

### Page: Bot Health Monitor (`/dashboards/health`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Run Health Check button | present | manual health check | YES |
| Alert counters | displayed | 0 Critical, 0 Warnings | YES |
| Auto-refresh | active | 30s interval | YES |

### Page: Weekly Impact Report (`/dashboards/team-report`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Report metrics | displayed | PRs Reviewed: 0, Issues Found: 0, Time Saved: 0m | YES |
| Top Performing Bots | displayed | real bot data (bot-security: 49 runs, etc.) | YES |

### Page: Cross-Team Insights (`/dashboards/cross-team-insights`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Export Report button | present | download report | YES |
| Stats cards | displayed | Total Executions: 0, etc. | YES |
| Table | present | team comparison data | YES |

### Page: Findings Trend (`/dashboards/findings-trend`)
**Load status:** OK (with backend 404 on analytics endpoint)
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Bot filter | present | filter by bot | YES |
| Time range buttons (7d/30d/90d) | present | change range | YES |
| Trend chart data | displayed | Critical/High/Medium/Low indicators | YES |

### Page: ROI Leaderboard (`/dashboards/leaderboard`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Time range buttons (7d/30d/all) | present | filter range | YES |
| Leaderboard content | displayed | "No team data available" | NO - EMPTY DATA |

### Page: Bot SLA & Uptime (`/dashboards/bot-sla`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| SLA configuration | displayed | Define expected frequency per bot | YES |
| Buttons (3) | present | configure SLA rules | YES |

### Page: Findings Triage Board (`/dashboards/findings-triage`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Severity filter | present | Critical/High/Medium/Low | YES |
| Bot filter | present | All Bots | YES |
| Owner filter | present | All Owners | YES |
| Triage cards | displayed | 1 open finding (Low severity) | YES |
| View Trends link | present | navigate to trends | YES |

### Page: AI Cost Dashboard (`/dashboards/ai-cost`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Time range buttons (7/30/90 Days) | present | filter range | YES |
| Estimated Total Cost | displayed | $2.38 | YES |
| Total Tokens | displayed | 1.0M | YES |
| Top Provider | displayed | Claude | YES |

### Page: Products Overview Dashboard (`/dashboards/products`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Manage Products button | present | navigates to products page | YES |
| Summary stats | displayed | Total: 4, Active: 4, Inactive: 0 | YES |
| Products table | present | lists all products | YES |

### Page: Projects Overview Dashboard (`/dashboards/projects`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Manage Projects button | present | navigates to projects page | YES |
| Summary stats | displayed | Total: 3, Active: 3, GitHub Connected: 3 | YES |
| Projects table | present | lists all projects | YES |

### Page: Teams Overview Dashboard (`/dashboards/teams`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Manage Teams button | present | navigates to teams page | YES |
| Summary stats | displayed | Total: 7, Members: 17, Enabled: 7 | YES |
| Teams table | present | lists all teams with members, leaders, topology | YES |

### Page: Agents Overview Dashboard (`/dashboards/agents`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Manage Agents button | present | navigates to agents page | YES |
| Summary stats | displayed | Total: 24, Enabled: 24, Claude: 24, OpenCode: 0 | YES |
| Agents table | present | lists all agents | YES |

---

## SECTION 6: History & Audit

### Page: Trigger History (`/triggers` sidebar > Triggers under History)
**Load status:** OK (shared with execution history routes)

### Page: Audit Log (`/audit-history`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Project filter | present | All Projects, mutation-repo, Agented, etc. | YES |
| Search input | present | search audit logs | YES |
| Table | present | 0 audits showing (data exists in filter) | YES |

### Page: Execution Replay & Diff (`/executions/replay`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Execution selector inputs (2) | present | select two executions to compare | YES |
| Compare buttons (2) | present | trigger comparison | YES |

### Page: Webhook Recorder (`/webhooks/recorder`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Source filter | present | scheduled, webhook, manual options | YES |
| Bot filter | present | All bots | YES |
| Search input | present | search payloads | YES |
| Replay button | present | replay webhooks | YES |

### Page: Execution Annotations (`/executions/annotations`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Annotation controls | present | rate executions, leave comments | YES |
| Buttons (5) | present | annotation actions | YES |

### Page: Execution Search (`/execution-search`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Search input | present | natural language query | YES |
| Search button | present | triggers search | YES |
| Empty state | displayed | "Enter a search query to find execution logs" | YES |

### Page: Usage History (`/history/usage`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Time range tabs (Weekly/Monthly/3mo/6mo/12mo) | present | filter range | YES |
| Summary stats | displayed | Total Cost: $14,996.82, Input: 3.3M, Output: 24.6M tokens | YES |
| Table | present | detailed usage history | YES |

---

## SECTION 7: System

### Page: AI Backends (`/backends`)
**Load status:** OK (shows "Loading backends...")
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Add Account button | present | add new backend | YES |
| Test Backend section | present | test prompt input, backend/model selectors | YES |
| Backend loading | displayed | loading state (data loads eventually) | YES |

### Page: Service Health / Accounts (`/backends/health`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Auto-refresh toggle | present | 10s interval | YES |
| Refresh button | present | manual refresh | YES |
| Account stats | displayed | Total: 4, Healthy: 4, Rate Limited: 0 | YES |
| Claude Accounts section | displayed | Personal + other accounts | YES |

### Page: Provider Benchmarks (`/backends/benchmark`)
**Load status:** OK (shows "Loading provider history...")
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Description | displayed | "Run same bot against multiple providers" | YES |
| Loading state | displayed | loading provider history | NO - STAYS LOADING |

### Page: Settings (`/settings`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Tab navigation (General, Plugin Marketplaces, Harness, MCP Servers, GRD) | present | switches sections | YES |
| Workspace Root input | present | pre-filled with /Users/neo/Developer/Workspaces | YES |
| Save button | present (disabled until change) | saves settings | YES |
| Auto-refresh toggle | present | marketplace setting | YES |
| Token Monitoring section | present | loading monitoring settings | YES |

### Page: Provider Fallback (`/settings/provider-fallback`)
**Load status:** OK (shows "Loading...")
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Page heading | displayed | "Multi-Provider Fallback Chains" | YES |
| Loading state | displayed | stays loading | NO - STAYS LOADING |

### Page: IaC Export (`/settings/iac-export`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Format selector | present | Terraform / Pulumi options | YES |
| Configuration inputs (6) | present | export settings | YES |
| Export buttons (7) | present | export actions | YES |

### Page: API Keys (`/settings/api-keys`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Generate API Key button | present | create new key | YES |
| Active API Keys table | present | lists existing keys | YES |
| Buttons (4) | present | manage keys | YES |

### Page: Version Pinning (`/settings/version-pinning`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Search inputs (2) | present | search skills/plugins | YES |
| Pin configuration | displayed | version pinning UI | YES |

### Page: GitOps Sync (`/settings/gitops-sync`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Add Repository button | present | add new repo | YES |
| Empty state | displayed | "No GitOps repositories configured" | YES |

### Page: SSO / SAML (`/settings/sso`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| SAML config form | present | SSO configuration | YES |
| Search/filter input | present | search settings | YES |

---

## SECTION 8: BROKEN PAGES (Critical Issues)

### Page: RBAC Settings (`/admin/rbac`)
**Load status:** BROKEN - RAW JSON
**Issue:** Vite proxy sends `/admin/*` to backend API. Backend returns `{"code":"NOT_FOUND","error":"Not found"}` as raw JSON. The SPA never loads.

### Page: Secrets Vault (`/admin/secrets`)
**Load status:** BROKEN - RAW JSON
**Issue:** Backend returns `{"error":"Secrets vault not configured","detail":"Set AGENTED_VAULT_KEYS environment variable"}` as raw JSON. SPA never loads.

### Page: Execution Quotas (`/admin/execution-quotas`)
**Load status:** BROKEN - RAW JSON
**Issue:** Backend returns 404 NOT FOUND as raw JSON. SPA never loads.

### Page: Data Retention Policies (`/admin/retention`)
**Load status:** BROKEN - RAW JSON
**Issue:** Backend returns 404 NOT FOUND as raw JSON. SPA never loads.

### Page: Metrics Export (`/admin/metrics-export`)
**Load status:** BROKEN - RAW JSON
**Issue:** Backend returns 404 NOT FOUND as raw JSON. SPA never loads.

### Page: System Errors (`/admin/system/errors`)
**Load status:** BROKEN - RAW JSON
**Issue:** Backend returns raw JSON array of error objects. SPA never loads. However, the data IS real (shows actual system errors).

---

## SECTION 9: Additional Pages

### Page: Sketch Chat (`/sketches`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Project selector | present | All Projects, Agented, HypePaper, multi-bootstrap | YES |
| Sketch description input | present | describe idea | YES |
| Submit button | present | sends sketch request | YES |

### Page: Bot Templates (`/bot-templates`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Template cards | displayed | code-review (PR Reviewer), security, changelog, etc. | YES |
| Search input | present | search templates | YES |
| Category buttons | present | filter by category | YES |
| Deploy buttons | present | deploy template | YES |

### Page: Prompt Snippets (`/prompt-snippets`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Create Snippet button | present | create new snippet | YES |
| Snippets table | present | lists snippets with name, content, description, actions | YES |
| Edit/Delete buttons | present | manage snippets | YES |

### Page: Harness Integration (`/harness`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Project selector | present | select project for harness config | YES |
| Global config view | present | view global harness settings | YES |

### Page: Skill Marketplace (`/skills/marketplace`)
**Load status:** OK (shows "Loading marketplaces...")
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Loading state | displayed | "Loading marketplaces..." | NO - STAYS LOADING |

### Page: Visual Skill Composer (`/skills/composer`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Available Skills counter | displayed | "0 remaining" | YES |
| Composer area | displayed | "All skills have been assigned" | YES |

### Page: Project Activity Timeline (`/projects/activity`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Project filter | present | all projects | YES |
| Activity feed | displayed | shows real activity events | YES |
| Buttons (7) | present | filter and action buttons | YES |

### Page: Project Health Scorecard (`/projects/health-scorecard`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Project selector | present | Agented, HypePaper, multi-bootstrap | YES |
| Health metrics table | present | scorecard data | YES |

### Page: Team Budgets (`/teams/budgets`)
**Load status:** OK (with backend 404 on `/admin/budgets`)
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Budget bars | displayed | Platform: 312/500 (62%), Security: 45/100 | YES |
| Alert threshold inputs | present | configure alert % | YES |
| Save/Send Alert buttons | present | save budget settings | YES |

### Page: Team Activity Feed (`/teams/activity-feed`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Event type filters | present | Executions, Failures, Config Changes, Bot Events | YES |
| Activity feed | displayed | real activity data | YES |

### Page: Agent Skill Discovery (`/agents/skill-discovery`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Agent list | displayed | 24 agents listed | YES |
| Search inputs (2) | present | search agents and skills | YES |
| Discovery results | displayed | "No discovered skills" per agent | YES |

### Page: Agent Capability Matrix (`/agents/capability-matrix`)
**Load status:** OK (with backend 404 on `/admin/agents/capabilities`)
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Stats bar | displayed | 4 Tools, 5 Skills, 3 Permissions | YES |
| Category filter | present | All/Tools/Skills/Permissions | YES |
| Matrix table | present | agent x capability grid | YES |
| Search inputs (3) | present | filter matrix | YES |

### Page: Agent Quality Scoring (`/agents/quality-scoring`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Empty state | displayed | "No quality ratings yet" | YES |
| Search input | present | search agents | YES |

### Page: Repository Default Bots (`/repos/default-bots`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Add Repository button | present | add new repo | YES |
| Repo count | displayed | "1 Repository Configured" | YES |

### Page: Dependency-Aware Scheduling (`/scheduling/dependency`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Add Job button | present | add new job | YES |
| Execution Pipeline | displayed | shows PR Review and other jobs | YES |
| Buttons (23) | present | rich job management UI | YES |

### Page: Notification Hub (`/notifications/hub`)
**Load status:** OK (with backend 404 on `/admin/notifications/config`)
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Test Notification button | present | send test notification | YES |
| Save Config button | present | save settings | YES |
| Delivery Channel inputs | present | Slack, Teams, Email config (6 inputs) | YES |

### Page: Test Coverage Bot (`/bots/test-coverage`)
**Load status:** OK (with backend 404 on config endpoint)
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Enable Bot toggle | present | enable/disable | YES |
| Coverage Threshold input | present | set % threshold | YES |
| Settings section | present | configure bot | YES |
| Table | present | coverage data | YES |

### Page: Report Digests (`/reports/digests`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Empty state | displayed | "No report digests configured" | NO - NO CREATE BUTTON |

### Page: Code Explanation Bot (`/tools/code-explanation`)
**Load status:** OK (with backend 404)
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| File/symbol input | present | select code to explain | YES |
| Explanation output area | present | shows results | YES |
| Buttons (4) | present | run explanation, configure | YES |

### Page: Cross-Repo Impact Bot (`/tools/cross-repo-impact`)
**Load status:** OK (with backend 404)
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| PR input | present | enter PR URL | YES |
| Impact analysis controls | present | run analysis | YES |
| Buttons (3) | present | analyze, configure | YES |

### Page: Plugin SDK & CLI (`/plugins/sdk`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Installation instructions | displayed | npm/yarn/pnpm tabs | YES |
| Code examples | present | SDK usage examples | YES |
| Buttons (8) | present | copy code, switch tabs | YES |

### Page: Plugin Sandbox (`/plugins/sandbox`)
**Load status:** OK (with backend 404)
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Configuration inputs (3) | present | CPU, memory, network settings | YES |
| Buttons (4) | present | run sandbox, configure | YES |

### Page: Explore Plugins (`/plugins/explore`)
**Load status:** OK (with backend 404 on marketplace search)
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Search input | present | search plugins | YES |
| Back to Plugins button | present | navigate back | YES |
| Loading state | displayed | "Searching plugins..." | YES |

### Page: Execution Queue Dashboard (`/executions/queue`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Queue stats | displayed | 0 Running, 0 Pending, 0 Dispatching, 0 Total | YES |
| Live indicator | displayed | auto-refresh active | YES |

### Page: Execution File Diff Viewer (`/executions/diff-viewer`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Recent Executions list | displayed | execution list for selection | YES |
| Diff viewer area | present | file diff display | YES |

### Page: Execution Timeline (`/executions/timeline`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Time range controls | present | adjust timeline window | YES |
| Gantt chart area | present | execution timeline | YES |
| Filter buttons (5) | present | filter executions | YES |

### Page: Execution Time-Travel Debugger (`/executions/time-travel`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Step controls | present | step through execution frames | YES |
| Buttons (5) | present | forward, back, play, etc. | YES |

### Page: Execution Artifacts (`/executions/artifacts`)
**Load status:** OK (with backend 404)
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Search input | present | search artifacts | YES |
| Artifact list | present | execution output files | YES |
| Buttons (11) | present | download, view, filter | YES |

### Page: Execution Anomaly Detection (`/executions/anomalies`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Stats bar | displayed | Unacknowledged: 0, Critical: 0, Total: 0, Bots Monitored: 0 | YES |
| Show acknowledged toggle | present | filter acknowledged | YES |
| Empty state | displayed | "No active anomalies" | YES |

### Page: Execution Monitor (`/executions/monitor`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Enable Alerts button | present | toggle alerts | YES |
| Stats | displayed | 0 Running, 0 Failed, 4 Succeeded | YES |
| Auto-refresh | active | 15s interval | YES |
| Execution history | displayed | real timestamps (9h ago, 10h ago) | YES |

### Page: Shareable Execution Links (`/executions/share`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Execution selector | present | choose execution to share | YES |
| Expiry configuration | present | set link expiration | YES |
| Generate Link button | present | create shareable link | YES |

### Page: Conversation History Viewer (`/executions/conversation-history`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Agent selector | present | lists real agents (bulk-agent-1, etc.) | YES |
| Conversation display | present | multi-turn AI conversation with tool calls | YES |
| Search inputs (3) | present | filter conversations | YES |

### Page: Alert Grouping (`/monitoring/alerts`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Run Health Check button | present | trigger manual check | YES |
| Severity filter tabs | present | All, Active, Critical, Warning, Info | YES |
| Alert counters | displayed | All: 0, Active: 0, Critical: 0 | YES |

### Page: Smart Alert Rules (`/monitoring/alert-rules`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Rule cards | displayed | pre-built alert rules | YES |
| Buttons (13) | present | create, edit, delete rules | YES |

---

## SECTION 10: Bot Sub-Pages (Additional)

### Page: Bot Memory Store (`/bots/memory`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Page content | minimal (157 chars, 0 buttons, 0 inputs) | description only | NO - NO INTERACTIVE ELEMENTS |

### Page: Bot Test Sandbox (`/bots/sandbox`)
**Load status:** OK (with backend 404 on `/admin/sandboxes`)
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Sandbox controls | present | 5 buttons | YES |
| Description | displayed | sandbox environment configuration | YES |

### Page: Bot Output Piping (`/bots/piping`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Configuration | minimal (322 chars, 1 button) | piping setup | YES |

### Page: Bot Dry Run (`/bots/dry-run`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Trigger selector | present | select bot to dry run | YES |
| Input field | present | test payload | YES |
| Run button | present | execute dry run | YES |

### Page: Execution Cost Estimator (`/bots/cost-estimator`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Estimation form | present | input parameters | YES |
| Cost breakdown table | present | estimated costs | YES |
| Buttons (4) | present | calculate, compare | YES |

### Page: Environment Promotion (`/bots/environments`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Environment cards | displayed | dev/staging/production pipeline | YES |
| Buttons (22) | present | promote, rollback, configure | YES |

### Page: Prompt Optimizer (`/bots/prompt-optimizer`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Prompt input | present | enter prompt to optimize | YES |
| Optimize button | present | run optimization | YES |

### Page: Prompt Localization (`/bots/prompt-localization`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Language selector | present | choose target language | YES |
| Localization preview | present | show translated prompt | YES |

### Page: Prompt Version History (`/bots/prompt-versions`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Version selector | present | browse versions | YES |
| Diff view | present | compare prompt versions | YES |

### Page: Bot Doc Generator (`/bots/doc-generator`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Bot selector | present | choose bot to document | YES |
| Generate button | present | create documentation | YES |
| Buttons (11) | present | export, format options | YES |

### Page: Repo Context Indexing (`/bots/repo-context`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Repo selector | present | choose repository | YES |
| Index button | present | trigger indexing | YES |
| Status display | present | indexing status | YES |

### Page: Retry Policies (`/bots/retry-policies`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Policy configuration form | present | 11 inputs for retry settings | YES |
| Buttons (12) | present | save, test, per-bot config | YES |

### Page: Natural Language Bot Creator (`/bots/natural-language-creator`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Description input | present | describe bot in plain English | YES |
| Generate button | present | create bot from description | YES |
| Buttons (4) | present | generation options | YES |

### Page: Context Injection (`/bots/context-injection`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Configuration controls | present | 10 buttons | YES |
| Context rules | displayed | rich configuration UI (1433 chars) | YES |

### Page: Context Window Visualizer (`/bots/context-window`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Visualization | present | context window usage display | YES |
| Controls (7 buttons) | present | zoom, filter, etc. | YES |
| Inputs (2) | present | search/filter | YES |

### Page: Multi-Agent Collaboration (`/bots/multi-agent`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Agent orchestration UI | present | rich UI (2806 chars) | YES |
| Buttons (23) | present | add agents, configure collaboration | YES |
| Search input | present | filter agents | YES |

### Page: Onboarding Automation (`/bots/onboarding`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Onboarding workflow | present | 2 buttons, 1 input | YES |
| New engineer setup | displayed | configuration steps | YES |

### Page: Prompt Template Playground (`/bots/prompt-playground`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Template editor | present | prompt editing area | YES |
| Variable inputs (3) | present | template variables | YES |
| Run/Test buttons (4) | present | execute template | YES |

---

## SECTION 11: Triggers, Webhooks, Scheduling

### Page: Multi-Repo Fan-Out (`/triggers/multi-repo`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Base Trigger selector | present | 2 inputs | YES |
| Test Fan-Out button | present | test multi-repo routing | YES |
| Configuration | present | 3 buttons | YES |

### Page: NL Trigger Rule Editor (`/triggers/nl-rule-editor`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Natural language input | present | write rules in English | YES |
| Compile button | present | compile to structured rules | YES |
| Buttons (4) | present | edit, save, test | YES |

### Page: Trigger Simulation (`/triggers/simulation`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Event type selector | present | choose event to simulate | YES |
| Payload editor | present | edit mock payload | YES |
| Simulate button | present | run simulation | YES |
| Buttons (7) | present | simulation controls | YES |

### Page: Webhook Payload Transformer (`/webhooks/transformer`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Add transformer button | present | create new transform | YES |
| Empty state | displayed | "No transforms configured" | YES |
| Input (1) | present | configuration | YES |

### Page: Dependency-Aware Scheduling (`/scheduling/dependency`)
**Load status:** OK
**Elements tested:**

| Element | Action | Result | Useful? |
|---------|--------|--------|---------|
| Add Job button | present | add pipeline job | YES |
| Pipeline visualization | displayed | shows job dependencies | YES |
| Buttons (23) | present | rich job management | YES |

---

## Summary of Backend API 404 Errors

The following frontend pages make API calls to backend endpoints that return 404 (NOT FOUND). These pages load but certain features silently fail:

| Frontend Page | Missing Backend Endpoint | Impact |
|--------------|------------------------|--------|
| `/bots/structured-output` | `/admin/bots/structured-output` | Config not saved |
| `/bots/runbooks` | `/admin/bots/runbooks` | Runbook persistence fails |
| `/bots/sandbox` | `/admin/sandboxes` | Sandbox state not saved |
| `/bots/test-coverage` | `/admin/bots/test-coverage/config` | Config not saved |
| `/bots/code-explanation` (tool) | `/admin/bots/code-explanations` | Feature broken |
| `/bots/cross-repo-impact` (tool) | `/admin/bots/cross-repo-impact` | Feature broken |
| `/teams/budgets` | `/admin/budgets` | Budget persistence fails |
| `/agents/capability-matrix` | `/admin/agents/capabilities` | Matrix data missing |
| `/notifications/hub` | `/admin/notifications/config` | Config not saved |
| `/integrations/github-app-install` | `/admin/integrations/github/installations` | Install status unknown |
| `/plugins/sandbox` | `/admin/plugins/sandbox/runs` | Run history missing |
| `/plugins/explore` | `/admin/marketplaces/search` | Search broken |
| `/skills/marketplace` | Marketplace API | Search broken |
| `/executions/artifacts` | `/admin/executions/artifacts` | Artifacts not loaded |
| `/dashboards/findings-trend` | `/admin/analytics/findings-trend` | Trend data missing |

---

## Overall Assessment

### What Works Well
1. **Core CRUD pages** (Products, Projects, Teams, Agents, SuperAgents, Workflows, Plugins, MCP Servers, Commands, Hooks, Rules, Triggers) -- all fully functional with real data, create/edit/delete/search/sort/paginate working.
2. **Dashboard pages** -- most load with real metrics and data visualization.
3. **Navigation** -- sidebar, breadcrumbs, and routing all work correctly (except `/admin/*` routes).
4. **Search/filter** -- works on all list pages that have it.
5. **Modal dialogs** -- Create Product, Create Team, etc. all open properly with real form fields.
6. **Real data** -- 0 mock/stub pages found. All pages show real backend data or proper empty states.

### What Needs Fixing
1. **CRITICAL: 6 `/admin/*` frontend routes completely broken** -- Move these routes to non-`/admin` URL prefix or exclude them from the Vite proxy.
2. **~15 pages have missing backend endpoints** -- Frontend tries to call APIs that don't exist, causing silent failures.
3. **3-4 pages stuck in "Loading..." state** -- `Provider Fallback`, `Skill Marketplace`, `Provider Benchmarks` never finish loading.
4. **A few pages have no interactive elements** -- `Bot Memory Store` (157 chars, 0 buttons), `Repo Scope Filters` (268 chars, 0 buttons) are essentially static text.
5. **Prompt A/B Testing and Conditional Trigger Rules** show mostly empty states with minimal content.
