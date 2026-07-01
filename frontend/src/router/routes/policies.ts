import type { RouteRecordRaw } from 'vue-router';

// Phase 23 — stackable policy / governance engine authoring surface.
// Reachable at /policies (no sidebar slot — a working backend does not earn one
// per the sidebar-IA convention).
export const policyRoutes: RouteRecordRaw[] = [
  {
    path: '/policies',
    name: 'policy-management',
    component: () => import('../../views/PolicyManagement.vue'),
    meta: { title: 'Policies' },
  },
];
