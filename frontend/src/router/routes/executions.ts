import type { RouteRecordRaw } from 'vue-router';

export const executionRoutes: RouteRecordRaw[] = [
  // Execution Search
  {
    path: '/execution-search',
    name: 'execution-search',
    component: () => import('../../views/ExecutionSearchPage.vue'),
    meta: { title: 'Execution Search' },
  },
  // Execution Replay & Diff
  {
    path: '/executions/replay',
    name: 'execution-replay-diff',
    component: () => import('../../views/ExecutionReplayDiff.vue'),
    meta: { title: 'Execution Replay & Diff' },
  },
  // Execution Cost Estimator
  {
    path: '/bots/cost-estimator',
    name: 'execution-cost-estimator',
    component: () => import('../../views/ExecutionCostEstimator.vue'),
    meta: { title: 'Execution Cost Estimator' },
  },
  // PR-D — Execution Queue folded into the Activity lane.
  {
    path: '/executions/queue',
    name: 'execution-queue-dashboard',
    redirect: () => ({ name: 'dashboards-activity', hash: '#execution-queue' }),
  },
  // Execution File Diff Viewer
  {
    path: '/executions/diff-viewer',
    name: 'execution-file-diff-viewer',
    component: () => import('../../views/ExecutionFileDiffViewer.vue'),
    meta: { title: 'Execution File Diff Viewer' },
  },
  // Execution Annotation & Quality Feedback
  {
    path: '/executions/annotations',
    name: 'execution-annotation',
    component: () => import('../../views/ExecutionAnnotation.vue'),
    meta: { title: 'Execution Annotations' },
  },
  // Execution Time-Travel Debugger
  {
    path: '/executions/time-travel',
    name: 'execution-time-travel-debugger',
    component: () => import('../../views/ExecutionTimeTravelDebugger.vue'),
    meta: { title: 'Time-Travel Debugger' },
  },
  // Live Execution Terminal
  {
    path: '/executions/:executionId/terminal',
    name: 'live-execution-terminal',
    component: () => import('../../views/LiveExecutionTerminal.vue'),
    props: true,
    meta: { title: 'Live Execution Terminal' },
  },
  // Execution Quota & Rate Controls (Feature 19)
  {
    path: '/settings/execution-quotas',
    name: 'execution-quota-controls',
    component: () => import('../../views/ExecutionQuotaControls.vue'),
    meta: { title: 'Execution Quotas & Rate Controls' },
  },
  // Mobile Execution Monitor (Feature 30)
  {
    path: '/executions/monitor',
    name: 'mobile-execution-monitor',
    component: () => import('../../views/MobileExecutionMonitor.vue'),
    meta: { title: 'Execution Monitor' },
  },
  // Execution Output Artifacts (Feature 34)
  {
    path: '/executions/artifacts',
    name: 'execution-artifacts',
    component: () => import('../../views/ExecutionArtifactsPage.vue'),
    meta: { title: 'Execution Artifacts' },
  },
  // Execution Timeline — Gantt-style view (item 22)
  {
    path: '/executions/timeline',
    name: 'execution-timeline',
    component: () => import('../../views/ExecutionTimelinePage.vue'),
    meta: { title: 'Execution Timeline' },
  },
  // Execution Tagging & Full-Text Search (feature 23)
  {
    path: '/executions/tagging',
    name: 'execution-tagging',
    component: () => import('../../views/ExecutionTaggingPage.vue'),
    meta: { title: 'Execution Tagging & Search' },
  },
  // Shareable Execution Live Links (Feature 34)
  {
    path: '/executions/share',
    name: 'shareable-execution-links',
    component: () => import('../../views/ShareableExecutionLinksPage.vue'),
    meta: { title: 'Shareable Execution Links' },
  },
];
