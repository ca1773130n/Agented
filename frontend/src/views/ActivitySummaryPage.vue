<script setup lang="ts">
/**
 * Activity Summary — daily / weekly "what you did" digest across every
 * registered project, rendered from Tesserae's `tesserae summary` markdown.
 */
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import MarkdownContent from '../components/base/MarkdownContent.vue';
import { memorySystemApi } from '../services/api/memory-system';

const { t } = useI18n();

const period = ref<'day' | 'week'>('day');
// Local YYYY-MM-DD (today). ponytail: native date input, no picker lib.
const today = new Date();
const date = ref(
  `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`,
);
const markdown = ref('');
const loading = ref(false);
const error = ref<string | null>(null);

async function load(refresh = false) {
  loading.value = true;
  error.value = null;
  try {
    const res = await memorySystemApi.activitySummary(period.value, date.value, null, refresh);
    markdown.value = res.markdown || '';
    if (!res.ok) error.value = res.reason || t('activitySummary.failed');
  } catch (e) {
    error.value = (e as Error).message || t('activitySummary.failed');
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
  <div class="activity-summary-page">
    <PageHeader :title="t('activitySummary.title')" :subtitle="t('activitySummary.subtitle')" />

    <div class="as-controls">
      <div class="as-toggle" role="tablist" :aria-label="t('activitySummary.period')">
        <button
          type="button"
          role="tab"
          :aria-selected="period === 'day'"
          :class="{ active: period === 'day' }"
          @click="setPeriod('day')"
        >{{ t('activitySummary.daily') }}</button>
        <button
          type="button"
          role="tab"
          :aria-selected="period === 'week'"
          :class="{ active: period === 'week' }"
          @click="setPeriod('week')"
        >{{ t('activitySummary.weekly') }}</button>
      </div>
      <input
        v-model="date"
        type="date"
        class="as-date"
        :aria-label="t('activitySummary.dateLabel')"
        @change="load()"
      />
      <button type="button" class="as-refresh" :disabled="loading" @click="load(true)">
        {{ loading ? t('activitySummary.loading') : t('activitySummary.refresh') }}
      </button>
    </div>

    <p v-if="error" class="as-error">{{ error }}</p>

    <div v-if="loading && !markdown" class="as-state">{{ t('activitySummary.loading') }}</div>
    <div v-else-if="markdown" class="as-body">
      <MarkdownContent :content="markdown" />
    </div>
    <div v-else-if="!error" class="as-state">{{ t('activitySummary.empty') }}</div>
  </div>
</template>

<style scoped>
.activity-summary-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.as-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.as-toggle {
  display: inline-flex;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  overflow: hidden;
}

.as-toggle button {
  padding: 6px 16px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.as-toggle button.active {
  background: var(--accent-cyan);
  color: var(--text-on-accent);
}

.as-date,
.as-refresh {
  padding: 6px 12px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  font-size: 13px;
}

.as-refresh {
  cursor: pointer;
}

.as-refresh:disabled {
  opacity: 0.6;
  cursor: default;
}

.as-error {
  margin: 0;
  color: var(--danger);
  font-size: 13px;
}

.as-state {
  padding: 32px 0;
  color: var(--text-tertiary);
  font-size: 13px;
}

.as-body {
  padding: 20px 24px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
}
</style>
