<script setup lang="ts">
/**
 * TabbedViewHost — a reusable host that presents a set of full page views as
 * tabs. Used to collapse several standalone sidebar surfaces (which were all
 * variations on one domain) into a single page without rewriting the views:
 * each tab renders its original view component unchanged, and only the active
 * tab is mounted.
 *
 * - The active tab is reflected in the URL `?tab=` (deep-linkable), and stays
 *   in sync when the query changes externally (redirect landings, back/fwd).
 * - Implements the ARIA tabs authoring pattern: tablist/tab/tabpanel roles,
 *   aria-controls / aria-labelledby wiring, roving tabindex, and
 *   Arrow/Home/End keyboard navigation.
 *
 * Callers should pass already-`markRaw`d components to avoid Vue proxying them.
 */
import { ref, computed, watch, nextTick, type Component } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';

interface TabDef {
  /** Stable key, used in the URL (`?tab=key`) and element ids. */
  key: string;
  /** i18n key for the tab label. */
  labelKey: string;
  /** The view component to render when this tab is active. */
  component: Component;
}

const props = defineProps<{
  tabs: TabDef[];
  /** i18n key for the tablist's accessible label. (Not `aria*`-prefixed:
   *  Vue treats `aria-` attributes as native passthrough, not props.) */
  tablistLabelKey: string;
  /** Prefix for element ids so multiple hosts don't collide. */
  idPrefix: string;
}>();

const { t } = useI18n();
const route = useRoute();
const router = useRouter();

const keys = computed(() => props.tabs.map((tb) => tb.key));
const fallback = computed(() => props.tabs[0]?.key ?? '');

function normalizeTab(raw: unknown): string {
  const v = String(raw ?? '');
  return keys.value.includes(v) ? v : fallback.value;
}

const activeTab = ref(normalizeTab(route.query.tab));

const activeView = computed(
  () => props.tabs.find((tb) => tb.key === activeTab.value)?.component ?? props.tabs[0]?.component,
);

function selectTab(key: string) {
  if (key === activeTab.value) return;
  activeTab.value = key;
  router.replace({ query: { ...route.query, tab: key } });
}

function onKeydown(e: KeyboardEvent) {
  const NAV = ['ArrowRight', 'ArrowLeft', 'Home', 'End'];
  if (!NAV.includes(e.key)) return;
  e.preventDefault();
  const ks = keys.value;
  const idx = ks.indexOf(activeTab.value);
  const last = ks.length - 1;
  let nextIdx = idx;
  if (e.key === 'ArrowRight') nextIdx = idx >= last ? 0 : idx + 1;
  else if (e.key === 'ArrowLeft') nextIdx = idx <= 0 ? last : idx - 1;
  else if (e.key === 'Home') nextIdx = 0;
  else if (e.key === 'End') nextIdx = last;
  const nextKey = ks[nextIdx];
  selectTab(nextKey);
  nextTick(() => document.getElementById(`${props.idPrefix}-tab-${nextKey}`)?.focus());
}

watch(
  () => route.query.tab,
  (raw) => {
    const next = normalizeTab(raw);
    if (next !== activeTab.value) activeTab.value = next;
  },
);
</script>

<template>
  <div class="tabbed-view-host">
    <div class="tvh-tabs" role="tablist" :aria-label="t(tablistLabelKey)" @keydown="onKeydown">
      <button
        v-for="tab in tabs"
        :id="`${idPrefix}-tab-${tab.key}`"
        :key="tab.key"
        type="button"
        role="tab"
        :class="['tvh-tab', { active: activeTab === tab.key }]"
        :aria-selected="activeTab === tab.key"
        :aria-controls="`${idPrefix}-panel`"
        :tabindex="activeTab === tab.key ? 0 : -1"
        @click="selectTab(tab.key)"
      >
        {{ t(tab.labelKey) }}
      </button>
    </div>

    <div
      :id="`${idPrefix}-panel`"
      class="tvh-panel"
      role="tabpanel"
      :aria-labelledby="`${idPrefix}-tab-${activeTab}`"
    >
      <component :is="activeView" />
    </div>
  </div>
</template>

<style scoped>
.tabbed-view-host {
  display: flex;
  flex-direction: column;
}

.tvh-tabs {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--border-default);
  margin-bottom: 20px;
  padding: 0 4px;
}

.tvh-tab {
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

.tvh-tab:hover {
  color: var(--text-primary, #fff);
}

.tvh-tab.active {
  color: var(--accent-cyan, #00d4ff);
  border-bottom-color: var(--accent-cyan, #00d4ff);
}

.tvh-tab:focus-visible {
  outline: 2px solid var(--accent-cyan, #00d4ff);
  outline-offset: 2px;
  border-radius: 4px;
}
</style>
