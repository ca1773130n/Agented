<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { HistoryStatsPeriod } from '../services/api';
import { budgetApi } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import DataTable from '../components/base/DataTable.vue';
import type { DataTableColumn } from '../components/base/DataTable.vue';
import EmptyState from '../components/base/EmptyState.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();

const selectedPeriod = ref<'weekly' | 'monthly'>('weekly');
const monthsBack = ref<number>(6);
const periods = ref<HistoryStatsPeriod[]>([]);
const isLoading = ref(false);

async function loadData() {
  isLoading.value = true;
  try {
    const res = await budgetApi.getHistoryStats({
      period: selectedPeriod.value,
      months_back: monthsBack.value,
    });
    periods.value = res.periods || [];
  } catch {
    periods.value = [];
  } finally {
    isLoading.value = false;
  }
}

const totalCost = computed(() => periods.value.reduce((s, p) => s + p.total_cost_usd, 0));
const totalInputTokens = computed(() => periods.value.reduce((s, p) => s + p.total_input_tokens, 0));
const totalOutputTokens = computed(() => periods.value.reduce((s, p) => s + p.total_output_tokens, 0));
const totalExecutions = computed(() => periods.value.reduce((s, p) => s + p.execution_count, 0));

function formatCurrency(value: number): string {
  return `$${value.toFixed(2)}`;
}

function formatTokenCount(n: number): string {
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + 'B';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return n.toString();
}

useWebMcpTool({
  name: 'hive_usage_history_get_state',
  description: 'Returns the current state of the UsageHistoryPage',
  page: 'UsageHistoryPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'UsageHistoryPage',
        isLoading: isLoading.value,
        selectedPeriod: selectedPeriod.value,
        monthsBack: monthsBack.value,
        periodsCount: periods.value.length,
        totalCost: totalCost.value,
        totalInputTokens: totalInputTokens.value,
        totalOutputTokens: totalOutputTokens.value,
        totalExecutions: totalExecutions.value,
      }),
    }],
  }),
  deps: [isLoading, selectedPeriod, monthsBack, periods, totalCost, totalInputTokens, totalOutputTokens, totalExecutions],
});

const columns: DataTableColumn[] = [
  { key: 'period_start', label: 'Period' },
  { key: 'total_cost_usd', label: 'Cost' },
  { key: 'total_input_tokens', label: 'Input Tokens' },
  { key: 'total_output_tokens', label: 'Output Tokens' },
  { key: 'execution_count', label: 'Executions' },
  { key: 'avg_rate_limit_pct', label: 'Avg Rate %' },
  { key: 'max_rate_limit_pct', label: 'Max Rate %' },
];

function formatPeriodLabel(periodStart: string): string {
  if (selectedPeriod.value === 'monthly' && /^\d{4}-\d{2}$/.test(periodStart)) {
    const [year, month] = periodStart.split('-');
    const date = new Date(Number(year), Number(month) - 1, 1);
    return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short' });
  }
  return periodStart;
}

let loadDebounceTimer: ReturnType<typeof setTimeout> | null = null;

function debouncedLoadData() {
  if (loadDebounceTimer) clearTimeout(loadDebounceTimer);
  loadDebounceTimer = setTimeout(() => loadData(), 150);
}

onMounted(loadData);
</script>

<template>
  <div class="usage-history-page">
    <AppBreadcrumb :items="[
      { label: 'Dashboards', action: () => router.push({ name: 'dashboards' }) },
      { label: 'Usage History' },
    ]" />

    <PageHeader title="Usage History" subtitle="Historical token usage, cost, and rate limit statistics">
      <template #actions>
        <div class="header-controls">
          <div class="period-toggle">
            <button
              class="period-btn"
              :class="{ active: selectedPeriod === 'weekly' }"
              @click="selectedPeriod = 'weekly'; debouncedLoadData()"
            >Weekly</button>
            <button
              class="period-btn"
              :class="{ active: selectedPeriod === 'monthly' }"
              @click="selectedPeriod = 'monthly'; debouncedLoadData()"
            >Monthly</button>
          </div>
          <div class="months-toggle">
            <button
              v-for="m in [3, 6, 12]"
              :key="m"
              class="period-btn"
              :class="{ active: monthsBack === m }"
              @click="monthsBack = m; debouncedLoadData()"
            >{{ m }}mo</button>
          </div>
        </div>
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" message="Loading history..." />

    <div v-if="!isLoading" class="summary-cards">
      <div class="summary-card">
        <div class="card-label">Total Cost</div>
        <div class="card-value highlight">{{ formatCurrency(totalCost) }}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">Input Tokens</div>
        <div class="card-value">{{ formatTokenCount(totalInputTokens) }}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">Output Tokens</div>
        <div class="card-value">{{ formatTokenCount(totalOutputTokens) }}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">Executions</div>
        <div class="card-value">{{ totalExecutions }}</div>
      </div>
    </div>

    <EmptyState
      v-if="!isLoading && periods.length === 0"
      title="No usage data found"
      description="No usage data found for the selected range."
    />

    <div v-if="!isLoading && periods.length > 0" class="section">
      <h2 class="section-title">{{ selectedPeriod === 'weekly' ? 'Weekly' : 'Monthly' }} Breakdown</h2>
      <DataTable :columns="columns" :items="periods">
        <template #cell-period_start="{ item }">
          <span class="period-cell">{{ formatPeriodLabel(item.period_start) }}</span>
        </template>
        <template #cell-total_cost_usd="{ item }">
          <span class="cost-cell">{{ formatCurrency(item.total_cost_usd) }}</span>
        </template>
        <template #cell-total_input_tokens="{ item }">
          {{ formatTokenCount(item.total_input_tokens) }}
        </template>
        <template #cell-total_output_tokens="{ item }">
          {{ formatTokenCount(item.total_output_tokens) }}
        </template>
        <template #cell-execution_count="{ item }">
          {{ item.execution_count }}
        </template>
        <template #cell-avg_rate_limit_pct="{ item }">
          {{ item.avg_rate_limit_pct != null ? item.avg_rate_limit_pct + '%' : '--' }}
        </template>
        <template #cell-max_rate_limit_pct="{ item }">
          <span v-if="item.max_rate_limit_pct != null" :class="{ 'rate-high': item.max_rate_limit_pct >= 80 }">
            {{ item.max_rate_limit_pct }}%
          </span>
          <span v-else>--</span>
        </template>
      </DataTable>
    </div>
  </div>
</template>

<style scoped>
.usage-history-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.header-controls {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.period-toggle,
.months-toggle {
  display: flex;
  gap: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 4px;
}

.period-btn {
  padding: 8px 14px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.period-btn:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.period-btn.active {
  color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.summary-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 20px;
}

.card-label {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}

.card-value {
  font-family: var(--font-mono);
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--text-primary);
}

.card-value.highlight {
  color: var(--accent-violet);
}

.section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 24px;
}

.section-title {
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 20px;
}

.period-cell {
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.cost-cell {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--accent-violet);
}

.rate-high {
  color: #ff3366;
  font-weight: 600;
}

@media (max-width: 900px) {
  .summary-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
