import type { RouteRecordRaw } from 'vue-router';

export const teamRoutes: RouteRecordRaw[] = [
  {
    path: '/teams',
    name: 'teams',
    component: () => import('../../views/TeamsPage.vue'),
    meta: { title: 'Teams' },
  },
  {
    path: '/teams/:teamId',
    name: 'team-dashboard',
    component: () => import('../../views/TeamDashboard.vue'),
    props: true,
    meta: { title: 'Team Dashboard', requiresEntity: 'teamId' },
  },
  {
    path: '/teams/:teamId/settings',
    name: 'team-settings',
    component: () => import('../../views/TeamSettingsPage.vue'),
    props: true,
    meta: { title: 'Team Settings', requiresEntity: 'teamId' },
  },
  {
    path: '/teams/:teamId/builder',
    name: 'team-builder',
    component: () => import('../../views/TeamBuilderPage.vue'),
    props: true,
    meta: { title: 'Team Builder', fullBleed: true, requiresEntity: 'teamId' },
  },
];
