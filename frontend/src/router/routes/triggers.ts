import type { RouteRecordRaw } from 'vue-router';

export const triggerRoutes: RouteRecordRaw[] = [
  {
    path: '/triggers',
    name: 'triggers',
    component: () => import('../../views/TriggerManagement.vue'),
    meta: { title: 'Triggers' },
  },
  {
    path: '/triggers/:triggerId',
    name: 'trigger-dashboard',
    component: () => import('../../views/GenericTriggerDashboard.vue'),
    props: true,
    meta: { title: 'Trigger Dashboard', requiresEntity: 'triggerId' },
  },
  {
    path: '/triggers/:triggerId/history',
    name: 'trigger-history',
    component: () => import('../../views/GenericTriggerHistory.vue'),
    props: true,
    meta: { title: 'Trigger History', requiresEntity: 'triggerId' },
  },
  {
    path: '/history/security',
    name: 'security-history',
    component: () => import('../../views/AuditHistory.vue'),
    meta: { title: 'Security History' },
  },
  {
    path: '/audits/:auditId',
    name: 'audit-detail',
    component: () => import('../../views/AuditDetail.vue'),
    props: true,
    meta: { title: 'Audit Detail', requiresEntity: 'auditId' },
  },
  {
    path: '/executions',
    name: 'execution-history',
    component: () => import('../../views/ExecutionHistory.vue'),
    meta: { title: 'Execution History' },
  },
];
