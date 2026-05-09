import type { RouteRecordRaw } from 'vue-router';

// Residual catch-all for routes that don't fit cleanly in domain modules.
// New routes should be added to a domain-specific file (auth, bots, executions,
// prompts, github, etc.) — this file should stay small.
export const miscRoutes: RouteRecordRaw[] = [
  // Base redirects for expandable sidebar sections
  {
    path: '/integrations',
    redirect: '/integrations/slack-notifications',
  },
  {
    path: '/platform',
    redirect: '/settings',
  },
  // Team Budgets
  {
    path: '/teams/budgets',
    name: 'team-budgets',
    component: () => import('../../views/TeamBudgetsPage.vue'),
    meta: { title: 'Team Budgets' },
  },
  // Human Approval Gates
  {
    path: '/workflows/approval-gates',
    name: 'human-approval-gates',
    component: () => import('../../views/HumanApprovalGates.vue'),
    meta: { title: 'Human Approval Gates' },
  },
];
