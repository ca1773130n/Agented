import type { RouteRecordRaw } from 'vue-router';

export const notificationRoutes: RouteRecordRaw[] = [
  // Notification Hub
  {
    path: '/notifications/hub',
    name: 'notification-hub',
    component: () => import('../../views/NotificationHubPage.vue'),
    meta: { title: 'Notification Hub' },
  },
  // Integrations — unified Slack / Ticketing / Channels surface (P2 merge).
  {
    path: '/integrations',
    name: 'integrations',
    component: () => import('../../views/IntegrationsPage.vue'),
    meta: { title: 'Integrations' },
  },
  // Slack Execution Notifications — folded into the Integrations page (P2).
  {
    path: '/integrations/slack-notifications',
    name: 'slack-notifications',
    redirect: () => ({ name: 'integrations', query: { tab: 'slack' } }),
  },
  // Slack Command Gateway
  {
    path: '/integrations/slack-gateway',
    name: 'slack-command-gateway',
    component: () => import('../../views/SlackCommandGatewayPage.vue'),
    meta: { title: 'Slack Command Gateway' },
  },
  // Slack & Teams Notification Channels — folded into the Integrations page (P2).
  {
    path: '/integrations/notification-channels',
    name: 'notification-channels',
    redirect: () => ({ name: 'integrations', query: { tab: 'channels' } }),
  },
  // Integration Ticketing — folded into the Integrations page (P2).
  {
    path: '/integrations/ticketing',
    name: 'integration-ticketing',
    redirect: () => ({ name: 'integrations', query: { tab: 'ticketing' } }),
  },
  // PR-D — On-Call Escalation merged into SchedulingCard's On-Call Policy
  // sub-card inside the Activity lane.
  {
    path: '/integrations/on-call',
    name: 'on-call-escalation',
    redirect: () => ({ name: 'dashboards-activity', hash: '#scheduling' }),
  },
];
