import type { RouteRecordRaw } from 'vue-router';

export const settingsRoutes: RouteRecordRaw[] = [
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../../views/SettingsPage.vue'),
    meta: { title: 'Settings' },
  },
];
