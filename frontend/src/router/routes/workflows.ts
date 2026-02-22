import type { RouteRecordRaw } from 'vue-router';

export const workflowRoutes: RouteRecordRaw[] = [
  {
    path: '/workflows',
    name: 'workflows',
    component: () => import('../../views/WorkflowsPage.vue'),
    meta: { title: 'Workflows' },
  },
  {
    path: '/workflows/playground',
    name: 'workflow-playground',
    component: () => import('../../views/WorkflowPlaygroundPage.vue'),
    meta: { title: 'Workflow Playground', fullBleed: true },
  },
  {
    path: '/workflows/:workflowId/builder',
    name: 'workflow-builder',
    component: () => import('../../views/WorkflowBuilderPage.vue'),
    props: true,
    meta: { title: 'Workflow Builder', fullBleed: true, requiresEntity: 'workflowId' },
  },
];
