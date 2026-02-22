import type { RouteRecordRaw } from 'vue-router';

export const agentRoutes: RouteRecordRaw[] = [
  {
    path: '/agents',
    name: 'agents',
    component: () => import('../../views/AgentsPage.vue'),
    meta: { title: 'Agents' },
  },
  {
    path: '/agents/new',
    name: 'agent-create',
    component: () => import('../../views/AgentCreateWizard.vue'),
    meta: { title: 'Create Agent' },
  },
  {
    path: '/agents/:agentId',
    name: 'agent-design',
    component: () => import('../../views/AgentDesignPage.vue'),
    props: true,
    meta: { title: 'Agent Design', requiresEntity: 'agentId' },
  },
];
