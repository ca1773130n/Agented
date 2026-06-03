<script setup lang="ts">
/**
 * Integrations — unified host for the three integration surfaces that all sit
 * on the single `db_integrations` table (slack / ticketing / channels). The
 * three old routes redirect here with `?tab=`; the views are composed via
 * TabbedViewHost (only the active tab mounts).
 */
import { markRaw } from 'vue';
import TabbedViewHost from '../components/base/TabbedViewHost.vue';
import ChannelsView from './TeamsNotificationChannelsPage.vue';
import SlackView from './SlackNotificationsPage.vue';
import TicketingView from './IntegrationTicketing.vue';

// Reuse the existing, already-localized sidebar labels — no new i18n keys.
const tabs = [
  { key: 'channels', labelKey: 'nav.notificationChannels', component: markRaw(ChannelsView) },
  { key: 'slack', labelKey: 'nav.slackNotifications', component: markRaw(SlackView) },
  { key: 'ticketing', labelKey: 'nav.jiraLinear', component: markRaw(TicketingView) },
];
</script>

<template>
  <TabbedViewHost :tabs="tabs" tablist-label-key="nav.integrations" id-prefix="integrations" />
</template>
