import type { RouteRecordRaw } from 'vue-router';

export const superAgentRoutes: RouteRecordRaw[] = [
  {
    path: '/super-agents',
    name: 'super-agents',
    component: () => import('../../views/SuperAgentsPage.vue'),
    meta: { title: 'Super Agents' },
  },
  {
    path: '/super-agents/explore',
    name: 'explore-super-agents',
    component: () => import('../../views/ExploreSuperAgents.vue'),
    meta: { title: 'Explore Super Agents' },
  },
  {
    path: '/super-agents/:superAgentId/playground',
    name: 'super-agent-playground',
    component: () => import('../../views/SuperAgentPlayground.vue'),
    props: true,
    meta: { title: 'Super Agent Playground', requiresEntity: 'superAgentId' },
  },
  {
    // v0.7.7: Super-Agent Activity Inspector — timeline + rollup + JSON drill-down.
    path: '/super-agents/:superAgentId/inspector',
    name: 'super-agent-inspector',
    component: () => import('../../views/SuperAgentInspectorPage.vue'),
    props: true,
    meta: { title: 'Super Agent Inspector', requiresEntity: 'superAgentId' },
  },
  {
    path: '/projects/:projectId/instances/:instanceId/playground',
    name: 'project-instance-playground',
    component: () => import('../../views/SuperAgentPlayground.vue'),
    props: true,
    meta: { title: 'Instance Playground' },
  },
];
