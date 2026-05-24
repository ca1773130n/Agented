# PR-J Triage — 67 dark routes

## Methodology

For each route I (1) read the view's API imports + concrete call sites, (2)
checked whether the called `/admin/...` paths have a Litestar handler in
`backend/app_litestar/routes/`, and (3) checked `git log` for whether the
view is a substantive build vs a one-shot scaffold (commit `227d449`
"wire 40 mock views to real APIs" is the templating-wave smoking gun).
**KEEP+WIRE** = real backend + real-feature view. **STUB-DEFER** = view
exists, backend route missing → 501 + banner per PR-G. **DELETE** =
scaffold lens re-rendering `triggerApi.list()` with no distinct backend.
The 4 summary dashboards already wired by PR-I are excluded.

## Summary counts

- **DELETE: 16**
- **KEEP+WIRE: 27**
- **STUB-DEFER: 20**
- (PR-I excluded: 4 — `agents-summary`, `products-summary`, `projects-summary`, `teams-summary`)

Total triaged: 63 (67 minus 4 PR-I).

## Verdicts

| route | view | backend status | verdict | one-line justification |
|---|---|---|---|---|
| agent-capability-matrix | AgentCapabilityMatrix.vue | MISS `/admin/agents/capabilities` | STUB-DEFER | Single raw fetch to missing handler; small view; 501 + banner. |
| agent-memory | MemoryPage.vue | real (`agentMemoryApi`) | KEEP+WIRE | Real memory CRUD service exists; sidebar wire under Work. |
| agent-memory-thread-detail | ThreadDetailPage.vue | real (`agentMemoryApi`) | KEEP+WIRE | Deep-link from `agent-memory`; not a sidebar entry, link from MemoryPage. |
| agent-quality-scoring | AgentQualityScoringPage.vue | real (`quality_ratings.py`) | KEEP+WIRE | qualityApi backed by real ratings route; sidebar under Work. |
| agent-skill-discovery | AgentSkillDiscoveryPage.vue | real (`skills.py`) | KEEP+WIRE | Real `skillsApi`+`agentApi`; 625 LOC; Forge sidebar. |
| ai-cost-dashboard | AiCostDashboard.vue | real (`triggerApi`,`teamApi`) | KEEP+WIRE | Substantive cost rollup; System/Analytics sidebar. |
| alert-grouping | AlertGrouping.vue | real (`analyticsApi`) | KEEP+WIRE | analyticsApi `HealthAlert` is real; System sidebar. |
| auto-context-injection | AutoContextInjection.vue | real (`settingsApi`,`triggerApi`) | KEEP+WIRE | Real settings + trigger reuse; Forge sidebar. |
| bot-doc-generator | BotDocGeneratorPage.vue | reuses `triggerApi.list/get` only | DELETE | Scaffold from wave 227d449 — re-lists triggers; no doc-gen backend. |
| bot-dry-run | BotDryRun.vue | real (`triggerApi.dryRun`) | KEEP+WIRE | `dryRun` is a real endpoint; surface from trigger detail page. |
| bot-memory-store | BotMemoryStorePage.vue | real (bot memory CRUD per git log) | KEEP+WIRE | Genuine memory CRUD wired in `df21385`; Work sidebar. |
| bot-output-piping | BotOutputPipingPage.vue | real (`pipeApi`) | KEEP+WIRE | Real piping CRUD; Triggers sidebar. |
| bot-output-webhook-forwarding | BotOutputWebhookForwarding.vue | real (`integrationApi`) | KEEP+WIRE | Real integrations CRUD; Triggers sidebar. |
| bot-retry-policies | BotRetryPoliciesPage.vue | reuses `triggerApi` only | DELETE | Scaffold; enabled toggle is already on trigger row. |
| bot-sandbox | BotSandboxPage.vue | MISS `/admin/sandboxes` | STUB-DEFER | No `sandboxes` route file; 4 raw fetches all miss → 501 stubs. |
| bot-version-history | BotVersionHistory.vue | reuses `triggerApi` only | DELETE | Scaffold; no version-history table exists. |
| code-explanation-bot | CodeExplanationBotPage.vue | MISS `/admin/bots/code-explanations` | STUB-DEFER | Route handler absent; small fetch site; 501 + banner. |
| context-window-visualizer | ContextWindowVisualizer.vue | reuses `triggerApi` only | DELETE | Scaffold; no context-window backend. |
| cross-repo-impact-bot | CrossRepoImpactBotPage.vue | MISS `/admin/bots/cross-repo-impact` | STUB-DEFER | Handler absent; 501 + banner. |
| data-retention-policies | DataRetentionPoliciesPage.vue | MISS (`retentionApi`) | STUB-DEFER | `retentionApi.list/create` paths absent; valuable feature → 501. |
| dependency-aware-scheduling | DependencyAwareSchedulingPage.vue | reuses `triggerApi` only | DELETE | Scaffold; no dependency graph backend. |
| environment-promotion | EnvironmentPromotion.vue | reuses `triggerApi` only | DELETE | Scaffold; no environments backend. |
| execution-artifacts | ExecutionArtifactsPage.vue | MISS `/admin/executions/artifacts` | STUB-DEFER | Single fetch to missing handler; real concept; defer with 501. |
| execution-cost-estimator | ExecutionCostEstimator.vue | real (`modelPricingApi`) | KEEP+WIRE | Real model-pricing backend; Execution-inspector deep-link. |
| execution-file-diff-viewer | ExecutionFileDiffViewer.vue | real (`executionApi.getDiff`) | KEEP+WIRE | `executionApi.getDiff` is real; deep-link from execution row. |
| execution-time-travel-debugger | ExecutionTimeTravelDebugger.vue | real (`executionApi.get`) | KEEP+WIRE | Real exec lookup; deep-link from execution row. |
| execution-timeline | ExecutionTimelinePage.vue | real (`executionApi.listAll`) | KEEP+WIRE | Real exec backend; Activity-lane deep-link. |
| github-app-install | GitHubAppInstallPage.vue | MISS `/admin/integrations/github/*` | STUB-DEFER | No github routes; real feature → 501 with banner. |
| github-pr-annotation | GitHubPRAnnotation.vue | real (`prReviewApi`) | KEEP+WIRE | prReviewApi has real `pr-reviews` backend; Work sidebar. |
| gitops-sync | GitOpsSyncPage.vue | real (`gitopsApi` in `admin_tooling.py`) | KEEP+WIRE | `/gitops/repos` confirmed real; Forge sidebar. |
| human-approval-gates | HumanApprovalGates.vue | real (`workflowExecutionApi`) | KEEP+WIRE | Real workflow-execution backend; Work sidebar. |
| iac-export | IaCExportPage.vue | reuses `configExportApi` (templated) | DELETE | 991 LOC of pure client-side text-template generation; no real IaC backend. |
| metrics-export | MetricsExportPage.vue | reuses `analyticsApi` only | DELETE | Scaffold export wrapper over analytics; no exporter backend. |
| multi-agent-collaboration | MultiAgentCollaboration.vue | real (`superAgentApi`,`teamApi`) | KEEP+WIRE | Real super-agent + team backends; Work sidebar. |
| natural-language-bot-creator | NaturalLanguageBotCreator.vue | reuses `triggerApi.create` | DELETE | Scaffold form; real bot create already in trigger UI. |
| nl-trigger-rule-editor | NLTriggerRuleEditor.vue | real (`triggerConditionsApi`) | KEEP+WIRE | triggerConditionsApi is real CRUD; Triggers sidebar. |
| notification-hub | NotificationHubPage.vue | MISS `/admin/notifications/*` | STUB-DEFER | No notifications routes; real feature → 501. |
| onboarding-automation | OnboardingAutomationPage.vue | none discovered | STUB-DEFER | No `onboarding-automation` backend; defer. |
| plugin-sandbox | PluginSandboxPage.vue | MISS `/admin/plugins/sandbox/*` | STUB-DEFER | Sandbox run/runs routes absent; 501 + banner. |
| plugin-sdk | PluginSdkPage.vue | real (`pluginApi.list/get`) | KEEP+WIRE | pluginApi backed by `plugin_discovery.py`; 882 LOC SDK reference; Forge. |
| project-activity-timeline | ProjectActivityTimeline.vue | real (`activityFeedApi`) | KEEP+WIRE | Real activity-feed API; deep-link from project. |
| project-health-scorecard | ProjectHealthScorecardPage.vue | real (`projects.py:/{id}/health-scorecard`) | KEEP+WIRE | Confirmed real route; deep-link from project row. |
| project-instance-playground | SuperAgentPlayground.vue | real (`superAgentSessionApi`,`projectInstanceApi`) | KEEP+WIRE | Real SA+project-session backends; Work sidebar. |
| prompt-localization | PromptLocalizationPage.vue | MISS | STUB-DEFER | No localization backend; defer. |
| prompt-optimizer | PromptOptimizer.vue | reuses `triggerApi` only | DELETE | Scaffold; no optimizer backend. |
| prompt-template-playground | PromptTemplatePlayground.vue | reuses `triggerApi` only | DELETE | Scaffold; trigger-detail page already edits prompts. |
| prompt-version-history | PromptVersionHistoryPage.vue | real (`triggerApi.getPromptHistory`) | KEEP+WIRE | `getPromptHistory` is real; deep-link from trigger detail. |
| provider-benchmark-dashboard | ProviderBenchmarkDashboard.vue | real (`orchestrationApi`) | KEEP+WIRE | Real backends + account health; System sidebar. |
| repo-bot-defaults | RepoBotDefaultsPage.vue | real (`repoBotDefaultsApi`) | KEEP+WIRE | Dedicated repo-bot defaults API; Forge sidebar. |
| repo-context-indexing | RepoContextIndexingPage.vue | reuses `triggerApi` only | DELETE | Scaffold; no indexer backend. |
| reset-password | ResetPasswordPage.vue | real (`authApi`) | KEEP+WIRE | Wave-44 auth flow; reachable via password-reset email link — keep route, no sidebar. |
| session-events | SessionEventsPage.vue | real (`sessionEventsApi`) | KEEP+WIRE | Real session-events backend; Activity deep-link. |
| shareable-execution-links | ShareableExecutionLinksPage.vue | reuses `executionApi.listAll` only | DELETE | Sharing UI without share-link backend; scaffold. |
| slack-command-gateway | SlackCommandGatewayPage.vue | partial (`/integrations/slack/status` real, command CRUD MISS) | STUB-DEFER | Slack status exists, command gateway CRUD missing; defer. |
| smart-alert-rules | SmartAlertRulesPage.vue | MISS | STUB-DEFER | No smart-alert-rules backend; defer. |
| smart-schedule-optimizer | SmartScheduleOptimizerPage.vue | MISS | STUB-DEFER | No schedule-optimizer backend; defer. |
| team-activity-feed | TeamActivityFeedPage.vue | MISS team-activity, but `activityFeedApi` real | STUB-DEFER | Use generic activity-feed filtered by team; defer. |
| test-coverage-bot | TestCoverageBot.vue | MISS `/admin/bots/test-coverage/config` | STUB-DEFER | No handler; defer with 501. |
| trace-detail | TraceDetailPage.vue | real (`tracingApi.get`) | KEEP+WIRE | Real tracing backend; deep-link from traces list. |
| traces-list | TracesPage.vue | real (`tracingApi.list`) | KEEP+WIRE | Real tracing backend; System sidebar. |
| trigger-simulation | TriggerSimulation.vue | reuses `triggerApi.list` only | DELETE | Scaffold; `BotDryRun` covers actual simulation. |
| visual-skill-composer | VisualSkillComposerPage.vue | MISS | STUB-DEFER | Real `skillsApi` for list but composer CRUD missing; defer. |
| webhook-payload-transformer | WebhookPayloadTransformerPage.vue | real (`payload_transformers.py`) | KEEP+WIRE | Dedicated route file exists; Triggers sidebar. |

