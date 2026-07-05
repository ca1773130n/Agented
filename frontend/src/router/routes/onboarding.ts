import type { RouteRecordRaw } from 'vue-router';

export const onboardingRoutes: RouteRecordRaw[] = [
  // New Engineer Onboarding Automation
  {
    path: '/bots/onboarding',
    name: 'onboarding-automation',
    component: () => import('../../views/OnboardingAutomationPage.vue'),
    meta: { title: 'Onboarding Automation' },
  },
  // Sketch
  {
    path: '/sketches',
    name: 'sketch-chat',
    component: () => import('../../views/SketchChatPage.vue'),
    meta: { title: 'Sketch Chat' },
  },
  // Research (top-level, project-scoped via in-page picker)
  {
    path: '/research',
    name: 'research',
    component: () => import('../../views/ResearchPage.vue'),
    meta: { title: 'Research' },
  },
];
