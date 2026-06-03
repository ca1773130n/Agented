import type { RouteRecordRaw } from 'vue-router';

export const triggersExtRoutes: RouteRecordRaw[] = [
  // Trigger Tools — unified Conditions / NL / Schedule / Payload / Dry-Run (P2).
  {
    path: '/trigger-tools',
    name: 'trigger-tools',
    component: () => import('../../views/TriggerToolsPage.vue'),
    meta: { title: 'Trigger Tools' },
  },
  // Bot Output Webhook Forwarding
  {
    path: '/integrations/webhook-forwarding',
    name: 'bot-output-webhook-forwarding',
    component: () => import('../../views/BotOutputWebhookForwarding.vue'),
    meta: { title: 'Webhook Output Forwarding' },
  },
  // Webhook Payload Transformer — folded into the Trigger Tools page (P2).
  {
    path: '/webhooks/transformer',
    name: 'webhook-payload-transformer',
    redirect: (to) => ({ name: 'trigger-tools', query: { ...to.query, tab: 'payload' } }),
  },
  // Visual Schedule / Cron Wizard — folded into the Trigger Tools page (P2).
  {
    path: '/scheduling/wizard',
    name: 'visual-cron-wizard',
    redirect: (to) => ({ name: 'trigger-tools', query: { ...to.query, tab: 'schedule' } }),
  },
  // Conditional Trigger Rules Engine — folded into the Trigger Tools page (P2).
  {
    path: '/triggers/conditional-rules',
    name: 'conditional-trigger-rules',
    redirect: (to) => ({ name: 'trigger-tools', query: { ...to.query, tab: 'conditions' } }),
  },
  // Natural Language Trigger Rule Editor — folded into the Trigger Tools page (P2).
  {
    path: '/triggers/nl-rule-editor',
    name: 'nl-trigger-rule-editor',
    redirect: (to) => ({ name: 'trigger-tools', query: { ...to.query, tab: 'nl' } }),
  },
  // Multi-Provider Fallback Chains
  {
    path: '/settings/provider-fallback',
    name: 'multi-provider-fallback',
    component: () => import('../../views/MultiProviderFallback.vue'),
    meta: { title: 'Multi-Provider Fallback' },
  },
  // Smart Schedule Optimizer (feature 37)
  {
    path: '/scheduling/optimizer',
    name: 'smart-schedule-optimizer',
    component: () => import('../../views/SmartScheduleOptimizerPage.vue'),
    meta: { title: 'Smart Schedule Optimizer' },
  },
  // Smart Alert Rules on Findings (item 8)
  {
    path: '/monitoring/alert-rules',
    name: 'smart-alert-rules',
    component: () => import('../../views/SmartAlertRulesPage.vue'),
    meta: { title: 'Smart Alert Rules' },
  },
  // Alert Grouping
  {
    path: '/monitoring/alerts',
    name: 'alert-grouping',
    component: () => import('../../views/AlertGrouping.vue'),
    meta: { title: 'Alert Grouping' },
  },
];
