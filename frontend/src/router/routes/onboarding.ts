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
  // Environment Promotion
  {
    path: '/bots/environments',
    name: 'environment-promotion',
    component: () => import('../../views/EnvironmentPromotion.vue'),
    meta: { title: 'Environment Promotion' },
  },
];
