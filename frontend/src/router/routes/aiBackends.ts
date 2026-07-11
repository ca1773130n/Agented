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
  // Council — a debating panel of your AI accounts decides (ai-accounts 0.4.5+)
  {
    path: '/council',
    name: 'council',
    component: () => import('../../views/CouncilPage.vue'),
    meta: { title: 'Council' },
  },
  // Usage history
  {
    path: '/history/usage',
    name: 'usage-history',
    component: () => import('../../views/UsageHistoryPage.vue'),
    meta: { title: 'Usage History' },
  },
];