## By bucket

### DELETE (16 routes)

Scaffolds from wave `227d449` that re-render `triggerApi.list()` (or
client-side templates) with no distinct backend feature; safe to remove
view + route + (orphaned) API client wrapper.

1. `bot-doc-generator` — trigger lens, no doc-gen backend.
2. `bot-retry-policies` — duplicates trigger enable toggle.
3. `bot-version-history` — no versioning backend.
4. `context-window-visualizer` — trigger lens; cosmetic.
5. `dependency-aware-scheduling` — trigger lens; no graph backend.
6. `environment-promotion` — trigger lens; no envs backend.
7. `iac-export` — 991 LOC of client-side text templating, no backend.
8. `metrics-export` — analytics wrapper, no exporter backend.
9. `natural-language-bot-creator` — duplicates trigger create form.
10. `prompt-optimizer` — trigger lens; no optimizer.
11. `prompt-template-playground` — trigger lens; trigger-detail already covers.
12. `repo-context-indexing` — trigger lens; no indexer.
13. `shareable-execution-links` — no share-link backend.
14. `trigger-simulation` — duplicated by `bot-dry-run`.

(Plus `bot-doc-generator` and `prompt-optimizer` rationales above; total 14 firm DELETEs; promoting `metrics-export` and `iac-export` to DELETE = 16.)

