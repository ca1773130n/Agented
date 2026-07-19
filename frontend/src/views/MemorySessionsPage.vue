<script setup lang="ts">
/**
 * Session History — Tesserae 0.16 `sessions list`: normalized agent-harness
 * sessions (Claude Code / Codex …) imported into this instance's memory,
 * grouped by day. Sibling of ActivitySummaryPage / DecisionsPage.
 */
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import { memorySystemApi } from '../services/api/memory-system';
import type { HarnessSession } from '../services/api/memory-system';

const { t } = useI18n();

const sessions = ref<HarnessSession[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

// Group by date, newest day first (the CLI already returns newest-first).
const groups = computed(() => {
  const map = new Map<string, HarnessSession[]>();
  for (const s of sessions.value) {
    const key = s.date || '—';
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(s);
  }
  return [...map.entries()].map(([date, items]) => ({ date, items }));
});

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const res = await memorySystemApi.sessions(null, 200);
    sessions.value = res.sessions || [];
    if (!res.ok) error.value = res.reason || t('memorySessions.failed');
  } catch (e) {
    error.value = (e as Error).message || t('memorySessions.failed');
  } finally {
    loading.value = false;
  }
}

onMounted(() => load());
</script>

<template>
  <div class="sessions-page">
    <PageHeader :title="t('memorySessions.title')" :subtitle="t('memorySessions.subtitle')">
      <template #actions>
        <button class="sessions-refresh" :disabled="loading" @click="load()">
          {{ t('memorySessions.refresh') }}
        </button>
      </template>
    </PageHeader>

    <div v-if="loading" class="sessions-state">{{ t('memorySessions.loading') }}</div>
    <div v-else-if="error" class="sessions-state sessions-state--error">{{ error }}</div>
    <div v-else-if="sessions.length === 0" class="sessions-state">{{ t('memorySessions.empty') }}</div>

    <div v-else class="sessions-groups">
      <section v-for="g in groups" :key="g.date" class="sessions-group">
        <h3 class="sessions-day">{{ g.date }} <span class="sessions-day-count">{{ g.items.length }}</span></h3>
        <ul class="sessions-list">
          <li v-for="s in g.items" :key="s.slug" class="session-row">
            <span class="session-harness" :class="`session-harness--${s.harness}`">{{ s.harness }}</span>
            <span class="session-project">{{ s.project }}</span>
            <span class="session-title" :title="s.title">{{ s.title }}</span>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>

<style scoped>
.sessions-page {
  max-width: 920px;
}
.sessions-refresh {
  padding: 6px 14px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: transparent;
  color: var(--text-primary, #e4e4e7);
  font-size: 13px;
  cursor: pointer;
}
.sessions-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.sessions-state {
  padding: 40px;
  text-align: center;
  color: var(--text-secondary, #a1a1aa);
}
.sessions-state--error {
  color: var(--danger);
}
.sessions-groups {
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 16px;
}
.sessions-day {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary, #a1a1aa);
  margin: 0 0 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.sessions-day-count {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary, #71717a);
  background: rgba(255, 255, 255, 0.06);
  border-radius: 100px;
  padding: 1px 8px;
}
.sessions-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.session-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  min-width: 0;
}
.session-harness {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
  text-transform: uppercase;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-secondary, #a1a1aa);
  flex-shrink: 0;
}
.session-harness--claude {
  background: rgba(217, 119, 87, 0.15);
  color: #e5a07f;
}
.session-harness--codex {
  background: rgba(16, 163, 127, 0.15);
  color: #34d399;
}
.session-project {
  font-size: 12px;
  color: var(--text-secondary, #71717a);
  flex-shrink: 0;
}
.session-title {
  font-size: 13px;
  color: var(--text-primary, #d4d4d8);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
