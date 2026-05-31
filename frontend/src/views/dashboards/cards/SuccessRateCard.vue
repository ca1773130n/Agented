<!--
  SuccessRateCard — extracted from AnalyticsDashboard.vue for the
  Activity lane (Live ops block).
-->
<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { analyticsApi, ApiError } from '../../../services/api';
import type { ExecutionDataPoint } from '../../../services/api';
import SuccessRateChart from '../../../components/analytics/SuccessRateChart.vue';
import LoadingState from '../../../components/base/LoadingState.vue';
import ErrorState from '../../../components/base/ErrorState.vue';
import {
  type AnalyticsDateRange,
  type AnalyticsGroupBy,
  rangeOptions,
  groupByOptions,
  buildDateRange,
} from './_analyticsFilters';

const emit = defineEmits<{ loaded: [slug: string] }>();
const { t } = useI18n();

const selectedRange = ref<AnalyticsDateRange>('30d');
const selectedGroupBy = ref<AnalyticsGroupBy>('day');

const isLoading = ref(false);
const loadError = ref<string | null>(null);
const executionData = ref<ExecutionDataPoint[]>([]);

const dateRange = computed(() => buildDateRange(selectedRange.value));
const isEmpty = computed(() => executionData.value.length === 0);

async function loadData() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const res = await analyticsApi.fetchExecutionAnalytics({
      group_by: selectedGroupBy.value,
      start_date: dateRange.value.start_date,
      end_date: dateRange.value.end_date,
    });
    executionData.value = res?.data || [];
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : t('successRateCard.error.load');
    executionData.value = [];
  } finally {
    isLoading.value = false;
    emit('loaded', 'success-rate');
  }
}

watch([selectedRange, selectedGroupBy], loadData);
onMounted(loadData);
</script>

<template>
  <section id="success-rate" class="lane-card chart-card">
    <header class="lane-card__head">
      <div>
        <h2 class="lane-card__title">{{ t('successRateCard.title') }}</h2>
        <p class="lane-card__subtitle">{{ t('successRateCard.subtitle') }}</p>
      </div>
      <div class="filter-controls">
        <div class="filter-group">
          <button
            v-for="opt in rangeOptions"
            :key="opt.key"
            class="filter-btn"
            :class="{ active: selectedRange === opt.key }"
            @click="selectedRange = opt.key"
          >{{ opt.label }}</button>
        </div>
        <div class="filter-divider"></div>
        <div class="filter-group">
          <button
            v-for="opt in groupByOptions"
            :key="opt.key"
            class="filter-btn"
            :class="{ active: selectedGroupBy === opt.key }"
            @click="selectedGroupBy = opt.key"
          >{{ opt.label }}</button>
        </div>
      </div>
    </header>

    <LoadingState v-if="isLoading" :message="t('successRateCard.loading')" />
    <ErrorState v-else-if="loadError" :message="loadError" @retry="loadData" />
    <p v-else-if="isEmpty" class="empty">{{ t('successRateCard.empty') }}</p>
    <SuccessRateChart v-else :data="executionData" />
  </section>
</template>

<style scoped>
.lane-card {
  padding: 20px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 10px;
  background: var(--bg-secondary, rgba(255, 255, 255, 0.02));
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.lane-card__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}
.lane-card__title { font-size: 16px; font-weight: 600; margin: 0; color: var(--text-primary); }
.lane-card__subtitle { font-size: 12px; color: var(--text-tertiary); margin: 4px 0 0; }
.empty { padding: 24px; text-align: center; color: var(--text-tertiary); margin: 0; }
.filter-controls {
  display: flex; align-items: center; gap: 4px;
  background: var(--bg-secondary); border: 1px solid var(--border-subtle);
  border-radius: 8px; padding: 4px;
}
.filter-divider { width: 1px; height: 20px; background: var(--border-subtle); margin: 0 4px; }
.filter-group { display: flex; gap: 2px; }
.filter-btn {
  padding: 6px 10px; border: none; border-radius: 6px; background: transparent;
  color: var(--text-tertiary); font-size: 0.75rem; font-weight: 500; cursor: pointer;
  transition: all var(--transition-fast); white-space: nowrap;
}
.filter-btn:hover { color: var(--text-primary); background: var(--bg-tertiary); }
.filter-btn.active { color: var(--accent-cyan); background: var(--accent-cyan-dim); }
</style>
