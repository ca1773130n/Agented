import type { RouteRecordRaw } from 'vue-router';

export const promptRoutes: RouteRecordRaw[] = [
  // Structured Output
  {
    path: '/bots/structured-output',
    name: 'structured-output',
    component: () => import('../../views/StructuredOutputPage.vue'),
    meta: { title: 'Structured Output' },
  },
  // Prompt Optimizer
  {
    path: '/bots/prompt-optimizer',
    name: 'prompt-optimizer',
    component: () => import('../../views/PromptOptimizer.vue'),
    meta: { title: 'Prompt Optimizer' },
  },
  // Context Window Visualizer
  {
    path: '/bots/context-window',
    name: 'context-window-visualizer',
    component: () => import('../../views/ContextWindowVisualizer.vue'),
    meta: { title: 'Context Window Visualizer' },
  },
  // Prompt A/B Testing
  {
    path: '/bots/ab-testing',
    name: 'prompt-ab-testing',
    component: () => import('../../views/PromptABTesting.vue'),
    meta: { title: 'Prompt A/B Testing' },
  },
  // Automatic Codebase Context Injection
  {
    path: '/bots/context-injection',
    name: 'auto-context-injection',
    component: () => import('../../views/AutoContextInjection.vue'),
    meta: { title: 'Auto Context Injection' },
  },
  // Inline Prompt Editor with Live Preview
  {
    path: '/bots/prompt-editor',
    name: 'inline-prompt-editor',
    component: () => import('../../views/InlinePromptEditor.vue'),
    meta: { title: 'Inline Prompt Editor' },
  },
  // Full Conversation History Viewer (feature 33)
  {
    path: '/executions/conversation-history',
    name: 'conversation-history-viewer',
    component: () => import('../../views/ConversationHistoryViewer.vue'),
    meta: { title: 'Conversation History' },
  },
  // Prompt Template Playground (Feature 2)
  {
    path: '/bots/prompt-playground',
    name: 'prompt-template-playground',
    component: () => import('../../views/PromptTemplatePlayground.vue'),
    meta: { title: 'Prompt Template Playground' },
  },
  // Non-English Prompt Localization (Feature 38)
  {
    path: '/bots/prompt-localization',
    name: 'prompt-localization',
    component: () => import('../../views/PromptLocalizationPage.vue'),
    meta: { title: 'Prompt Localization' },
  },
  // Prompt Template Version History (item 3)
  {
    path: '/bots/prompt-versions',
    name: 'prompt-version-history',
    component: () => import('../../views/PromptVersionHistoryPage.vue'),
    meta: { title: 'Prompt Version History' },
  },
];
