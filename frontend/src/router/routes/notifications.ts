import type { RouteRecordRaw } from 'vue-router';

export const notificationRoutes: RouteRecordRaw[] = [
  // Notification Hub
  {
    path: '/notifications/hub',
    name: 'notification-hub',
    component: () => import('../../views/NotificationHubPage.vue'),
    meta: { title: 'Notification Hub' },
  },
  // Slack Execution Notifications (Feature 7)
  {
    path: '/integrations/slack-notifications',
    name: 'slack-notifications',
    component: () => import('../../views/SlackNotificationsPage.vue'),
    meta: { title: 'Slack Notifications' },
  },
  // Slack Command Gateway
  {
    path: '/integrations/slack-gateway',
    name: 'slack-command-gateway',
    component: () => import('../../views/SlackCommandGatewayPage.vue'),
    meta: { title: 'Slack Command Gateway' },
  },
  // Slack & Teams Notification Channels (feature 9)
  {
    path: '/integrations/notification-channels',
    name: 'notification-channels',
    component: () => import('../../views/TeamsNotificationChannelsPage.vue'),
    meta: { title: 'Notification Channels' },
  },
  // Integration Ticketing
  {
    path: '/integrations/ticketing',
    name: 'integration-ticketing',
    component: () => import('../../views/IntegrationTicketing.vue'),
    meta: { title: 'Ticketing Integrations' },
  },
  // On-Call Escalation
  {
    path: '/integrations/on-call',
    name: 'on-call-escalation',
    component: () => import('../../views/OnCallEscalation.vue'),
    meta: { title: 'On-Call Escalation' },
  },
  // Incident Response Playbook Bots (item 34)
  {
    path: '/bots/incident-playbooks',
    name: 'incident-response-playbooks',
    component: () => import('../../views/IncidentResponsePlaybooksPage.vue'),
    meta: { title: 'Incident Response Playbooks' },
  },
];
