import type { RouteRecordRaw } from 'vue-router';

export const miscRoutes: RouteRecordRaw[] = [
  // Execution Search
  {
    path: '/execution-search',
    name: 'execution-search',
    component: () => import('../../views/ExecutionSearchPage.vue'),
    meta: { title: 'Execution Search' },
  },
  // Sketch
  {
    path: '/sketches',
    name: 'sketch-chat',
    component: () => import('../../views/SketchChatPage.vue'),
    meta: { title: 'Sketch Chat' },
  },
  // Usage history
  {
    path: '/history/usage',
    name: 'usage-history',
    component: () => import('../../views/UsageHistoryPage.vue'),
    meta: { title: 'Usage History' },
  },
  // AI Backends
  {
    path: '/backends',
    name: 'ai-backends',
    component: () => import('../../views/AIBackendsPage.vue'),
    meta: { title: 'AI Backends' },
  },
  {
    path: '/backends/health',
    name: 'service-health',
    component: () => import('../../views/ServiceHealthDashboard.vue'),
    meta: { title: 'Service Health' },
  },
  {
    path: '/backends/:backendId',
    name: 'backend-detail',
    component: () => import('../../views/BackendDetailPage.vue'),
    props: true,
    meta: { title: 'Backend Detail', requiresEntity: 'backendId' },
  },
  // Hooks
  {
    path: '/hooks',
    name: 'hooks',
    component: () => import('../../views/HooksPage.vue'),
    meta: { title: 'Hooks' },
  },
  {
    path: '/hooks/design/:hookId?',
    name: 'hook-design',
    component: () => import('../../views/HookDesignPage.vue'),
    props: true,
    meta: { title: 'Hook Design' },
  },
  // Commands
  {
    path: '/commands',
    name: 'commands',
    component: () => import('../../views/CommandsPage.vue'),
    meta: { title: 'Commands' },
  },
  {
    path: '/commands/design/:commandId?',
    name: 'command-design',
    component: () => import('../../views/CommandDesignPage.vue'),
    props: true,
    meta: { title: 'Command Design' },
  },
  // Rules
  {
    path: '/rules',
    name: 'rules',
    component: () => import('../../views/RulesPage.vue'),
    meta: { title: 'Rules' },
  },
  {
    path: '/rules/design/:ruleId?',
    name: 'rule-design',
    component: () => import('../../views/RuleDesignPage.vue'),
    props: true,
    meta: { title: 'Rule Design' },
  },
  // Team Budgets
  {
    path: '/teams/budgets',
    name: 'team-budgets',
    component: () => import('../../views/TeamBudgetsPage.vue'),
    meta: { title: 'Team Budgets' },
  },
  // Notification Hub
  {
    path: '/notifications/hub',
    name: 'notification-hub',
    component: () => import('../../views/NotificationHubPage.vue'),
    meta: { title: 'Notification Hub' },
  },
  // GitHub Actions Integration
  {
    path: '/integrations/github-actions',
    name: 'github-actions',
    component: () => import('../../views/GitHubActionsPage.vue'),
    meta: { title: 'GitHub Actions' },
  },
  // Test Coverage Bot
  {
    path: '/bots/test-coverage',
    name: 'test-coverage-bot',
    component: () => import('../../views/TestCoverageBot.vue'),
    meta: { title: 'Test Coverage Bot' },
  },
  // RBAC Settings
  {
    path: '/settings/rbac',
    name: 'rbac-settings',
    component: () => import('../../views/RbacSettingsPage.vue'),
    meta: { title: 'RBAC Settings' },
  },
  // Report Digests
  {
    path: '/reports/digests',
    name: 'report-digests',
    component: () => import('../../views/ReportDigestsPage.vue'),
    meta: { title: 'Report Digests' },
  },
  // Structured Output
  {
    path: '/bots/structured-output',
    name: 'structured-output',
    component: () => import('../../views/StructuredOutputPage.vue'),
    meta: { title: 'Structured Output' },
  },
  // Natural Language Bot Creator
  {
    path: '/bots/natural-language-creator',
    name: 'natural-language-bot-creator',
    component: () => import('../../views/NaturalLanguageBotCreator.vue'),
    meta: { title: 'Natural Language Bot Creator' },
  },
  // Execution Replay & Diff
  {
    path: '/executions/replay',
    name: 'execution-replay-diff',
    component: () => import('../../views/ExecutionReplayDiff.vue'),
    meta: { title: 'Execution Replay & Diff' },
  },
  // Prompt Optimizer
  {
    path: '/bots/prompt-optimizer',
    name: 'prompt-optimizer',
    component: () => import('../../views/PromptOptimizer.vue'),
    meta: { title: 'Prompt Optimizer' },
  },
  // Environment Promotion
  {
    path: '/bots/environments',
    name: 'environment-promotion',
    component: () => import('../../views/EnvironmentPromotion.vue'),
    meta: { title: 'Environment Promotion' },
  },
  // Execution Cost Estimator
  {
    path: '/bots/cost-estimator',
    name: 'execution-cost-estimator',
    component: () => import('../../views/ExecutionCostEstimator.vue'),
    meta: { title: 'Execution Cost Estimator' },
  },
  // Bot Version History
  {
    path: '/bots/:botId/versions',
    name: 'bot-version-history',
    component: () => import('../../views/BotVersionHistory.vue'),
    props: true,
    meta: { title: 'Bot Version History' },
  },
  // Bot Dry Run
  {
    path: '/bots/dry-run',
    name: 'bot-dry-run',
    component: () => import('../../views/BotDryRun.vue'),
    meta: { title: 'Bot Dry Run' },
  },
  // Integration Ticketing
  {
    path: '/integrations/ticketing',
    name: 'integration-ticketing',
    component: () => import('../../views/IntegrationTicketing.vue'),
    meta: { title: 'Ticketing Integrations' },
  },
  // Webhook Recorder
  {
    path: '/webhooks/recorder',
    name: 'webhook-recorder',
    component: () => import('../../views/WebhookRecorder.vue'),
    meta: { title: 'Webhook Recorder' },
  },
  // Human Approval Gates
  {
    path: '/workflows/approval-gates',
    name: 'human-approval-gates',
    component: () => import('../../views/HumanApprovalGates.vue'),
    meta: { title: 'Human Approval Gates' },
  },
  // Secrets Vault
  {
    path: '/settings/secrets',
    name: 'secrets-vault',
    component: () => import('../../views/SecretsVault.vue'),
    meta: { title: 'Secrets Vault' },
  },
  // Alert Grouping
  {
    path: '/monitoring/alerts',
    name: 'alert-grouping',
    component: () => import('../../views/AlertGrouping.vue'),
    meta: { title: 'Alert Grouping' },
  },
  // Cross-Team Bot Sharing
  {
    path: '/bots/sharing',
    name: 'cross-team-bot-sharing',
    component: () => import('../../views/CrossTeamBotSharing.vue'),
    meta: { title: 'Cross-Team Bot Sharing' },
  },
  // Changelog Generator
  {
    path: '/tools/changelog',
    name: 'changelog-generator',
    component: () => import('../../views/ChangelogGenerator.vue'),
    meta: { title: 'Changelog Generator' },
  },
  // Dependency Impact Bot
  {
    path: '/tools/dependency-impact',
    name: 'dependency-impact-bot',
    component: () => import('../../views/DependencyImpactBot.vue'),
    meta: { title: 'Dependency Impact Bot' },
  },
  // Execution Queue Dashboard
  {
    path: '/executions/queue',
    name: 'execution-queue-dashboard',
    component: () => import('../../views/ExecutionQueueDashboard.vue'),
    meta: { title: 'Execution Queue Dashboard' },
  },
  // Bot Dependency Graph
  {
    path: '/bots/dependency-graph',
    name: 'bot-dependency-graph',
    component: () => import('../../views/BotDependencyGraph.vue'),
    meta: { title: 'Bot Dependency Graph' },
  },
  // On-Call Escalation
  {
    path: '/integrations/on-call',
    name: 'on-call-escalation',
    component: () => import('../../views/OnCallEscalation.vue'),
    meta: { title: 'On-Call Escalation' },
  },
  // Context Window Visualizer
  {
    path: '/bots/context-window',
    name: 'context-window-visualizer',
    component: () => import('../../views/ContextWindowVisualizer.vue'),
    meta: { title: 'Context Window Visualizer' },
  },
  // Multi-Repo Fan-Out
  {
    path: '/triggers/multi-repo',
    name: 'multi-repo-fan-out',
    component: () => import('../../views/MultiRepoFanOut.vue'),
    meta: { title: 'Multi-Repo Fan-Out' },
  },
  // Execution File Diff Viewer
  {
    path: '/executions/diff-viewer',
    name: 'execution-file-diff-viewer',
    component: () => import('../../views/ExecutionFileDiffViewer.vue'),
    meta: { title: 'Execution File Diff Viewer' },
  },
  // Multi-Provider Fallback Chains
  {
    path: '/settings/provider-fallback',
    name: 'multi-provider-fallback',
    component: () => import('../../views/MultiProviderFallback.vue'),
    meta: { title: 'Multi-Provider Fallback' },
  },
  // GitHub PR Annotation Integration
  {
    path: '/integrations/github-pr-annotations',
    name: 'github-pr-annotation',
    component: () => import('../../views/GitHubPRAnnotation.vue'),
    meta: { title: 'GitHub PR Annotations' },
  },
  // Prompt A/B Testing
  {
    path: '/bots/ab-testing',
    name: 'prompt-ab-testing',
    component: () => import('../../views/PromptABTesting.vue'),
    meta: { title: 'Prompt A/B Testing' },
  },
  // Automatic Codebase Context Injection
  {
    path: '/bots/context-injection',
    name: 'auto-context-injection',
    component: () => import('../../views/AutoContextInjection.vue'),
    meta: { title: 'Auto Context Injection' },
  },
  // Natural Language Trigger Rule Editor
  {
    path: '/triggers/nl-rule-editor',
    name: 'nl-trigger-rule-editor',
    component: () => import('../../views/NLTriggerRuleEditor.vue'),
    meta: { title: 'Natural Language Trigger Rules' },
  },
  // Provider Benchmarking Dashboard
  {
    path: '/backends/benchmark',
    name: 'provider-benchmark-dashboard',
    component: () => import('../../views/ProviderBenchmarkDashboard.vue'),
    meta: { title: 'Provider Benchmarks' },
  },
  // Bot Output Webhook Forwarding
  {
    path: '/integrations/webhook-forwarding',
    name: 'bot-output-webhook-forwarding',
    component: () => import('../../views/BotOutputWebhookForwarding.vue'),
    meta: { title: 'Webhook Output Forwarding' },
  },
  // Multi-Agent Collaboration Mode
  {
    path: '/bots/multi-agent',
    name: 'multi-agent-collaboration',
    component: () => import('../../views/MultiAgentCollaboration.vue'),
    meta: { title: 'Multi-Agent Collaboration' },
  },
  // Visual Schedule / Cron Wizard
  {
    path: '/scheduling/wizard',
    name: 'visual-cron-wizard',
    component: () => import('../../views/VisualCronWizard.vue'),
    meta: { title: 'Schedule Wizard' },
  },
  // Bot Recommendation Engine
  {
    path: '/bots/recommendations',
    name: 'bot-recommendation-engine',
    component: () => import('../../views/BotRecommendationEngine.vue'),
    meta: { title: 'Bot Recommendations' },
  },
  // Inline Prompt Editor with Live Preview
  {
    path: '/bots/prompt-editor',
    name: 'inline-prompt-editor',
    component: () => import('../../views/InlinePromptEditor.vue'),
    meta: { title: 'Inline Prompt Editor' },
  },
  // Execution Annotation & Quality Feedback
  {
    path: '/executions/annotations',
    name: 'execution-annotation',
    component: () => import('../../views/ExecutionAnnotation.vue'),
    meta: { title: 'Execution Annotations' },
  },
  // Trigger Simulation & Test Harness
  {
    path: '/triggers/simulation',
    name: 'trigger-simulation',
    component: () => import('../../views/TriggerSimulation.vue'),
    meta: { title: 'Trigger Simulation' },
  },
  // Execution Time-Travel Debugger
  {
    path: '/executions/time-travel',
    name: 'execution-time-travel-debugger',
    component: () => import('../../views/ExecutionTimeTravelDebugger.vue'),
    meta: { title: 'Time-Travel Debugger' },
  },
  // Project Activity Timeline
  {
    path: '/projects/activity',
    name: 'project-activity-timeline',
    component: () => import('../../views/ProjectActivityTimeline.vue'),
    meta: { title: 'Project Activity Timeline' },
  },
  // Configurable Smart Retry Policies
  {
    path: '/bots/retry-policies',
    name: 'bot-retry-policies',
    component: () => import('../../views/BotRetryPoliciesPage.vue'),
    meta: { title: 'Retry Policies' },
  },
  // Repository Context Indexing
  {
    path: '/bots/repo-context',
    name: 'repo-context-indexing',
    component: () => import('../../views/RepoContextIndexingPage.vue'),
    meta: { title: 'Repository Context Indexing' },
  },
  // Auto-Generated Bot Documentation
  {
    path: '/bots/doc-generator',
    name: 'bot-doc-generator',
    component: () => import('../../views/BotDocGeneratorPage.vue'),
    meta: { title: 'Bot Doc Generator' },
  },
  // Bot Clone & Fork
  {
    path: '/bots/clone',
    name: 'bot-clone-fork',
    component: () => import('../../views/BotCloneForkPage.vue'),
    meta: { title: 'Clone & Fork Bot' },
  },
  // AI-Powered PR Auto-Assignment
  {
    path: '/integrations/pr-auto-assign',
    name: 'pr-auto-assignment',
    component: () => import('../../views/PrAutoAssignmentPage.vue'),
    meta: { title: 'PR Auto-Assignment' },
  },
  // Slack Command Gateway
  {
    path: '/integrations/slack-gateway',
    name: 'slack-command-gateway',
    component: () => import('../../views/SlackCommandGatewayPage.vue'),
    meta: { title: 'Slack Command Gateway' },
  },
  // Live Execution Terminal
  {
    path: '/executions/:executionId/terminal',
    name: 'live-execution-terminal',
    component: () => import('../../views/LiveExecutionTerminal.vue'),
    props: true,
    meta: { title: 'Live Execution Terminal' },
  },
  // New Engineer Onboarding Automation
  {
    path: '/bots/onboarding',
    name: 'onboarding-automation',
    component: () => import('../../views/OnboardingAutomationPage.vue'),
    meta: { title: 'Onboarding Automation' },
  },
  // Plugin SDK & CLI (Feature 18)
  {
    path: '/plugins/sdk',
    name: 'plugin-sdk',
    component: () => import('../../views/PluginSdkPage.vue'),
    meta: { title: 'Plugin SDK & CLI' },
  },
  // Bot Output Piping (Feature 20)
  {
    path: '/bots/piping',
    name: 'bot-output-piping',
    component: () => import('../../views/BotOutputPipingPage.vue'),
    meta: { title: 'Bot Output Piping' },
  },
  // Agent Skill Auto-Discovery (Feature 28)
  {
    path: '/agents/skill-discovery',
    name: 'agent-skill-discovery',
    component: () => import('../../views/AgentSkillDiscoveryPage.vue'),
    meta: { title: 'Skill Auto-Discovery' },
  },
  // Infrastructure-as-Code Export (Feature 30)
  {
    path: '/settings/iac-export',
    name: 'iac-export',
    component: () => import('../../views/IaCExportPage.vue'),
    meta: { title: 'IaC Export' },
  },
  // Project Health Scorecard (Feature 36)
  {
    path: '/projects/health-scorecard',
    name: 'project-health-scorecard',
    component: () => import('../../views/ProjectHealthScorecardPage.vue'),
    meta: { title: 'Project Health Scorecard' },
  },
  // API Key-Based Programmatic Access (Feature 38)
  {
    path: '/settings/api-keys',
    name: 'api-keys',
    component: () => import('../../views/ApiKeysPage.vue'),
    meta: { title: 'API Keys' },
  },
  // Agent Capability Matrix (Feature 17)
  {
    path: '/agents/capability-matrix',
    name: 'agent-capability-matrix',
    component: () => import('../../views/AgentCapabilityMatrix.vue'),
    meta: { title: 'Agent Capability Matrix' },
  },
  // Execution Quota & Rate Controls (Feature 19)
  {
    path: '/settings/execution-quotas',
    name: 'execution-quota-controls',
    component: () => import('../../views/ExecutionQuotaControls.vue'),
    meta: { title: 'Execution Quotas & Rate Controls' },
  },
  // Findings Trend Analysis (Feature 24)
  {
    path: '/dashboards/findings-trend',
    name: 'findings-trend-analysis',
    component: () => import('../../views/FindingsTrendAnalysis.vue'),
    meta: { title: 'Findings Trend Analysis' },
  },
  // Bot Test Sandbox Environments (Feature 29)
  {
    path: '/bots/sandbox',
    name: 'bot-sandbox',
    component: () => import('../../views/BotSandboxPage.vue'),
    meta: { title: 'Bot Test Sandboxes' },
  },
  // Mobile Execution Monitor (Feature 30)
  {
    path: '/executions/monitor',
    name: 'mobile-execution-monitor',
    component: () => import('../../views/MobileExecutionMonitor.vue'),
    meta: { title: 'Execution Monitor' },
  },
  // Team Automation Leaderboard (Feature 32)
  {
    path: '/dashboards/leaderboard',
    name: 'team-leaderboard',
    component: () => import('../../views/TeamLeaderboard.vue'),
    meta: { title: 'Team Automation Leaderboard' },
  },
  // Bot-Linked Runbooks (Feature 33)
  {
    path: '/bots/runbooks',
    name: 'bot-runbooks',
    component: () => import('../../views/BotRunbooksPage.vue'),
    meta: { title: 'Bot Runbooks' },
  },
  // Execution Anomaly Detection (Feature 34)
  {
    path: '/executions/anomalies',
    name: 'execution-anomaly-detection',
    component: () => import('../../views/ExecutionAnomalyDetection.vue'),
    meta: { title: 'Execution Anomaly Detection' },
  },
  // On-Demand Code Explanation Bot (Feature 10)
  {
    path: '/tools/code-explanation',
    name: 'code-explanation-bot',
    component: () => import('../../views/CodeExplanationBotPage.vue'),
    meta: { title: 'Code Explanation Bot' },
  },
  // One-Click GitHub App Install (Feature 14)
  {
    path: '/integrations/github-app-install',
    name: 'github-app-install',
    component: () => import('../../views/GitHubAppInstallPage.vue'),
    meta: { title: 'GitHub App Install' },
  },
  // Execution Output Artifacts (Feature 34)
  {
    path: '/executions/artifacts',
    name: 'execution-artifacts',
    component: () => import('../../views/ExecutionArtifactsPage.vue'),
    meta: { title: 'Execution Artifacts' },
  },
  // Cross-Repo Impact Analysis Bot (Feature 35)
  {
    path: '/tools/cross-repo-impact',
    name: 'cross-repo-impact-bot',
    component: () => import('../../views/CrossRepoImpactBotPage.vue'),
    meta: { title: 'Cross-Repo Impact Analysis' },
  },
  // Plugin Execution Sandboxing (Feature 37)
  {
    path: '/plugins/sandbox',
    name: 'plugin-sandbox',
    component: () => import('../../views/PluginSandboxPage.vue'),
    meta: { title: 'Plugin Sandbox' },
  },
  // Bot SLA & Uptime Tracking (Feature 39)
  {
    path: '/dashboards/bot-sla',
    name: 'bot-sla-uptime',
    component: () => import('../../views/BotSlaUptimePage.vue'),
    meta: { title: 'Bot SLA & Uptime' },
  },
  // Slack Execution Notifications (Feature 7)
  {
    path: '/integrations/slack-notifications',
    name: 'slack-notifications',
    component: () => import('../../views/SlackNotificationsPage.vue'),
    meta: { title: 'Slack Notifications' },
  },
  // Conditional Trigger Rules Engine (Feature 12)
  {
    path: '/triggers/conditional-rules',
    name: 'conditional-trigger-rules',
    component: () => import('../../views/ConditionalTriggerRulesPage.vue'),
    meta: { title: 'Conditional Trigger Rules' },
  },
  // Agent Quality Scoring (Feature 14)
  {
    path: '/agents/quality-scoring',
    name: 'agent-quality-scoring',
    component: () => import('../../views/AgentQualityScoringPage.vue'),
    meta: { title: 'Agent Quality Scoring' },
  },
  // Team Activity Feed (Feature 17)
  {
    path: '/teams/activity-feed',
    name: 'team-activity-feed',
    component: () => import('../../views/TeamActivityFeedPage.vue'),
    meta: { title: 'Team Activity Feed' },
  },
  // Guided Onboarding Wizard (Feature 30)
  {
    path: '/onboarding',
    name: 'guided-onboarding-wizard',
    component: () => import('../../views/GuidedOnboardingWizardPage.vue'),
    meta: { title: 'Get Started' },
  },
  // Execution Timeline — Gantt-style view (item 22)
  {
    path: '/executions/timeline',
    name: 'execution-timeline',
    component: () => import('../../views/ExecutionTimelinePage.vue'),
    meta: { title: 'Execution Timeline' },
  },
  // Incident Response Playbook Bots (item 34)
  {
    path: '/bots/incident-playbooks',
    name: 'incident-response-playbooks',
    component: () => import('../../views/IncidentResponsePlaybooksPage.vue'),
    meta: { title: 'Incident Response Playbooks' },
  },
  // Repository-Level Default Bots (feature 21)
  {
    path: '/repos/default-bots',
    name: 'repo-bot-defaults',
    component: () => import('../../views/RepoBotDefaultsPage.vue'),
    meta: { title: 'Repository Default Bots' },
  },
  // Metrics Export to Grafana/Datadog (feature 25)
  {
    path: '/settings/metrics-export',
    name: 'metrics-export',
    component: () => import('../../views/MetricsExportPage.vue'),
    meta: { title: 'Metrics Export' },
  },
  // Dependency-Aware Scheduling (feature 30)
  {
    path: '/scheduling/dependency',
    name: 'dependency-aware-scheduling',
    component: () => import('../../views/DependencyAwareSchedulingPage.vue'),
    meta: { title: 'Dependency-Aware Scheduling' },
  },
  // Visual Skill Composer (feature 31)
  {
    path: '/skills/composer',
    name: 'visual-skill-composer',
    component: () => import('../../views/VisualSkillComposerPage.vue'),
    meta: { title: 'Visual Skill Composer' },
  },
  // Per-Bot Persistent Memory (feature 35)
  {
    path: '/bots/memory',
    name: 'bot-memory-store',
    component: () => import('../../views/BotMemoryStorePage.vue'),
    meta: { title: 'Bot Memory Store' },
  },
  // Configurable Data Retention Policies (feature 39)
  {
    path: '/settings/retention',
    name: 'data-retention-policies',
    component: () => import('../../views/DataRetentionPoliciesPage.vue'),
    meta: { title: 'Data Retention Policies' },
  },
  // Findings Triage Board (feature 13)
  {
    path: '/dashboards/findings-triage',
    name: 'findings-triage-board',
    component: () => import('../../views/FindingsTriageBoardPage.vue'),
    meta: { title: 'Findings Triage Board' },
  },
  // PR Review Learning Loop (feature 7)
  {
    path: '/integrations/pr-review-learning',
    name: 'pr-review-learning-loop',
    component: () => import('../../views/PrReviewLearningLoopPage.vue'),
    meta: { title: 'PR Review Learning Loop' },
  },
  // Full Conversation History Viewer (feature 33)
  {
    path: '/executions/conversation-history',
    name: 'conversation-history-viewer',
    component: () => import('../../views/ConversationHistoryViewer.vue'),
    meta: { title: 'Conversation History' },
  },
  // Skill & Plugin Version Pinning (feature 34)
  {
    path: '/settings/version-pinning',
    name: 'skill-version-pinning',
    component: () => import('../../views/SkillVersionPinningPage.vue'),
    meta: { title: 'Skill & Plugin Version Pinning' },
  },
  // Repository Scope Filters for Bots (feature 15)
  {
    path: '/bots/repo-scope-filters',
    name: 'repo-scope-filters',
    component: () => import('../../views/RepoScopeFiltersPage.vue'),
    meta: { title: 'Repository Scope Filters' },
  },
  // Bot Performance Benchmarks (feature 7)
  {
    path: '/bots/benchmarks',
    name: 'bot-performance-benchmarks',
    component: () => import('../../views/BotPerformanceBenchmarksPage.vue'),
    meta: { title: 'Bot Performance Benchmarks' },
  },
  // Smart Schedule Optimizer (feature 37)
  {
    path: '/scheduling/optimizer',
    name: 'smart-schedule-optimizer',
    component: () => import('../../views/SmartScheduleOptimizerPage.vue'),
    meta: { title: 'Smart Schedule Optimizer' },
  },
  // Cross-Team Insights Dashboard (feature 33)
  {
    path: '/dashboards/cross-team-insights',
    name: 'cross-team-insights',
    component: () => import('../../views/CrossTeamInsightsDashboard.vue'),
    meta: { title: 'Cross-Team Insights' },
  },
  // Slack & Teams Notification Channels (feature 9)
  {
    path: '/integrations/notification-channels',
    name: 'notification-channels',
    component: () => import('../../views/TeamsNotificationChannelsPage.vue'),
    meta: { title: 'Notification Channels' },
  },
  // Execution Tagging & Full-Text Search (feature 23)
  {
    path: '/executions/tagging',
    name: 'execution-tagging',
    component: () => import('../../views/ExecutionTaggingPage.vue'),
    meta: { title: 'Execution Tagging & Search' },
  },
  // Prompt Template Playground (Feature 2)
  {
    path: '/bots/prompt-playground',
    name: 'prompt-template-playground',
    component: () => import('../../views/PromptTemplatePlayground.vue'),
    meta: { title: 'Prompt Template Playground' },
  },
  // AI Cost Dashboard (Feature 4)
  {
    path: '/dashboards/ai-cost',
    name: 'ai-cost-dashboard',
    component: () => import('../../views/AiCostDashboard.vue'),
    meta: { title: 'AI Cost Dashboard' },
  },
  // GitOps Bot Configuration Sync (Feature 28)
  {
    path: '/settings/gitops-sync',
    name: 'gitops-sync',
    component: () => import('../../views/GitOpsSyncPage.vue'),
    meta: { title: 'GitOps Sync' },
  },
  // Shareable Execution Live Links (Feature 34)
  {
    path: '/executions/share',
    name: 'shareable-execution-links',
    component: () => import('../../views/ShareableExecutionLinksPage.vue'),
    meta: { title: 'Shareable Execution Links' },
  },
  // Webhook Payload Transformer (Feature 37)
  {
    path: '/webhooks/transformer',
    name: 'webhook-payload-transformer',
    component: () => import('../../views/WebhookPayloadTransformerPage.vue'),
    meta: { title: 'Webhook Payload Transformer' },
  },
  // Non-English Prompt Localization (Feature 38)
  {
    path: '/bots/prompt-localization',
    name: 'prompt-localization',
    component: () => import('../../views/PromptLocalizationPage.vue'),
    meta: { title: 'Prompt Localization' },
  },
  // Prompt Template Version History (item 3)
  {
    path: '/bots/prompt-versions',
    name: 'prompt-version-history',
    component: () => import('../../views/PromptVersionHistoryPage.vue'),
    meta: { title: 'Prompt Version History' },
  },
  // Smart Alert Rules on Findings (item 8)
  {
    path: '/monitoring/alert-rules',
    name: 'smart-alert-rules',
    component: () => import('../../views/SmartAlertRulesPage.vue'),
    meta: { title: 'Smart Alert Rules' },
  },
  // Skill Marketplace & Sharing (item 10)
  {
    path: '/skills/marketplace',
    name: 'skill-marketplace',
    component: () => import('../../views/SkillMarketplacePage.vue'),
    meta: { title: 'Skill Marketplace' },
  },
  // System Error Dashboard
  {
    path: '/settings/system-errors',
    name: 'system-errors',
    component: () => import('../../views/SystemErrorsPage.vue'),
    meta: { title: 'System Errors' },
  },
];
