import type { RouteRecordRaw } from 'vue-router';

// PR-D — Dashboards lanes.
//
// 14 dashboards collapse into 4 lane pages (Quality / Cost / Health /
// Activity) + the repurposed 4-tile landing at `/`. Old route names
// remain wired as function-form redirects so any `router.push({ name:
// '...' })` call site continues to work and bookmarks land on the
// matching card via the URL hash.
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

  // New lane pages
  {
    path: '/dashboards/quality',
    name: 'dashboards-quality',
    component: () => import('../../views/dashboards/QualityPage.vue'),
    meta: { title: 'Quality Dashboards' },
  },
  {
    path: '/dashboards/cost',
    name: 'dashboards-cost',
    component: () => import('../../views/dashboards/CostPage.vue'),
    meta: { title: 'Cost Dashboards' },
  },
  {
    path: '/dashboards/health',
    name: 'dashboards-health',
    component: () => import('../../views/dashboards/HealthPage.vue'),
    meta: { title: 'Health Dashboards' },
  },
  {
    path: '/dashboards/activity',
    name: 'dashboards-activity',
    component: () => import('../../views/dashboards/ActivityPage.vue'),
    meta: { title: 'Activity Dashboards' },
  },

  // Org-overview tiles still in the launcher — keep the routes that
  // existed pre-PR-D and weren't part of the lane consolidation.
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

  // Function-form redirects for the 8 dashboard routes that lived here
  // pre-PR-D. PRESERVE the old `name`s so `router.push({ name: ... })`
  // call sites continue to resolve.
  {
    path: '/dashboards/security',
    name: 'security-dashboard',
    redirect: () => ({ name: 'dashboards-quality', hash: '#security' }),
  },
  {
    path: '/dashboards/pr-review',
    name: 'pr-review-dashboard',
    redirect: () => ({ name: 'dashboards-quality', hash: '#pr-review' }),
  },
  {
    path: '/dashboards/scheduling',
    name: 'rotation-dashboard',
    redirect: () => ({ name: 'dashboards-activity', hash: '#scheduling' }),
  },
  {
    path: '/dashboards/tokens',
    name: 'token-usage',
    redirect: () => ({ name: 'dashboards-cost', hash: '#token-usage' }),
  },
  {
    path: '/dashboards/analytics',
    name: 'analytics-dashboard',
    redirect: () => ({ name: 'dashboards-cost', hash: '#token-usage' }),
  },
  {
    path: '/dashboards/bot-health-monitor',
    name: 'health-dashboard',
    redirect: () => ({ name: 'dashboards-health', hash: '#health-monitor' }),
  },
  {
    path: '/dashboards/team-report',
    name: 'team-impact-report',
    redirect: () => ({ name: 'dashboards-activity', hash: '#impact-report' }),
  },
];
