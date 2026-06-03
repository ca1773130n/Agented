<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import type { HistoryStatsPeriod } from '../services/api';
import { budgetApi, ApiError } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import DataTable from '../components/base/DataTable.vue';
import type { DataTableColumn } from '../components/base/DataTable.vue';
import EmptyState from '../components/base/EmptyState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useWebMcpTool } from '../composables/useWebMcpTool';
import { useToast } from '../composables/useToast';

const { t } = useI18n();
const showToast = useToast();
const selectedPeriod = ref<'weekly' | 'monthly'>('weekly');
const monthsBack = ref<number>(6);
const periods = ref<HistoryStatsPeriod[]>([]);
const isLoading = ref(false);
const loadError = ref<string | null>(null);

async function loadData() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const res = await budgetApi.getHistoryStats({
      period: selectedPeriod.value,
      months_back: monthsBack.value,
    });
    periods.value = res.periods || [];
  } catch (e) {
    // A failed load must not masquerade as "no usage data" — surface it.
    periods.value = [];
    loadError.value = e instanceof ApiError ? e.message : t('usageHistory.loadError');
    showToast(loadError.value, 'error');
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
  name: 'agented_usage_history_get_state',
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

const columns = computed<DataTableColumn[]>(() => [
  { key: 'period_start', label: t('usageHistory.columns.period') },
  { key: 'total_cost_usd', label: t('usageHistory.columns.cost') },
  { key: 'total_input_tokens', label: t('usageHistory.columns.inputTokens') },
  { key: 'total_output_tokens', label: t('usageHistory.columns.outputTokens') },
  { key: 'total_cache_read_tokens', label: t('usageHistory.columns.cacheRead') },
  { key: 'total_cache_creation_tokens', label: t('usageHistory.columns.cacheWrite') },
  { key: 'execution_count', label: t('usageHistory.columns.executions') },
  { key: 'avg_rate_limit_pct', label: t('usageHistory.columns.avgRate') },
  { key: 'max_rate_limit_pct', label: t('usageHistory.columns.maxRate') },
]);

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

    <PageHeader :title="t('usageHistory.title')" :subtitle="t('usageHistory.subtitle')">
      <template #actions>
        <div class="header-controls">
          <div class="period-toggle">
            <button
              class="period-btn"
              :class="{ active: selectedPeriod === 'weekly' }"
              @click="selectedPeriod = 'weekly'; debouncedLoadData()"
            >{{ t('usageHistory.weekly') }}</button>
            <button
              class="period-btn"
              :class="{ active: selectedPeriod === 'monthly' }"
              @click="selectedPeriod = 'monthly'; debouncedLoadData()"
            >{{ t('usageHistory.monthly') }}</button>
          </div>
          <div class="months-toggle">
            <button
              v-for="m in [3, 6, 12]"
              :key="m"
              class="period-btn"
              :class="{ active: monthsBack === m }"
              @click="monthsBack = m; debouncedLoadData()"
            >{{ t('usageHistory.monthsShort', { count: m }) }}</button>
          </div>
        </div>
      </template>
    </PageHeader>

    <div class="notional-note">
      <span class="notional-icon">ⓘ</span>
      <span>{{ t('usageHistory.billingNote') }}</span>
    </div>

    <LoadingState v-if="isLoading" :message="t('usageHistory.loading')" />

    <ErrorState
      v-if="!isLoading && loadError"
      :title="t('usageHistory.loadErrorTitle')"
      :message="loadError"
      @retry="loadData"
    />

    <div v-if="!isLoading && !loadError" class="summary-cards">
      <div class="summary-card">
        <div class="card-label">{{ t('usageHistory.totalCost') }}</div>
        <div class="card-value highlight">{{ formatCurrency(totalCost) }}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">{{ t('usageHistory.inputTokens') }}</div>
        <div class="card-value">{{ formatTokenCount(totalInputTokens) }}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">{{ t('usageHistory.outputTokens') }}</div>
        <div class="card-value">{{ formatTokenCount(totalOutputTokens) }}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">{{ t('usageHistory.executions') }}</div>
        <div class="card-value">{{ totalExecutions }}</div>
      </div>
    </div>

    <EmptyState
      v-if="!isLoading && !loadError && periods.length === 0"
      :title="t('usageHistory.emptyTitle')"
      :description="t('usageHistory.emptyDescription')"
    />

    <div v-if="!isLoading && !loadError && periods.length > 0" class="section">
      <h2 class="section-title">{{ selectedPeriod === 'weekly' ? t('usageHistory.weeklyBreakdown') : t('usageHistory.monthlyBreakdown') }}</h2>
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
        <template #cell-total_cache_read_tokens="{ item }">
          {{ formatTokenCount(item.total_cache_read_tokens || 0) }}
        </template>
        <template #cell-total_cache_creation_tokens="{ item }">
          {{ formatTokenCount(item.total_cache_creation_tokens || 0) }}
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

.notional-note {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: var(--bg-secondary, rgba(255, 255, 255, 0.02));
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
  border-left: 3px solid var(--accent-violet, #a78bfa);
  border-radius: 8px;
  font-size: 0.8rem;
  line-height: 1.45;
  color: var(--text-tertiary, #888);
}

.notional-icon {
  color: var(--accent-violet, #a78bfa);
  flex-shrink: 0;
  font-size: 0.95rem;
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
