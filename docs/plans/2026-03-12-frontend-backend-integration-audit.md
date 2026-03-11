# Frontend-Backend Integration Audit

**Date**: 2026-03-12
**Source**: Codebase exploration triggered by evolve discovery failure

## Context

The GRD evolve command (`--iterations 100 --no-worktree`) failed to discover improvements due to subprocess timeout during the discovery phase. A manual codebase exploration was performed instead, revealing a critical frontend-backend integration gap.

## Key Finding

**166 out of 172 frontend views (96.5%) have zero API integration.** Most views use hardcoded sample data instead of calling real backend endpoints.

## Disconnected Feature Categories

| Category | Disconnected Views | Examples |
|----------|-------------------|----------|
| Bot Management | 28 | BotMemoryStorePage, BotOutputWebhookForwarding, BotRetryPoliciesPage, BotRunbooksPage, BotSandboxPage |
| Execution & Monitoring | 21 | ExecutionAnnotation, ExecutionArtifactsPage, ExecutionQueueDashboard, ExecutionQuotaControls |
| Agent & Team | 15 | AgentCapabilityMatrix, AgentCreateWizard, AgentsPage, TeamBuilderPage, TeamDashboard |
| Settings & Admin | 18 | ApiKeysPage, RbacSettingsPage, SecretsVault, SsoSettingsPage, DataRetentionPoliciesPage |
| Products & Projects | 12 | ProductDashboard, ProjectDashboard, ProjectHealthScorecardPage |
| Dashboards | 11 | AiCostDashboard, TokenUsageDashboard, ServiceHealthDashboard |
| Integrations | 14 | GitHubActionsPage, SlackNotificationsPage, PrAutoAssignmentPage, OnCallEscalation |
| Plugins/Skills | 20 | CommandDesignPage, HookDesignPage, PluginDesignPage, SkillCreateWizard |
| Triggers/Workflows | 16 | TriggerManagement, TriggerSimulation, WorkflowBuilderPage |
| Other | 11 | LiveExecutionTerminal, PromptOptimizer, StructuredOutputPage |

## Backend Routes Without Frontend

Routes exist in the backend but have no or incomplete UI:

- `POST /admin/specialized-bots/:bot_id/health`
- `GET /admin/orchestration/fallback-chains`
- `GET /health-monitor/alerts`
- `GET /admin/config-export`
- `GET /admin/bookmarks`
- `POST /admin/rbac/policies`
- `POST /admin/bulk/operations`
- `POST /admin/campaigns`
- `GET /admin/trigger-conditions`

## Unused Database Tables

Tables with no route or UI access:

1. **webhook_dedup** - Webhook deduplication (internal use only)
2. **execution_queue** - Queue persistence (no route to fetch items)
3. **conversation_branches** - Route exists, UI incomplete
4. **bot_templates** - Route exists, UI doesn't call it
5. **health_alerts** - Route exists, no dashboard
6. **trigger_conditions** - Route exists, no configuration UI

## Resolved Issue

During this session, one concrete issue was identified and fixed:

**TRIGGER_LOG_DIR pollution** - All webhook trigger events (from any trigger) were writing JSON files to `.claude/skills/weekly-security-audit/reports/`, producing hundreds of garbage files. Fixed by:
- Moving generic trigger event logs to `data/trigger_events/`
- Keeping security audit threat reports in the skill-specific directory
- Adding both directories to `.gitignore`

Commit: `278728d` — "fix: separate trigger event logs from security audit reports"

## Recommended Priority for Wiring

1. **Low-hanging fruit**: Views where backend routes already exist but frontend doesn't call them (bot_templates, trigger_conditions, health_alerts, bookmarks, rbac, campaigns, bulk operations)
2. **Core entity pages**: AgentsPage, TeamDashboard, ProductDashboard, ProjectDashboard — these should use existing CRUD APIs
3. **Execution monitoring**: ExecutionQueueDashboard should use the existing execution_queue table
4. **Settings pages**: SecretsVault, RBAC — backend routes exist
5. **New backend needed**: BotMemoryStore, BotRetryPolicies, BotRunbooks, ApiKeys, SSO — require new routes and DB tables
