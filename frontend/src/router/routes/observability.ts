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
  {
    path: '/agents/:id/memory',
    name: 'agent-memory',
    component: () => import('../../views/MemoryPage.vue'),
    meta: { title: 'Agent Memory' },
    props: true,
  },
  {
    path: '/agents/:id/memory/threads/:thread_id',
    name: 'agent-memory-thread-detail',
    component: () => import('../../views/ThreadDetailPage.vue'),
    meta: { title: 'Memory Thread Detail' },
    props: true,
  },
];
