import type { RouteRecordRaw } from 'vue-router';

export const settingsRoutes: RouteRecordRaw[] = [
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../../views/SettingsPage.vue'),
    meta: { title: 'Settings' },
  },
  // SSO / SAML Authentication (item 35)
  {
    path: '/settings/sso',
    name: 'sso-settings',
    component: () => import('../../views/SsoSettingsPage.vue'),
    meta: { title: 'SSO / SAML' },
  },
];
