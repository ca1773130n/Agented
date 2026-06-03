<script setup lang="ts">
/**
 * IntegrationsPage — unified host for the three integration surfaces that
 * all sit on the single `db_integrations` table (differentiated only by
 * `integration_type`). Replaces three standalone sidebar slots + routes
 * (slack-notifications / integration-ticketing / notification-channels)
 * with one tabbed page. The old routes redirect here with `?tab=`.
 *
 * Each tab renders its original view component unchanged (they are
 * router-free and bring their own PageHeader + actions), so all existing
 * functionality is preserved; only the active tab mounts.
 */
import { ref, computed, watch, markRaw } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import ChannelsViewSrc from './TeamsNotificationChannelsPage.vue';
import SlackViewSrc from './SlackNotificationsPage.vue';
import TicketingViewSrc from './IntegrationTicketing.vue';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();

// Only the active tab is mounted (<component :is>), so just one view fetches
// at a time. markRaw keeps the component objects out of reactivity.
const ChannelsView = markRaw(ChannelsViewSrc);
const SlackView = markRaw(SlackViewSrc);
const TicketingView = markRaw(TicketingViewSrc);

// Reuse the existing, already-localized sidebar labels for the tabs
// (Notification Channels / Slack Notifications / Jira · Linear) so no new
// i18n keys are needed in any locale.
const TABS = [
  { key: 'channels', labelKey: 'nav.notificationChannels', view: ChannelsView },
  { key: 'slack', labelKey: 'nav.slackNotifications', view: SlackView },
  { key: 'ticketing', labelKey: 'nav.jiraLinear', view: TicketingView },
] as const;

const validTabs = TABS.map((tb) => tb.key) as readonly string[];

function normalizeTab(raw: unknown): string {
  const v = String(raw ?? '');
  return validTabs.includes(v) ? v : 'channels';
}

const activeTab = ref(normalizeTab(route.query.tab));

const activeView = computed(
  () => TABS.find((tb) => tb.key === activeTab.value)?.view ?? ChannelsView,
);

function selectTab(key: string) {
  if (key === activeTab.value) return;
  activeTab.value = key;
  // Reflect the tab in the URL so it's deep-linkable / bookmarkable.
  router.replace({ query: { ...route.query, tab: key } });
}

// Keep the active tab in sync when the `?tab=` query changes externally
// (redirect landings from the old routes, browser back/forward).
watch(
  () => route.query.tab,
  (raw) => {
    const next = normalizeTab(raw);
    if (next !== activeTab.value) activeTab.value = next;
  },
);
</script>

<template>
  <div class="integrations-page">
    <div class="integrations-tabs" role="tablist" :aria-label="t('nav.integrations')">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        type="button"
        role="tab"
        :class="['integrations-tab', { active: activeTab === tab.key }]"
        :aria-selected="activeTab === tab.key"
        @click="selectTab(tab.key)"
      >
        {{ t(tab.labelKey) }}
      </button>
    </div>

    <div class="integrations-panel" role="tabpanel">
      <component :is="activeView" />
    </div>
  </div>
</template>

<style scoped>
.integrations-page {
  display: flex;
  flex-direction: column;
}

.integrations-tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--border-default);
  margin-bottom: 20px;
  padding: 0 4px;
}

.integrations-tab {
  appearance: none;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary, #888);
  font-size: 0.9rem;
  font-weight: 500;
  padding: 10px 16px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
  margin-bottom: -1px;
}

.integrations-tab:hover {
  color: var(--text-primary, #fff);
}

.integrations-tab.active {
  color: var(--accent-cyan, #00d4ff);
  border-bottom-color: var(--accent-cyan, #00d4ff);
}

.integrations-tab:focus-visible {
  outline: 2px solid var(--accent-cyan, #00d4ff);
  outline-offset: 2px;
  border-radius: 4px;
}
</style>