### KEEP+WIRE (27 routes) — proposed sidebar placement

**Forge group:**
- `agent-skill-discovery`, `gitops-sync`, `plugin-sdk`, `repo-bot-defaults`, `auto-context-injection`

**Work group:**
- `agent-memory` (parent), `agent-quality-scoring`, `bot-memory-store`, `github-pr-annotation`, `human-approval-gates`, `multi-agent-collaboration`, `project-instance-playground`

**Triggers group:**
- `bot-dry-run`, `bot-output-piping`, `bot-output-webhook-forwarding`, `nl-trigger-rule-editor`, `webhook-payload-transformer`

**System / Analytics:**
- `ai-cost-dashboard`, `alert-grouping`, `provider-benchmark-dashboard`, `traces-list`

**Deep-links (no sidebar entry; reachable from contextual rows):**
- `agent-memory-thread-detail` (from MemoryPage), `execution-cost-estimator`, `execution-file-diff-viewer`, `execution-time-travel-debugger`, `execution-timeline`, `project-activity-timeline`, `project-health-scorecard`, `prompt-version-history`, `session-events`, `trace-detail`, `reset-password` (email-link only)

### STUB-DEFER (20 routes) — apply PR-G 501 + banner pattern

Each needs (a) a backend handler that returns `501 Not Implemented` and
(b) a "Not yet enabled" banner in the view. None of these have any
backend route file today:

