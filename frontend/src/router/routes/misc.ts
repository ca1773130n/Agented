import type { RouteRecordRaw } from 'vue-router';

export const miscRoutes: RouteRecordRaw[] = [
  // Sketch
  {
    path: '/sketches',
    name: 'sketch-chat',
    component: () => import('../../views/SketchChatPage.vue'),
    meta: { title: 'Sketch Chat' },
  },
  // Usage history
  {
    path: '/history/usage',
    name: 'usage-history',
    component: () => import('../../views/UsageHistoryPage.vue'),
    meta: { title: 'Usage History' },
  },
  // AI Backends
  {
    path: '/backends',
    name: 'ai-backends',
    component: () => import('../../views/AIBackendsPage.vue'),
    meta: { title: 'AI Backends' },
  },
  {
    path: '/backends/health',
    name: 'service-health',
    component: () => import('../../views/ServiceHealthDashboard.vue'),
    meta: { title: 'Service Health' },
  },
  {
    path: '/backends/:backendId',
    name: 'backend-detail',
    component: () => import('../../views/BackendDetailPage.vue'),
    props: true,
    meta: { title: 'Backend Detail', requiresEntity: 'backendId' },
  },
  // Hooks
  {
    path: '/hooks',
    name: 'hooks',
    component: () => import('../../views/HooksPage.vue'),
    meta: { title: 'Hooks' },
  },
  {
    path: '/hooks/design/:hookId?',
    name: 'hook-design',
    component: () => import('../../views/HookDesignPage.vue'),
    props: true,
    meta: { title: 'Hook Design' },
  },
  // Commands
  {
    path: '/commands',
    name: 'commands',
    component: () => import('../../views/CommandsPage.vue'),
    meta: { title: 'Commands' },
  },
  {
    path: '/commands/design/:commandId?',
    name: 'command-design',
    component: () => import('../../views/CommandDesignPage.vue'),
    props: true,
    meta: { title: 'Command Design' },
  },
  // Rules
  {
    path: '/rules',
    name: 'rules',
    component: () => import('../../views/RulesPage.vue'),
    meta: { title: 'Rules' },
  },
  {
    path: '/rules/design/:ruleId?',
    name: 'rule-design',
    component: () => import('../../views/RuleDesignPage.vue'),
    props: true,
    meta: { title: 'Rule Design' },
  },
];
