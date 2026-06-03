import type { RouteRecordRaw } from 'vue-router';

export const executionRoutes: RouteRecordRaw[] = [
  // Execution Tools — unified Search / Tagging / Replay-Diff / Annotations (P2).
  {
    path: '/execution-tools',
    name: 'execution-tools',
    component: () => import('../../views/ExecutionToolsPage.vue'),
    meta: { title: 'Execution Tools' },
  },
  // Execution Search — folded into the Execution Tools page (P2).
  {
    path: '/execution-search',
    name: 'execution-search',
    redirect: (to) => ({ name: 'execution-tools', query: { ...to.query, tab: 'search' } }),
  },
  // Execution Replay & Diff — folded into the Execution Tools page (P2).
  {
    path: '/executions/replay',
    name: 'execution-replay-diff',
    redirect: (to) => ({ name: 'execution-tools', query: { ...to.query, tab: 'replay' } }),
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
  // Execution Annotation & Quality Feedback — folded into Execution Tools (P2).
  {
    path: '/executions/annotations',
    name: 'execution-annotation',
    redirect: (to) => ({ name: 'execution-tools', query: { ...to.query, tab: 'annotations' } }),
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
  // Execution Tagging & Full-Text Search — folded into Execution Tools (P2).
  {
    path: '/executions/tagging',
    name: 'execution-tagging',
    redirect: (to) => ({ name: 'execution-tools', query: { ...to.query, tab: 'tagging' } }),
  },
];
