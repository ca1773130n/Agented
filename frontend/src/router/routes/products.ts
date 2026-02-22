import type { RouteRecordRaw } from 'vue-router';

export const productRoutes: RouteRecordRaw[] = [
  {
    path: '/products',
    name: 'products',
    component: () => import('../../views/ProductsPage.vue'),
    meta: { title: 'Products' },
  },
  {
    path: '/products/:productId',
    name: 'product-dashboard',
    component: () => import('../../views/ProductDashboard.vue'),
    props: true,
    meta: { title: 'Product Dashboard', requiresEntity: 'productId' },
  },
  {
    path: '/products/:productId/settings',
    name: 'product-settings',
    component: () => import('../../views/ProductSettingsPage.vue'),
    props: true,
    meta: { title: 'Product Settings', requiresEntity: 'productId' },
  },
];
