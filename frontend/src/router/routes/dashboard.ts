import type { RouteRecordRaw } from 'vue-router';

export const dashboardRoutes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'dashboards',
    component: () => import('../../views/DashboardsPage.vue'),
    meta: { title: 'Dashboards' },
  },
  {
    path: '/dashboards',
    redirect: { name: 'dashboards' },
  },
  {
    path: '/dashboards/security',
    name: 'security-dashboard',
    component: () => import('../../views/SecurityDashboard.vue'),
    meta: { title: 'Security Dashboard' },
  },
  {
    path: '/dashboards/pr-review',
    name: 'pr-review-dashboard',
    component: () => import('../../views/PrReviewDashboard.vue'),
    meta: { title: 'PR Review Dashboard' },
  },
  {
    path: '/dashboards/products',
    name: 'products-summary',
    component: () => import('../../views/ProductsSummaryDashboard.vue'),
    meta: { title: 'Products Summary' },
  },
  {
    path: '/dashboards/projects',
    name: 'projects-summary',
    component: () => import('../../views/ProjectsSummaryDashboard.vue'),
    meta: { title: 'Projects Summary' },
  },
  {
    path: '/dashboards/teams',
    name: 'teams-summary',
    component: () => import('../../views/TeamsSummaryDashboard.vue'),
    meta: { title: 'Teams Summary' },
  },
  {
    path: '/dashboards/agents',
    name: 'agents-summary',
    component: () => import('../../views/AgentsSummaryDashboard.vue'),
    meta: { title: 'Agents Summary' },
  },
  {
    path: '/dashboards/scheduling',
    name: 'rotation-dashboard',
    component: () => import('../../views/SchedulingDashboard.vue'),
    meta: { title: 'Scheduling Dashboard' },
  },
  {
    path: '/dashboards/tokens',
    name: 'token-usage',
    component: () => import('../../views/TokenUsageDashboard.vue'),
    meta: { title: 'Token Usage' },
  },
];
