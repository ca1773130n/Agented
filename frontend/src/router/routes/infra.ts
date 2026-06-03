import type { RouteRecordRaw } from 'vue-router';

export const infraRoutes: RouteRecordRaw[] = [
  // Plugin SDK & CLI — folded into the Help page (P2).
  {
    path: '/plugins/sdk',
    name: 'plugin-sdk',
    redirect: (to) => ({ name: 'help', query: { ...to.query, tab: 'plugin-sdk' } }),
  },
  // Plugin Execution Sandboxing (Feature 37)
  {
    path: '/plugins/sandbox',
    name: 'plugin-sandbox',
    component: () => import('../../views/PluginSandboxPage.vue'),
    meta: { title: 'Plugin Sandbox' },
  },
  // Secrets Vault
  {
    path: '/settings/secrets',
    name: 'secrets-vault',
    component: () => import('../../views/SecretsVault.vue'),
    meta: { title: 'Secrets Vault' },
  },
  // Configurable Data Retention Policies (feature 39)
  {
    path: '/settings/retention',
    name: 'data-retention-policies',
    component: () => import('../../views/DataRetentionPoliciesPage.vue'),
    meta: { title: 'Data Retention Policies' },
  },
];
