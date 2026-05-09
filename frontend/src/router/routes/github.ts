import type { RouteRecordRaw } from 'vue-router';

export const githubRoutes: RouteRecordRaw[] = [
  // GitHub Actions Integration
  {
    path: '/integrations/github-actions',
    name: 'github-actions',
    component: () => import('../../views/GitHubActionsPage.vue'),
    meta: { title: 'GitHub Actions' },
  },
  // GitHub PR Annotation Integration
  {
    path: '/integrations/github-pr-annotations',
    name: 'github-pr-annotation',
    component: () => import('../../views/GitHubPRAnnotation.vue'),
    meta: { title: 'GitHub PR Annotations' },
  },
  // AI-Powered PR Auto-Assignment
  {
    path: '/integrations/pr-auto-assign',
    name: 'pr-auto-assignment',
    component: () => import('../../views/PrAutoAssignmentPage.vue'),
    meta: { title: 'PR Auto-Assignment' },
  },
  // One-Click GitHub App Install (Feature 14)
  {
    path: '/integrations/github-app-install',
    name: 'github-app-install',
    component: () => import('../../views/GitHubAppInstallPage.vue'),
    meta: { title: 'GitHub App Install' },
  },
  // PR Review Learning Loop (feature 7)
  {
    path: '/integrations/pr-review-learning',
    name: 'pr-review-learning-loop',
    component: () => import('../../views/PrReviewLearningLoopPage.vue'),
    meta: { title: 'PR Review Learning Loop' },
  },
  // GitOps Bot Configuration Sync (Feature 28)
  {
    path: '/settings/gitops-sync',
    name: 'gitops-sync',
    component: () => import('../../views/GitOpsSyncPage.vue'),
    meta: { title: 'GitOps Sync' },
  },
];
