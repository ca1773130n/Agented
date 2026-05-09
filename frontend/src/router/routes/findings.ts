import type { RouteRecordRaw } from 'vue-router';

export const findingsRoutes: RouteRecordRaw[] = [
  // Findings Trend Analysis (Feature 24)
  {
    path: '/dashboards/findings-trend',
    name: 'findings-trend-analysis',
    component: () => import('../../views/FindingsTrendAnalysis.vue'),
    meta: { title: 'Findings Trend Analysis' },
  },
  // Findings Triage Board (feature 13)
  {
    path: '/dashboards/findings-triage',
    name: 'findings-triage-board',
    component: () => import('../../views/FindingsTriageBoardPage.vue'),
    meta: { title: 'Findings Triage Board' },
  },
];
