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
];
