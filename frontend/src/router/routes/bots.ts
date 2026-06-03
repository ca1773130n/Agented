import type { RouteRecordRaw } from 'vue-router';

export const botRoutes: RouteRecordRaw[] = [
  // Test Coverage Bot
  {
    path: '/bots/test-coverage',
    name: 'test-coverage-bot',
    component: () => import('../../views/TestCoverageBot.vue'),
    meta: { title: 'Test Coverage Bot' },
  },
  // Bot Dry Run — folded into the Trigger Tools page (P2).
  {
    path: '/bots/dry-run',
    name: 'bot-dry-run',
    redirect: (to) => ({ name: 'trigger-tools', query: { ...to.query, tab: 'dry-run' } }),
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
  // Bot Test Sandbox Environments (Feature 29)
  {
    path: '/bots/sandbox',
    name: 'bot-sandbox',
    component: () => import('../../views/BotSandboxPage.vue'),
    meta: { title: 'Bot Test Sandboxes' },
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
