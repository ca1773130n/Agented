import type { RouteRecordRaw } from 'vue-router';

export const pluginRoutes: RouteRecordRaw[] = [
  {
    path: '/plugins',
    name: 'plugins',
    component: () => import('../../views/PluginsPage.vue'),
    meta: { title: 'Plugins' },
  },
  {
    path: '/plugins/design',
    name: 'plugin-design',
    component: () => import('../../views/PluginDesignPage.vue'),
    meta: { title: 'Plugin Design' },
  },
  {
    // Redirect: replaced by unified Marketplace (PR-C).
    // Kept so old links and any programmatic `router.push({ name:
    // 'explore-plugins' })` continue to resolve.
    path: '/plugins/explore',
    name: 'explore-plugins',
    redirect: () => ({ name: 'marketplace', query: { type: 'plugins' } }),
  },
  {
    path: '/plugins/:pluginId',
    name: 'plugin-detail',
    component: () => import('../../views/PluginDetailPage.vue'),
    props: true,
    meta: { title: 'Plugin Detail', requiresEntity: 'pluginId' },
  },
  {
    path: '/harness',
    name: 'harness-integration',
    component: () => import('../../views/HarnessIntegration.vue'),
    meta: { title: 'Harness Integration' },
  },
];
