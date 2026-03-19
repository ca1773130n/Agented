<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { analyticsApi } from '../services/api';
import type {
  CostDataPoint,
  ExecutionDataPoint,
  EffectivenessOverTimePoint,
} from '../services/api';
import CostTrendChart from '../components/analytics/CostTrendChart.vue';
import ExecutionVolumeChart from '../components/analytics/ExecutionVolumeChart.vue';
import SuccessRateChart from '../components/analytics/SuccessRateChart.vue';
import BotEffectivenessChart from '../components/analytics/BotEffectivenessChart.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';
const showToast = useToast();

// Filter state
type DateRange = '7d' | '30d' | '90d';
type GroupBy = 'day' | 'week' | 'month';

const selectedRange = ref<DateRange>('30d');
const selectedGroupBy = ref<GroupBy>('day');

const rangeOptions: { key: DateRange; label: string }[] = [
  { key: '7d', label: '7 Days' },
  { key: '30d', label: '30 Days' },
  { key: '90d', label: '90 Days' },
];

const groupByOptions: { key: GroupBy; label: string }[] = [
  { key: 'day', label: 'Day' },
  { key: 'week', label: 'Week' },
  { key: 'month', label: 'Month' },
];

// Data state
const isLoading = ref(false);
const costData = ref<CostDataPoint[]>([]);
const executionData = ref<ExecutionDataPoint[]>([]);
const effectivenessSummary = ref<{
  accepted: number;
  ignored: number;
  pending: number;
  acceptance_rate: number;
}>({ accepted: 0, ignored: 0, pending: 0, acceptance_rate: 0 });
const effectivenessOverTime = ref<EffectivenessOverTimePoint[]>([]);

function toLocalDateString(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

const dateRange = computed(() => {
  const now = new Date();
  const days = selectedRange.value === '7d' ? 7 : selectedRange.value === '30d' ? 30 : 90;
  const start = new Date(now);
  start.setDate(start.getDate() - days);
  return {
    start_date: toLocalDateString(start),
    end_date: toLocalDateString(now),
  };
});

const isEmpty = computed(() => {
  return costData.value.length === 0
    && executionData.value.length === 0
    && effectivenessSummary.value.accepted === 0
    && effectivenessSummary.value.ignored === 0
    && effectivenessSummary.value.pending === 0;
});

async function loadData() {
  isLoading.value = true;
  const params = {
    group_by: selectedGroupBy.value,
    start_date: dateRange.value.start_date,
    end_date: dateRange.value.end_date,
  };

  try {
    const [costRes, execRes, effRes] = await Promise.all([
      analyticsApi.fetchCostAnalytics(params),
      analyticsApi.fetchExecutionAnalytics(params),
      analyticsApi.fetchEffectiveness(params),
    ]);

    costData.value = costRes?.data || [];
    executionData.value = execRes?.data || [];

    if (effRes) {
      effectivenessSummary.value = {
        accepted: effRes.accepted || 0,
        ignored: effRes.ignored || 0,
        pending: effRes.pending || 0,
        acceptance_rate: effRes.acceptance_rate || 0,
      };
      effectivenessOverTime.value = effRes.over_time || [];
    }
  } catch {
    showToast('Failed to load analytics data', 'error');
    costData.value = [];
    executionData.value = [];
    effectivenessSummary.value = { accepted: 0, ignored: 0, pending: 0, acceptance_rate: 0 };
    effectivenessOverTime.value = [];
  } finally {
    isLoading.value = false;
  }
}

watch([selectedRange, selectedGroupBy], loadData);
onMounted(loadData);
</script>

<template>
  <div class="analytics-dashboard">
    <PageHeader title="Analytics Dashboard" subtitle="Execution costs, volume, success rates, and bot effectiveness">
      <template #actions>
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
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" message="Loading analytics..." />

    <div v-else-if="isEmpty" class="empty-state">
      <p class="empty-title">No execution data yet</p>
      <p class="empty-subtitle">Run some bots to see analytics here.</p>
    </div>

    <div v-else class="charts-grid">
      <div class="chart-card">
        <h3 class="chart-title">Cost Trend</h3>
        <p class="chart-subtitle">Spending over time by entity</p>
        <CostTrendChart :data="costData" />
      </div>

      <div class="chart-card">
        <h3 class="chart-title">Execution Volume</h3>
        <p class="chart-subtitle">Success, failed, and cancelled executions</p>
        <ExecutionVolumeChart :data="executionData" />
      </div>

      <div class="chart-card">
        <h3 class="chart-title">Success Rate</h3>
        <p class="chart-subtitle">Percentage of successful executions</p>
        <SuccessRateChart :data="executionData" />
      </div>

      <div class="chart-card">
        <h3 class="chart-title">Bot Effectiveness</h3>
        <p class="chart-subtitle">PR review acceptance rate</p>
        <BotEffectivenessChart
          :summary="effectivenessSummary"
          :over-time="effectivenessOverTime"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.analytics-dashboard {
  display: flex;
  flex-direction: column;
  gap: 24px;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.filter-controls {
  display: flex;
  align-items: center;
  gap: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 4px;
}

.filter-divider {
  width: 1px;
  height: 20px;
  background: var(--border-subtle);
  margin: 0 4px;
}

.filter-group {
  display: flex;
  gap: 2px;
}

.filter-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.filter-btn:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.filter-btn.active {
  color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
}

.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.chart-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 20px;
}

.chart-title {
  font-family: 'Geist Mono', 'SF Mono', monospace;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px 0;
}

.chart-subtitle {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin: 0 0 12px 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 24px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  text-align: center;
}

.empty-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 8px 0;
}

.empty-subtitle {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  margin: 0;
}

@media (max-width: 900px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }

  .filter-controls {
    flex-wrap: wrap;
  }
}
</style>
