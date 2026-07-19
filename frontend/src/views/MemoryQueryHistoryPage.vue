<script setup lang="ts">
/**
 * Memory Query History — read-later log of every memory/observability query
 * dispatched as a background job (useMemoryJob). Lists all kinds newest-first;
 * clicking a row loads the full result (getMemoryJob) into an inline panel.
 * Kind-specific result rendering is deferred to the per-kind pages; here we
 * surface the raw result payload as pretty JSON (v1) plus status/timestamps.
 */
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import EmptyState from '../components/base/EmptyState.vue';
import { memorySystemApi } from '../services/api/memory-system';
import type { MemoryJobSummary, MemoryJob } from '../services/api/memory-system';

const { t } = useI18n();

const jobs = ref<MemoryJobSummary[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

// Inline expander for the selected row's full result.
const expandedId = ref<string | null>(null);
const detail = ref<MemoryJob | null>(null);
const detailLoading = ref(false);
const detailError = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const res = await memorySystemApi.listMemoryJobs();
    jobs.value = res.jobs || [];
  } catch (e) {
    error.value = (e as Error).message || t('memoryHistory.failed');
  } finally {
    loading.value = false;
  }
}

async function toggleRow(job: MemoryJobSummary) {
  if (expandedId.value === job.job_id) {
    expandedId.value = null;
    detail.value = null;
    return;
  }
  expandedId.value = job.job_id;
  detail.value = null;
  detailError.value = null;
  detailLoading.value = true;
  try {
    detail.value = await memorySystemApi.getMemoryJob(job.job_id);
  } catch (e) {
    detailError.value = (e as Error).message || t('memoryHistory.detailFailed');
  } finally {
    detailLoading.value = false;
  }
}

function prettyResult(result: unknown): string {
  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return String(result);
  }
}

// Compact relative time ("3m ago") from an ISO timestamp.
function relTime(iso: string | null): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const secs = Math.round((Date.now() - then) / 1000);
  if (secs < 60) return t('memoryHistory.relNow');
  const mins = Math.round(secs / 60);
  if (mins < 60) return t('memoryHistory.relMinutes', { n: mins });
  const hours = Math.round(mins / 60);
  if (hours < 24) return t('memoryHistory.relHours', { n: hours });
  const days = Math.round(hours / 24);
  return t('memoryHistory.relDays', { n: days });
}

function absTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function statusMod(status: string): string {
  if (status === 'completed') return 'ok';
  if (status === 'failed') return 'error';
  return 'running';
}

onMounted(load);
</script>

<template>
  <div class="history-page">
    <PageHeader :title="t('memoryHistory.title')" :subtitle="t('memoryHistory.subtitle')">
      <template #actions>
        <button class="history-refresh" :disabled="loading" @click="load()">
          {{ t('memoryHistory.refresh') }}
        </button>
      </template>
    </PageHeader>

    <LoadingState v-if="loading && !jobs.length" :message="t('memoryHistory.loading')" />
    <ErrorState
      v-else-if="error"
      :title="t('memoryHistory.failed')"
      :message="error"
      @retry="load"
    />
    <EmptyState
      v-else-if="!jobs.length"
      :title="t('memoryHistory.emptyTitle')"
      :description="t('memoryHistory.emptyDescription')"
    />

    <ul v-else class="history-list">
      <li v-for="job in jobs" :key="job.job_id" class="history-item">
        <button
          type="button"
          class="history-row"
          :aria-expanded="expandedId === job.job_id"
          @click="toggleRow(job)"
        >
          <span class="history-kind">{{ t(`memoryHistory.kind.${job.kind}`, job.kind) }}</span>
          <span class="history-label" :title="job.label">{{ job.label || job.job_id }}</span>
          <span class="history-status" :class="`history-status--${statusMod(job.status)}`">
            {{ t(`memoryJob.status.${job.status}`, job.status) }}
          </span>
          <span class="history-time" :title="absTime(job.created_at)">{{ relTime(job.created_at) }}</span>
        </button>

        <div v-if="expandedId === job.job_id" class="history-detail">
          <LoadingState v-if="detailLoading" :message="t('memoryHistory.detailLoading')" />
          <p v-else-if="detailError" class="history-detail-error">{{ detailError }}</p>
          <template v-else-if="detail">
            <div class="history-meta">
              <span class="history-meta-item">
                <span class="history-meta-label">{{ t('memoryHistory.metaStatus') }}</span>
                <span class="history-status" :class="`history-status--${statusMod(detail.status)}`">
                  {{ t(`memoryJob.status.${detail.status}`, detail.status) }}
                </span>
              </span>
              <span class="history-meta-item">
                <span class="history-meta-label">{{ t('memoryHistory.metaStarted') }}</span>
                <span class="history-meta-value">{{ absTime(detail.started_at) }}</span>
              </span>
              <span class="history-meta-item">
                <span class="history-meta-label">{{ t('memoryHistory.metaFinished') }}</span>
                <span class="history-meta-value">{{ absTime(detail.finished_at) }}</span>
              </span>
            </div>
            <p v-if="job.error" class="history-detail-error">{{ job.error }}</p>
            <pre class="history-json">{{ prettyResult(detail.result) }}</pre>
          </template>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.history-page {
  max-width: 920px;
}
.history-refresh {
  padding: 6px 14px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}
.history-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.history-list {
  list-style: none;
  padding: 0;
  margin: 16px 0 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.history-item {
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  overflow: hidden;
}
.history-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  color: var(--text-primary);
  transition: background var(--transition-fast);
}
.history-row:hover {
  background: var(--bg-tertiary);
}
.history-kind {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  padding: 3px 9px;
  border-radius: 100px;
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
  flex-shrink: 0;
}
.history-label {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-status {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 9px;
  border-radius: 100px;
  flex-shrink: 0;
}
.history-status--ok {
  background: var(--accent-emerald-dim);
  color: var(--success);
}
.history-status--error {
  background: var(--accent-crimson-dim);
  color: var(--danger);
}
.history-status--running {
  background: var(--accent-amber-dim);
  color: var(--warning);
}
.history-time {
  font-size: 12px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}
.history-detail {
  border-top: 1px solid var(--border-subtle);
  padding: 12px 14px;
  background: var(--bg-secondary);
}
.history-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 10px;
}
.history-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.history-meta-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--text-tertiary);
}
.history-meta-value {
  font-size: 12px;
  color: var(--text-secondary);
}
.history-detail-error {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--danger);
}
.history-json {
  margin: 0;
  padding: 12px;
  border-radius: 8px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  line-height: 1.5;
  max-height: 480px;
  overflow: auto;
  white-space: pre;
}
</style>
