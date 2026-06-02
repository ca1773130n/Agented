import type { RouteRecordRaw } from 'vue-router';

export const observabilityExtRoutes: RouteRecordRaw[] = [
  // System Error Dashboard
  {
    path: '/settings/system-errors',
    name: 'system-errors',
    component: () => import('../../views/SystemErrorsPage.vue'),
    meta: { title: 'System Errors' },
  },
  // PR-D — Service Health folded into the Health lane.
  {
    path: '/backends/health',
    name: 'service-health',
    redirect: () => ({ name: 'dashboards-health', hash: '#service-health' }),
  },
  // PR-D — Bot Health folded into the Health lane.
  {
    path: '/bots/health',
    name: 'bot-health',
    redirect: () => ({ name: 'dashboards-health', hash: '#bot-health' }),
  },
  // AI Cost Dashboard (Feature 4)
  {
    path: '/dashboards/ai-cost',
    name: 'ai-cost-dashboard',
    component: () => import('../../views/AiCostDashboard.vue'),
    meta: { title: 'AI Cost Dashboard' },
  },
  // PR-D — Execution Anomaly Detection folded into the Quality lane.
  {
    path: '/executions/anomalies',
    name: 'execution-anomaly-detection',
    redirect: () => ({ name: 'dashboards-quality', hash: '#anomaly-detection' }),
  },
];
