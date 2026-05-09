import type { RouteRecordRaw } from 'vue-router';

export const observabilityExtRoutes: RouteRecordRaw[] = [
  // System Error Dashboard
  {
    path: '/settings/system-errors',
    name: 'system-errors',
    component: () => import('../../views/SystemErrorsPage.vue'),
    meta: { title: 'System Errors' },
  },
  // Service Health
  {
    path: '/backends/health',
    name: 'service-health',
    component: () => import('../../views/ServiceHealthDashboard.vue'),
    meta: { title: 'Service Health' },
  },
  // v0.7.0: per-bot success-rate / p95 / status rollups
  {
    path: '/bots/health',
    name: 'bot-health',
    component: () => import('../../views/BotHealthPage.vue'),
    meta: { title: 'Bot Health' },
  },
  // AI Cost Dashboard (Feature 4)
  {
    path: '/dashboards/ai-cost',
    name: 'ai-cost-dashboard',
    component: () => import('../../views/AiCostDashboard.vue'),
    meta: { title: 'AI Cost Dashboard' },
  },
  // Provider Benchmarking Dashboard
  {
    path: '/backends/benchmark',
    name: 'provider-benchmark-dashboard',
    component: () => import('../../views/ProviderBenchmarkDashboard.vue'),
    meta: { title: 'Provider Benchmarks' },
  },
  // Execution Anomaly Detection (Feature 34)
  {
    path: '/executions/anomalies',
    name: 'execution-anomaly-detection',
    component: () => import('../../views/ExecutionAnomalyDetection.vue'),
    meta: { title: 'Execution Anomaly Detection' },
  },
];
