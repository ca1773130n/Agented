import type { RouteRecordRaw } from 'vue-router';

export const triggersExtRoutes: RouteRecordRaw[] = [
  // Webhook Recorder
  {
    path: '/webhooks/recorder',
    name: 'webhook-recorder',
    component: () => import('../../views/WebhookRecorder.vue'),
    meta: { title: 'Webhook Recorder' },
  },
  // Bot Output Webhook Forwarding
  {
    path: '/integrations/webhook-forwarding',
    name: 'bot-output-webhook-forwarding',
    component: () => import('../../views/BotOutputWebhookForwarding.vue'),
    meta: { title: 'Webhook Output Forwarding' },
  },
  // Webhook Payload Transformer (Feature 37)
  {
    path: '/webhooks/transformer',
    name: 'webhook-payload-transformer',
    component: () => import('../../views/WebhookPayloadTransformerPage.vue'),
    meta: { title: 'Webhook Payload Transformer' },
  },
  // Trigger Simulation & Test Harness
  {
    path: '/triggers/simulation',
    name: 'trigger-simulation',
    component: () => import('../../views/TriggerSimulation.vue'),
    meta: { title: 'Trigger Simulation' },
  },
  // Visual Schedule / Cron Wizard
  {
    path: '/scheduling/wizard',
    name: 'visual-cron-wizard',
    component: () => import('../../views/VisualCronWizard.vue'),
    meta: { title: 'Schedule Wizard' },
  },
  // Conditional Trigger Rules Engine (Feature 12)
  {
    path: '/triggers/conditional-rules',
    name: 'conditional-trigger-rules',
    component: () => import('../../views/ConditionalTriggerRulesPage.vue'),
    meta: { title: 'Conditional Trigger Rules' },
  },
  // Natural Language Trigger Rule Editor
  {
    path: '/triggers/nl-rule-editor',
    name: 'nl-trigger-rule-editor',
    component: () => import('../../views/NLTriggerRuleEditor.vue'),
    meta: { title: 'Natural Language Trigger Rules' },
  },
  // Multi-Provider Fallback Chains
  {
    path: '/settings/provider-fallback',
    name: 'multi-provider-fallback',
    component: () => import('../../views/MultiProviderFallback.vue'),
    meta: { title: 'Multi-Provider Fallback' },
  },
  // Dependency-Aware Scheduling (feature 30)
  {
    path: '/scheduling/dependency',
    name: 'dependency-aware-scheduling',
    component: () => import('../../views/DependencyAwareSchedulingPage.vue'),
    meta: { title: 'Dependency-Aware Scheduling' },
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
  // Repository Context Indexing
  {
    path: '/bots/repo-context',
    name: 'repo-context-indexing',
    component: () => import('../../views/RepoContextIndexingPage.vue'),
    meta: { title: 'Repository Context Indexing' },
  },
];
