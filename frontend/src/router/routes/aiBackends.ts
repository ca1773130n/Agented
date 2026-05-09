import type { RouteRecordRaw } from 'vue-router';

export const aiBackendRoutes: RouteRecordRaw[] = [
  // AI Backends
  {
    path: '/backends',
    name: 'ai-backends',
    component: () => import('../../views/AIBackendsPage.vue'),
    meta: { title: 'AI Backends' },
  },
  {
    path: '/backends/:backendId',
    name: 'backend-detail',
    component: () => import('../../views/BackendDetailPage.vue'),
    props: true,
    meta: { title: 'Backend Detail', requiresEntity: 'backendId' },
  },
  // Usage history
  {
    path: '/history/usage',
    name: 'usage-history',
    component: () => import('../../views/UsageHistoryPage.vue'),
    meta: { title: 'Usage History' },
  },
];