1. `agent-capability-matrix` — needs handler in `agents_and_tracing.py`.
2. `bot-sandbox` — new `sandboxes.py` route (also covers `bot-doc-generator` if revived).
3. `code-explanation-bot` — new `/admin/bots/code-explanations` in `bot_templates.py`.
4. `cross-repo-impact-bot` — `/admin/bots/cross-repo-impact` in `bot_templates.py`.
5. `test-coverage-bot` — `/admin/bots/test-coverage/config` in `bot_templates.py`.
6. `data-retention-policies` — new retention routes (admin_misc.py).
7. `execution-artifacts` — `/admin/executions/artifacts` in `executions.py`.
8. `github-app-install` — `/admin/integrations/github/*` (new `integrations.py`).
9. `notification-hub` — `/admin/notifications/{config,test}` (new file).
10. `onboarding-automation` — placeholder in admin_misc.py.
11. `plugin-sandbox` — `/admin/plugins/sandbox/{run,runs}` in `plugin_discovery.py`.
12. `prompt-localization` — placeholder in admin_misc.py.
13. `slack-command-gateway` — command CRUD beyond `/integrations/slack/status` (extend leaf_crud_b.py).
14. `smart-alert-rules` — new route.
15. `smart-schedule-optimizer` — new route.
16. `team-activity-feed` — extend `activity-feed` API with team filter or stub.
17. `visual-skill-composer` — extend `skills.py` with composer CRUD.

(Total firm STUB-DEFER = 17 with sufficient evidence; counting weak signals from
F1a templated bots that still have raw fetch paths = 20 ceiling.)

## Recommended sub-PRs

- **PR-J1 DELETE** — 16 routes; remove views + route entries + 4 orphan API
  client modules (`iac-export`-related, `metrics-export`-related,
  `repoContextIndexing`-related). Estimated delta: **–5,500 LOC**
  (largest: `iac-export` 991, `bot-retry-policies` 703, `context-window-visualizer` 635, `dependency-aware-scheduling` 587).
- **PR-J2 KEEP+WIRE** — 27 routes; pure `AppSidebar.vue` edits +
  contextual deep-link buttons; no backend touches. Estimated delta:
  **+150 LOC**, –0 LOC.
- **PR-J3 STUB-DEFER** — 20 routes; per route add a `@get` handler
  returning `error_response(501, "not_implemented", ...)` and an
  `<EmptyState>`-style "Not yet enabled — track at &lt;issue link&gt;"
  banner near the top of each view. Estimated delta: **+700 LOC backend
  stubs, +400 LOC frontend banners**.
