import type { RouteRecordRaw } from 'vue-router';

export const codeBlockRoutes: RouteRecordRaw[] = [
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
