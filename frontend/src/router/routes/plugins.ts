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
    path: '/plugins/explore',
    name: 'explore-plugins',
    component: () => import('../../views/ExplorePlugins.vue'),
    meta: { title: 'Explore Plugins' },
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
