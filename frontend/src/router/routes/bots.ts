import type { RouteRecordRaw } from 'vue-router';

export const botRoutes: RouteRecordRaw[] = [
  // Test Coverage Bot
  {
    path: '/bots/test-coverage',
    name: 'test-coverage-bot',
    component: () => import('../../views/TestCoverageBot.vue'),
    meta: { title: 'Test Coverage Bot' },
  },
  // Bot Dry Run
  {
    path: '/bots/dry-run',
    name: 'bot-dry-run',
    component: () => import('../../views/BotDryRun.vue'),
    meta: { title: 'Bot Dry Run' },
  },
  // Cross-Team Bot Sharing
  {
    path: '/bots/sharing',
    name: 'cross-team-bot-sharing',
    component: () => import('../../views/CrossTeamBotSharing.vue'),
    meta: { title: 'Cross-Team Bot Sharing' },
  },
  // Dependency Impact Bot
  {
    path: '/tools/dependency-impact',
    name: 'dependency-impact-bot',
    component: () => import('../../views/DependencyImpactBot.vue'),
    meta: { title: 'Dependency Impact Bot' },
  },
  // Bot Dependency Graph
  {
    path: '/bots/dependency-graph',
    name: 'bot-dependency-graph',
    component: () => import('../../views/BotDependencyGraph.vue'),
    meta: { title: 'Bot Dependency Graph' },
  },
  // Multi-Repo Fan-Out
  {
    path: '/triggers/multi-repo',
    name: 'multi-repo-fan-out',
    component: () => import('../../views/MultiRepoFanOut.vue'),
    meta: { title: 'Multi-Repo Fan-Out' },
  },
  // Bot Recommendation Engine
  {
    path: '/bots/recommendations',
    name: 'bot-recommendation-engine',
    component: () => import('../../views/BotRecommendationEngine.vue'),
    meta: { title: 'Bot Recommendations' },
  },
  // Bot Clone & Fork
  {
    path: '/bots/clone',
    name: 'bot-clone-fork',
    component: () => import('../../views/BotCloneForkPage.vue'),
    meta: { title: 'Clone & Fork Bot' },
  },
  // Bot Output Piping (Feature 20)
  {
    path: '/bots/piping',
    name: 'bot-output-piping',
    component: () => import('../../views/BotOutputPipingPage.vue'),
    meta: { title: 'Bot Output Piping' },
  },
  // Bot Test Sandbox Environments (Feature 29)
  {
    path: '/bots/sandbox',
    name: 'bot-sandbox',
    component: () => import('../../views/BotSandboxPage.vue'),
    meta: { title: 'Bot Test Sandboxes' },
  },
  // Bot-Linked Runbooks (Feature 33)
  {
    path: '/bots/runbooks',
    name: 'bot-runbooks',
    component: () => import('../../views/BotRunbooksPage.vue'),
    meta: { title: 'Bot Runbooks' },
  },
  // On-Demand Code Explanation Bot (Feature 10)
  {
    path: '/tools/code-explanation',
    name: 'code-explanation-bot',
    component: () => import('../../views/CodeExplanationBotPage.vue'),
    meta: { title: 'Code Explanation Bot' },
  },
  // Cross-Repo Impact Analysis Bot (Feature 35)
  {
    path: '/tools/cross-repo-impact',
    name: 'cross-repo-impact-bot',
    component: () => import('../../views/CrossRepoImpactBotPage.vue'),
    meta: { title: 'Cross-Repo Impact Analysis' },
  },
  // Bot SLA & Uptime Tracking (Feature 39)
  {
    path: '/dashboards/bot-sla',
    name: 'bot-sla-uptime',
    component: () => import('../../views/BotSlaUptimePage.vue'),
    meta: { title: 'Bot SLA & Uptime' },
  },
  // Repository-Level Default Bots (feature 21)
  {
    path: '/repos/default-bots',
    name: 'repo-bot-defaults',
    component: () => import('../../views/RepoBotDefaultsPage.vue'),
    meta: { title: 'Repository Default Bots' },
  },
  // Per-Bot Persistent Memory (feature 35)
  {
    path: '/bots/memory',
    name: 'bot-memory-store',
    component: () => import('../../views/BotMemoryStorePage.vue'),
    meta: { title: 'Bot Memory Store' },
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
];
