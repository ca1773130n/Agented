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
    path: '/admin/rbac',
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
    path: '/admin/secrets',
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
    path: '/executions/terminal',
    name: 'live-execution-terminal',
    component: () => import('../../views/LiveExecutionTerminal.vue'),
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
];
