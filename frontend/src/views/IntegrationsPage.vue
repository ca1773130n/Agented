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
import { ref, computed, watch, markRaw, nextTick } from 'vue';
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

// ARIA tabs keyboard pattern: arrows cycle, Home/End jump to the ends.
function onTabKeydown(e: KeyboardEvent) {
  const NAV = ['ArrowRight', 'ArrowLeft', 'Home', 'End'];
  if (!NAV.includes(e.key)) return;
  e.preventDefault();
  const idx = validTabs.indexOf(activeTab.value);
  const last = validTabs.length - 1;
  let nextIdx = idx;
  if (e.key === 'ArrowRight') nextIdx = idx >= last ? 0 : idx + 1;
  else if (e.key === 'ArrowLeft') nextIdx = idx <= 0 ? last : idx - 1;
  else if (e.key === 'Home') nextIdx = 0;
  else if (e.key === 'End') nextIdx = last;
  const nextKey = validTabs[nextIdx];
  selectTab(nextKey);
  nextTick(() => {
    document.getElementById(`integrations-tab-${nextKey}`)?.focus();
  });
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
    <div class="integrations-tabs" role="tablist" :aria-label="t('nav.integrations')" @keydown="onTabKeydown">
      <button
        v-for="tab in TABS"
        :id="`integrations-tab-${tab.key}`"
        :key="tab.key"
        type="button"
        role="tab"
        :class="['integrations-tab', { active: activeTab === tab.key }]"
        :aria-selected="activeTab === tab.key"
        aria-controls="integrations-panel"
        :tabindex="activeTab === tab.key ? 0 : -1"
        @click="selectTab(tab.key)"
      >
        {{ t(tab.labelKey) }}
      </button>
    </div>

    <div
      id="integrations-panel"
      class="integrations-panel"
      role="tabpanel"
      :aria-labelledby="`integrations-tab-${activeTab}`"
    >
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
