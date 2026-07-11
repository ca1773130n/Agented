import type { RouteRecordRaw } from 'vue-router';

export const observabilityRoutes: RouteRecordRaw[] = [
  {
    path: '/activity-summary',
    name: 'activity-summary',
    component: () => import('../../views/ActivitySummaryPage.vue'),
    meta: { title: 'Activity Summary' },
  },
  {
    path: '/decisions',
    name: 'decisions',
    component: () => import('../../views/DecisionsPage.vue'),
    meta: { title: 'Decisions' },
  },
  {
    path: '/memory/doctor',
    name: 'memory-doctor',
    component: () => import('../../views/MemoryDoctorPage.vue'),
    meta: { title: 'Memory Health' },
  },
  {
    path: '/memory/graph',
    name: 'memory-graph',
    component: () => import('../../views/KnowledgeGraphPage.vue'),
    meta: { title: 'Knowledge Graph' },
  },
  {
    path: '/memory/research',
    name: 'memory-research',
    component: () => import('../../views/MemoryResearchPage.vue'),
    meta: { title: 'Memory Research' },
  },
  {
    path: '/memory/sessions',
    name: 'memory-sessions',
    component: () => import('../../views/MemorySessionsPage.vue'),
    meta: { title: 'Session History' },
  },
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
  {
    // v0.6.3: operator dashboard for the v0.5.12 session_events audit log.
    path: '/admin/session-events',
    name: 'session-events',
    component: () => import('../../views/SessionEventsPage.vue'),
    meta: { title: 'Session Events', requiresRole: 'admin' },
  },
];
