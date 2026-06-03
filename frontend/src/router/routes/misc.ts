import type { RouteRecordRaw } from 'vue-router';

// Residual catch-all for routes that don't fit cleanly in domain modules.
// New routes should be added to a domain-specific file (auth, bots, executions,
// prompts, github, etc.) — this file should stay small.
export const miscRoutes: RouteRecordRaw[] = [
  // Help — developer docs / setup surfaces (Plugin SDK, GitHub Actions) (P2).
  {
    path: '/help',
    name: 'help',
    component: () => import('../../views/HelpPage.vue'),
    meta: { title: 'Help' },
  },
  // Base redirect for the Platform expandable sidebar section.
  // (`/integrations` is now a real route — the unified Integrations page.)
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
