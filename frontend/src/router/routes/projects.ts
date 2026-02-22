import type { RouteRecordRaw } from 'vue-router';

export const projectRoutes: RouteRecordRaw[] = [
  {
    path: '/projects',
    name: 'projects',
    component: () => import('../../views/ProjectsPage.vue'),
    meta: { title: 'Projects' },
  },
  {
    path: '/projects/:projectId',
    name: 'project-dashboard',
    component: () => import('../../views/ProjectDashboard.vue'),
    props: true,
    meta: { title: 'Project Dashboard', requiresEntity: 'projectId' },
  },
  {
    path: '/projects/:projectId/settings',
    name: 'project-settings',
    component: () => import('../../views/ProjectSettingsPage.vue'),
    props: true,
    meta: { title: 'Project Settings', requiresEntity: 'projectId' },
  },
  {
    path: '/projects/:projectId/management',
    name: 'project-management',
    component: () => import('../../views/ProjectManagementPage.vue'),
    props: true,
    meta: { title: 'Project Management', requiresEntity: 'projectId' },
  },
];
