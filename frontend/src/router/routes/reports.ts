import type { RouteRecordRaw } from 'vue-router';

export const reportsRoutes: RouteRecordRaw[] = [
  // Report Digests
  {
    path: '/reports/digests',
    name: 'report-digests',
    component: () => import('../../views/ReportDigestsPage.vue'),
    meta: { title: 'Report Digests' },
  },
  // Project Activity Timeline
  {
    path: '/projects/activity',
    name: 'project-activity-timeline',
    component: () => import('../../views/ProjectActivityTimeline.vue'),
    meta: { title: 'Project Activity Timeline' },
  },
  // Project Health Scorecard (Feature 36)
  {
    path: '/projects/health-scorecard',
    name: 'project-health-scorecard',
    component: () => import('../../views/ProjectHealthScorecardPage.vue'),
    meta: { title: 'Project Health Scorecard' },
  },
  // Team Activity Feed (Feature 17)
  {
    path: '/teams/activity-feed',
    name: 'team-activity-feed',
    component: () => import('../../views/TeamActivityFeedPage.vue'),
    meta: { title: 'Team Activity Feed' },
  },
  // PR-D — Team Automation Leaderboard folded into the Activity lane.
  {
    path: '/dashboards/leaderboard',
    name: 'team-leaderboard',
    redirect: () => ({ name: 'dashboards-activity', hash: '#roi-leaderboard' }),
  },
  // PR-D — Cross-Team Insights folded into the Activity lane.
  {
    path: '/dashboards/cross-team-insights',
    name: 'cross-team-insights',
    redirect: () => ({ name: 'dashboards-activity', hash: '#cross-team-insights' }),
  },
  // Changelog Generator
  {
    path: '/tools/changelog',
    name: 'changelog-generator',
    component: () => import('../../views/ChangelogGenerator.vue'),
    meta: { title: 'Changelog Generator' },
  },
];
