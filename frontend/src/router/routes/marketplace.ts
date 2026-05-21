import type { RouteRecordRaw } from 'vue-router';

export const marketplaceRoutes: RouteRecordRaw[] = [
  {
    path: '/marketplace',
    name: 'marketplace',
    component: () => import('../../views/MarketplacePage.vue'),
    meta: { title: 'Marketplace' },
  },
];
