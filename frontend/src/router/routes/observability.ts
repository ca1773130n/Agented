import type { RouteRecordRaw } from 'vue-router';

export const observabilityRoutes: RouteRecordRaw[] = [
  {
    path: '/traces',
    name: 'traces-list',
    component: () => import('../../views/TracesPage.vue'),
    meta: { title: 'Traces' },
  },
  {
    path: '/traces/:id',
    name: 'trace-detail',
    component: () => import('../../views/TraceDetailPage.vue'),
    meta: { title: 'Trace Detail' },
  },
];
