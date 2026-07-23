<script setup lang="ts">
/**
 * Session History — Tesserae 0.16 `sessions list`: normalized agent-harness
 * sessions (Claude Code / Codex …) imported into this instance's memory,
 * grouped by day. Sibling of ActivitySummaryPage / DecisionsPage.
 */
import { computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import { useMemoryJob } from '../composables/useMemoryJob';
import type { HarnessSession, SessionsResult } from '../services/api/memory-system';

const { t } = useI18n();

// Runs as a BACKGROUND job — the operator can leave the page; results persist
// to the query-history store and are shown instantly on the next visit.
const { result, error: jobError, running, run, showLatest } = useMemoryJob<SessionsResult>('sessions');

const sessions = computed<HarnessSession[]>(() => result.value?.sessions || []);
// Surface either a transport/job error, or a completed-but-not-ok reason.
const error = computed<string | null>(() => {
  if (jobError.value) return jobError.value;
  if (result.value && !result.value.ok) return result.value.reason || t('memorySessions.failed');
  return null;
});

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

function refresh() {
  run({ limit: 200 });
}

onMounted(() => showLatest());
</script>

<template>
  <div class="sessions-page">
    <PageHeader :title="t('memorySessions.title')" :subtitle="t('memorySessions.subtitle')">
      <template #actions>
        <button class="sessions-refresh" :disabled="running" @click="refresh()">
          {{ running ? t('memoryJob.running') : t('memorySessions.refresh') }}
        </button>
      </template>
    </PageHeader>

    <div v-if="running" class="sessions-state">
      {{ t('memorySessions.loading') }}
      <p class="sessions-bg-note">{{ t('memoryJob.background') }}</p>
    </div>
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
.sessions-bg-note {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-tertiary, #71717a);
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
