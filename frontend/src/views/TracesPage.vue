<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { tracingApi, type Trace, type TraceStats } from '../services/api/tracing';
import TraceListItem from '../components/tracing/TraceListItem.vue';

const { t } = useI18n();

const traces = ref<Trace[]>([]);
const total = ref(0);
const stats = ref<TraceStats | null>(null);
const isLoading = ref(false);
const loadError = ref<string | null>(null);

// Filters
const statusFilter = ref<string>('all');
const entityTypeFilter = ref<string>('all');
const searchQuery = ref('');

// Pagination
const limit = 100;
const offset = ref(0);

async function load() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const params: { status?: string; entityType?: string; limit: number; offset: number } = {
      limit,
      offset: offset.value,
    };
    if (statusFilter.value !== 'all') params.status = statusFilter.value;
    if (entityTypeFilter.value !== 'all') params.entityType = entityTypeFilter.value;
    const result = await tracingApi.list(params);
    traces.value = result.traces;
    total.value = result.total;
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : t('traces.loadFailed');
  } finally {
    isLoading.value = false;
  }
}

async function loadStats() {
  try {
    stats.value = await tracingApi.stats(
      entityTypeFilter.value !== 'all' ? { entityType: entityTypeFilter.value } : {},
    );
  } catch {
    /* stats are best-effort */
  }
}

watch([statusFilter, entityTypeFilter], () => {
  offset.value = 0;
  load();
});

watch(entityTypeFilter, loadStats);

const filteredTraces = computed(() => {
  if (!searchQuery.value) return traces.value;
  const q = searchQuery.value.toLowerCase();
  return traces.value.filter(
    (tr) => tr.name.toLowerCase().includes(q) || tr.entity_id.toLowerCase().includes(q),
  );
});

onMounted(() => {
  load();
  loadStats();
});

function nextPage() { offset.value += limit; load(); }
function prevPage() { offset.value = Math.max(0, offset.value - limit); load(); }
</script>

<template>
  <div class="traces-page">
    <header class="page-header">
      <h1>{{ t('traces.title') }}</h1>
      <div v-if="stats" class="stats-header" data-testid="stats-header">
        <span>{{ t('traces.statTotal', { count: stats.total_traces }) }}</span>
        <span>{{ t('traces.statCompleted', { count: stats.completed }) }}</span>
        <span>{{ t('traces.statErrors', { count: stats.errors }) }}</span>
      </div>
    </header>

    <div class="filter-bar">
      <select v-model="statusFilter" data-testid="status-filter">
        <option value="all">{{ t('traces.statusOptions.all') }}</option>
        <option value="running">{{ t('traces.statusOptions.running') }}</option>
        <option value="completed">{{ t('traces.statusOptions.completed') }}</option>
        <option value="error">{{ t('traces.statusOptions.error') }}</option>
      </select>
      <select v-model="entityTypeFilter" data-testid="entity-type-filter">
        <option value="all">{{ t('traces.entityOptions.all') }}</option>
        <option value="agent">{{ t('traces.entityOptions.agent') }}</option>
        <option value="super_agent">{{ t('traces.entityOptions.superAgent') }}</option>
        <option value="team">{{ t('traces.entityOptions.team') }}</option>
      </select>
      <input
        v-model="searchQuery"
        type="search"
        :placeholder="t('traces.searchPlaceholder')"
        data-testid="search-filter"
      />
    </div>

    <div v-if="isLoading" data-testid="loading-state">{{ t('traces.loading') }}</div>
    <div v-else-if="loadError" data-testid="error-state" class="error-state">
      {{ loadError }}
      <button @click="load">{{ t('common.retry') }}</button>
    </div>
    <div v-else-if="traces.length === 0" data-testid="empty-state" class="empty-state">
      {{ t('traces.empty') }}
    </div>
    <div v-else class="trace-list">
      <TraceListItem
        v-for="trace in filteredTraces"
        :key="trace.id"
        :trace="trace"
      />
    </div>

    <footer v-if="!isLoading && total > limit" class="pagination">
      <button :disabled="offset === 0" @click="prevPage">{{ t('traces.previous') }}</button>
      <span>{{ t('traces.pageRange', { start: offset + 1, end: Math.min(offset + limit, total), total }) }}</span>
      <button :disabled="offset + limit >= total" @click="nextPage">{{ t('traces.next') }}</button>
    </footer>
  </div>
</template>

<style scoped>
.traces-page { }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.stats-header { display: flex; gap: 16px; color: var(--text-tertiary); font-size: 13px; }
.filter-bar { display: flex; gap: 12px; margin-bottom: 16px; }
.filter-bar select, .filter-bar input { padding: 6px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-subtle); color: var(--text-primary); border-radius: 4px; }
.trace-list { background: var(--bg-secondary); border-radius: 8px; overflow: hidden; }
.empty-state, .error-state { padding: 48px; text-align: center; color: var(--text-tertiary); }
.error-state button { margin-left: 12px; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 16px; margin-top: 16px; color: var(--text-tertiary); font-size: 13px; }
</style>
