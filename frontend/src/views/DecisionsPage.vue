<script setup lang="ts">
/**
 * Decisions — human (AskUserQuestion) + agent decisions across every registered
 * project in a day/week window, from Tesserae 0.15.0's `tesserae decisions`.
 * Sibling of ActivitySummaryPage; same controls, structured cards instead of md.
 */
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import { memorySystemApi } from '../services/api/memory-system';
import type { Decision } from '../services/api/memory-system';

const { t } = useI18n();

const period = ref<'day' | 'week'>('day');
const today = new Date();
const date = ref(
  `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`,
);
// Default OFF: deterministic human (AskUserQuestion) decisions load fast and
// need no LLM; the user opts into the slower LLM agent-decision mining.
const includeAgent = ref(false);
const decisions = ref<Decision[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

// Group by project, preserving order of first appearance.
const groups = computed(() => {
  const map = new Map<string, Decision[]>();
  for (const d of decisions.value) {
    const key = d.project || '—';
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(d);
  }
  return [...map.entries()].map(([project, items]) => ({ project, items }));
});

function alternatives(d: Decision): string[] {
  return (d.options || []).filter((o) => o !== d.answer);
}

function when(ts: string): string {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const res = await memorySystemApi.decisions(period.value, date.value, null, includeAgent.value);
    decisions.value = res.decisions || [];
    if (!res.ok) error.value = res.reason || t('decisions.failed');
  } catch (e) {
    error.value = (e as Error).message || t('decisions.failed');
  } finally {
    loading.value = false;
  }
}

function setPeriod(p: 'day' | 'week') {
  if (period.value === p) return;
  period.value = p;
  load();
}

onMounted(load);
</script>

<template>
  <div class="decisions-page">
    <PageHeader :title="t('decisions.title')" :subtitle="t('decisions.subtitle')" />

    <div class="dc-controls">
      <div class="dc-toggle" role="tablist" :aria-label="t('decisions.period')">
        <button
          type="button"
          role="tab"
          :aria-selected="period === 'day'"
          :class="{ active: period === 'day' }"
          @click="setPeriod('day')"
        >{{ t('decisions.daily') }}</button>
        <button
          type="button"
          role="tab"
          :aria-selected="period === 'week'"
          :class="{ active: period === 'week' }"
          @click="setPeriod('week')"
        >{{ t('decisions.weekly') }}</button>
      </div>
      <input
        v-model="date"
        type="date"
        class="dc-date"
        :aria-label="t('decisions.dateLabel')"
        @change="load"
      />
      <label class="dc-check">
        <input v-model="includeAgent" type="checkbox" @change="load" />
        {{ t('decisions.includeAgent') }}
      </label>
      <button type="button" class="dc-refresh" :disabled="loading" @click="load">
        {{ loading ? t('decisions.loading') : t('decisions.refresh') }}
      </button>
    </div>

    <p v-if="error" class="dc-error">{{ error }}</p>

    <div v-if="loading && !decisions.length" class="dc-state">{{ t('decisions.loading') }}</div>
    <div v-else-if="groups.length" class="dc-groups">
      <section v-for="g in groups" :key="g.project" class="dc-group">
        <h2 class="dc-group__title">{{ g.project }}</h2>
        <div class="dc-cards">
          <article v-for="(d, i) in g.items" :key="i" class="dc-card">
            <div class="dc-card__top">
              <span class="dc-badge" :class="`dc-badge--${d.source}`">
                {{ d.source === 'human' ? t('decisions.human') : t('decisions.agent') }}
              </span>
              <span v-if="d.header" class="dc-header-chip">{{ d.header }}</span>
              <span class="dc-when">{{ when(d.ts) }}</span>
            </div>
            <p class="dc-question">{{ d.question }}</p>
            <p class="dc-answer"><span class="dc-arrow">→</span> {{ d.answer }}</p>
            <p v-if="alternatives(d).length" class="dc-alts">
              {{ t('decisions.alternatives') }}: {{ alternatives(d).join(' · ') }}
            </p>
            <p v-if="d.rationale" class="dc-rationale">{{ d.rationale }}</p>
          </article>
        </div>
      </section>
    </div>
    <div v-else class="dc-state">{{ t('decisions.empty') }}</div>
  </div>
</template>

<style scoped>
.decisions-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.dc-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.dc-toggle {
  display: inline-flex;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  overflow: hidden;
}

.dc-toggle button {
  padding: 6px 16px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.dc-toggle button.active {
  background: var(--accent-cyan);
  color: var(--text-on-accent);
}

.dc-date,
.dc-refresh {
  padding: 6px 12px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  font-size: 13px;
}

.dc-refresh {
  cursor: pointer;
}

.dc-refresh:disabled {
  opacity: 0.6;
  cursor: default;
}

.dc-check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
}

.dc-error {
  margin: 0;
  color: var(--danger);
  font-size: 13px;
}

.dc-state {
  padding: 32px 0;
  color: var(--text-tertiary);
  font-size: 13px;
}

.dc-groups {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.dc-group__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 10px;
  text-transform: none;
}

.dc-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.dc-card {
  padding: 14px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
}

.dc-card__top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.dc-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
}

.dc-badge--human {
  background: color-mix(in srgb, var(--accent-cyan) 22%, transparent);
  color: var(--accent-cyan);
}

.dc-badge--agent {
  background: color-mix(in srgb, var(--accent-violet) 22%, transparent);
  color: var(--accent-violet);
}

.dc-header-chip {
  font-size: 11px;
  color: var(--text-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 2px 8px;
}

.dc-when {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-tertiary);
}

.dc-question {
  margin: 0 0 6px;
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.4;
}

.dc-answer {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-cyan);
}

.dc-arrow {
  opacity: 0.7;
}

.dc-alts {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.dc-rationale {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}
</style>
