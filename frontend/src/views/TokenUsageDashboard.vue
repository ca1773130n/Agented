<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import type { UsageSummaryEntry, EntityUsageEntry, BudgetLimit, MonitoringStatus, SnapshotHistory, SessionStatsSummary, RotationDashboardStatus } from '../services/api';
import { budgetApi, agentApi, teamApi, triggerApi, monitoringApi, rotationApi } from '../services/api';
import TokenUsageChart from '../components/monitoring/TokenUsageChart.vue';
import BudgetLimitForm from '../components/monitoring/BudgetLimitForm.vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import TokenBreakdownCard from '../components/monitoring/TokenBreakdownCard.vue';
import MonitoringSection from '../components/monitoring/MonitoringSection.vue';
import EntitySpendSection from '../components/monitoring/EntitySpendSection.vue';
import BudgetLimitsSection from '../components/monitoring/BudgetLimitsSection.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const showToast = useToast();

// Period selection
type PeriodOption = '7d' | '30d' | 'month' | 'custom';
const selectedPeriod = ref<PeriodOption>('7d');
const periodOptions: { key: PeriodOption; label: string }[] = [
  { key: '7d', label: 'Last 7 Days' }, { key: '30d', label: 'Last 30 Days' },
  { key: 'month', label: 'This Month' }, { key: 'custom', label: 'Custom Range' },
];
const customStartDate = ref('');
const customEndDate = ref('');
const chartType = ref<'bar' | 'line'>('bar');
const activeEntityTab = ref<'agent' | 'team' | 'trigger'>('agent');

// Data state
const summaryData = ref<UsageSummaryEntry[]>([]);
const entityData = ref<EntityUsageEntry[]>([]);
const budgetLimits = ref<BudgetLimit[]>([]);
const isLoading = ref(false);
const sessionStats = ref<SessionStatsSummary | null>(null);
const sessionCollecting = ref(false);
const allTimeSpend = ref<number | null>(null);
const agents = ref<{ id: string; name: string }[]>([]);
const teams = ref<{ id: string; name: string }[]>([]);
const triggers = ref<{ id: string; name: string }[]>([]);

// Budget form modal state
const showBudgetForm = ref(false);
const budgetFormMode = ref<'create' | 'edit'>('create');
const selectedLimit = ref<BudgetLimit | null>(null);

// Monitoring state
const monitoringStatus = ref<MonitoringStatus | null>(null);
const trendHistories = ref<Record<string, SnapshotHistory>>({});
const previousThresholdState = ref<Record<string, string>>({});
const pollingInterval = ref<ReturnType<typeof setInterval> | null>(null);
const monitoringLoading = ref(false);
const pollNowLoading = ref(false);
const monitoringRefreshing = ref(false);
const selectedRateWindows = ref<Record<number, '24h' | '48h' | '72h' | '96h' | '120h'>>({});
const expandedCards = ref<Set<number>>(new Set());
const selectedProjectionWindow = ref<Record<number, string>>({});

// Rotation state
const rotationStatus = ref<RotationDashboardStatus | null>(null);
const rotationPollingInterval = ref<ReturnType<typeof setInterval> | null>(null);

useWebMcpTool({
  name: 'agented_token_usage_get_state',
  description: 'Returns the current state of the TokenUsageDashboard',
  page: 'TokenUsageDashboard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'TokenUsageDashboard',
        isLoading: isLoading.value,
        selectedPeriod: selectedPeriod.value,
        chartType: chartType.value,
        activeEntityTab: activeEntityTab.value,
        summaryDataCount: summaryData.value.length,
        entityDataCount: entityData.value.length,
        budgetLimitsCount: budgetLimits.value.length,
        showBudgetForm: showBudgetForm.value,
        monitoringLoading: monitoringLoading.value,
        allTimeSpend: allTimeSpend.value,
        sessionCollecting: sessionCollecting.value,
      }),
    }],
  }),
  deps: [isLoading, selectedPeriod, chartType, activeEntityTab, summaryData, entityData, budgetLimits, showBudgetForm, monitoringLoading, allTimeSpend, sessionCollecting],
});

async function fetchRotationStatus() {
  try {
    rotationStatus.value = await rotationApi.getStatus();
  } catch { /* ignore -- rotation API may not be available */ }
}

function startRotationPolling() {
  stopRotationPolling();
  rotationPollingInterval.value = setInterval(fetchRotationStatus, 15000);
}

function stopRotationPolling() {
  if (rotationPollingInterval.value) {
    clearInterval(rotationPollingInterval.value);
    rotationPollingInterval.value = null;
  }
}

function toLocalDateString(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

const customDateError = computed(() => {
  if (selectedPeriod.value !== 'custom') return '';
  if (!customStartDate.value || !customEndDate.value) return '';
  if (customStartDate.value > customEndDate.value) return 'Start date must be before or equal to end date';
  return '';
});

const dateRange = computed(() => {
  const now = new Date();
  let start: Date, end = new Date(now);
  switch (selectedPeriod.value) {
    case '7d': start = new Date(now); start.setDate(start.getDate() - 7); break;
    case '30d': start = new Date(now); start.setDate(start.getDate() - 30); break;
    case 'month': start = new Date(now.getFullYear(), now.getMonth(), 1); break;
    case 'custom':
      start = customStartDate.value ? new Date(customStartDate.value) : new Date(now.getTime() - 7 * 86400000);
      end = customEndDate.value ? new Date(customEndDate.value) : new Date(now); break;
    default: start = new Date(now); start.setDate(start.getDate() - 7);
  }
  return { start_date: toLocalDateString(start), end_date: toLocalDateString(end) };
});

// Summary computations
const totalSpend = computed(() => summaryData.value.reduce((s, d) => s + d.total_cost_usd, 0));
const totalExecutions = computed(() => summaryData.value.reduce((s, d) => s + d.execution_count, 0));
const totalSessions = computed(() => summaryData.value.reduce((s, d) => s + (d.session_count || 0), 0));
const totalTurns = computed(() => summaryData.value.reduce((s, d) => s + (d.total_turns || 0), 0));
const totalInputTokens = computed(() => summaryData.value.reduce((s, d) => s + (d.total_input_tokens || 0), 0));
const totalOutputTokens = computed(() => summaryData.value.reduce((s, d) => s + (d.total_output_tokens || 0), 0));
const totalCacheReadTokens = computed(() => summaryData.value.reduce((s, d) => s + (d.total_cache_read_tokens || 0), 0));
const totalCacheCreationTokens = computed(() => summaryData.value.reduce((s, d) => s + (d.total_cache_creation_tokens || 0), 0));
const totalAllTokens = computed(() => totalInputTokens.value + totalOutputTokens.value + totalCacheReadTokens.value + totalCacheCreationTokens.value);
const cacheHitRate = computed(() => {
  const total = totalInputTokens.value + totalCacheReadTokens.value + totalCacheCreationTokens.value;
  return total === 0 ? 0 : Math.round((totalCacheReadTokens.value / total) * 100);
});

const periodLabel = computed(() => {
  const labels: Record<string, string> = { '7d': 'Last 7 Days', '30d': 'Last 30 Days', month: 'This Month' };
  return labels[selectedPeriod.value] || `${dateRange.value.start_date} \u2013 ${dateRange.value.end_date}`;
});

const monitoringHistoryMinutes = computed(() => {
  if (selectedPeriod.value === '7d') return 10080;
  if (selectedPeriod.value === '30d') return 43200;
  if (selectedPeriod.value === 'month') {
    const now = new Date();
    return Math.ceil((now.getTime() - new Date(now.getFullYear(), now.getMonth(), 1).getTime()) / 60000);
  }
  const start = customStartDate.value ? new Date(customStartDate.value) : new Date(Date.now() - 7 * 86400000);
  const end = customEndDate.value ? new Date(customEndDate.value) : new Date();
  return Math.ceil((end.getTime() - start.getTime()) / 60000);
});

const chartTimeRangeStart = computed(() => {
  const now = new Date();
  if (selectedPeriod.value === '7d') return new Date(now.getTime() - 7 * 86400000).toISOString();
  if (selectedPeriod.value === '30d') return new Date(now.getTime() - 30 * 86400000).toISOString();
  if (selectedPeriod.value === 'month') return new Date(now.getFullYear(), now.getMonth(), 1).toISOString();
  return customStartDate.value ? new Date(customStartDate.value).toISOString() : new Date(now.getTime() - 7 * 86400000).toISOString();
});

const chartTimeRangeEnd = computed(() => {
  return (selectedPeriod.value === 'custom' && customEndDate.value) ? new Date(customEndDate.value).toISOString() : new Date().toISOString();
});

function getTrendKey(accountId: number, windowType: string) { return `${accountId}_${windowType}`; }

const highUsageWindows = computed(() => {
  if (!monitoringStatus.value?.windows) return [];
  return monitoringStatus.value.windows.filter(
    w => w.threshold_level === 'warning' || w.threshold_level === 'critical'
  );
});

function checkAndNotifyThresholds() {
  if (!monitoringStatus.value?.windows) return;
  const levels = ['normal', 'info', 'warning', 'critical'];
  for (const w of monitoringStatus.value.windows) {
    const key = getTrendKey(w.account_id, w.window_type);
    const prev = levels.indexOf(previousThresholdState.value[key] || 'normal');
    const curr = levels.indexOf(w.threshold_level || 'normal');
    if (curr > prev) {
      if (w.threshold_level === 'critical') showToast(`Rate limit CRITICAL: ${w.account_name} at ${Math.round(w.percentage)}% (${w.window_type})`, 'error');
      else if (w.threshold_level === 'warning') showToast(`Rate limit warning: ${w.account_name} at ${Math.round(w.percentage)}% (${w.window_type})`, 'info');
    }
    previousThresholdState.value[key] = w.threshold_level || 'normal';
  }
}

async function loadTrendHistories(windows: MonitoringStatus['windows']) {
  const results: Record<string, SnapshotHistory> = {};
  await Promise.all(windows.map(async (w) => {
    const key = getTrendKey(w.account_id, w.window_type);
    try { results[key] = await monitoringApi.getHistory(w.account_id, w.window_type, monitoringHistoryMinutes.value); }
    catch { /* skip */ }
  }));
  // Batch update to avoid N reactive notifications causing chart re-renders
  trendHistories.value = { ...trendHistories.value, ...results };
}

async function loadMonitoringStatus() {
  if (monitoringStatus.value?.windows?.length) monitoringRefreshing.value = true;
  monitoringLoading.value = true;
  try {
    const status = await monitoringApi.getStatus();
    monitoringStatus.value = status;
    checkAndNotifyThresholds();
    await Promise.all([collectSessionUsage(), loadSessionStats(), loadAllTimeSpend(), status.windows ? loadTrendHistories(status.windows) : Promise.resolve()]);
  } catch { monitoringStatus.value = null; }
  finally { monitoringLoading.value = false; monitoringRefreshing.value = false; }
}

async function pollNow() {
  pollNowLoading.value = true;
  try {
    const status = await monitoringApi.pollNow();
    monitoringStatus.value = status;
    checkAndNotifyThresholds();
    if (status.windows) await loadTrendHistories(status.windows);
    showToast('Monitoring data refreshed', 'success');
  } catch { showToast('Failed to poll monitoring data', 'error'); }
  finally { pollNowLoading.value = false; }
}

function startMonitoringPolling() {
  stopMonitoringPolling();
  if (monitoringStatus.value?.enabled && monitoringStatus.value?.polling_minutes) {
    pollingInterval.value = setInterval(loadMonitoringStatus, monitoringStatus.value.polling_minutes * 60000);
  }
}
function stopMonitoringPolling() { if (pollingInterval.value) { clearInterval(pollingInterval.value); pollingInterval.value = null; } }

async function loadData() {
  isLoading.value = true;
  try {
    const { start_date, end_date } = dateRange.value;
    const [summaryRes, entityRes, limitsRes] = await Promise.all([
      budgetApi.getUsageSummary({ group_by: 'day', start_date, end_date }),
      budgetApi.getUsageByEntity({ entity_type: activeEntityTab.value, start_date, end_date }),
      budgetApi.getLimits(),
    ]);
    summaryData.value = summaryRes.summary || []; entityData.value = entityRes.entities || [];
    budgetLimits.value = limitsRes.limits || [];
  } catch (err) {
    showToast('Failed to load usage data', 'error');
    summaryData.value = []; entityData.value = []; budgetLimits.value = [];
  } finally { isLoading.value = false; }
}

async function loadEntityData() {
  try {
    const { start_date, end_date } = dateRange.value;
    entityData.value = (await budgetApi.getUsageByEntity({ entity_type: activeEntityTab.value, start_date, end_date })).entities || [];
  } catch (err) { showToast('Failed to load entity data', 'error'); entityData.value = []; }
}

async function loadAgentsTeamsAndTriggers() {
  try {
    const [a, t, tr] = await Promise.all([agentApi.list(), teamApi.list(), triggerApi.list()]);
    agents.value = (a.agents || []).map(x => ({ id: x.id, name: x.name }));
    teams.value = (t.teams || []).map(x => ({ id: x.id, name: x.name }));
    triggers.value = (tr.triggers || []).map(x => ({ id: x.id, name: x.name }));
  } catch { /* ignore */ }
}

async function collectSessionUsage() {
  sessionCollecting.value = true;
  try { await budgetApi.collectSessions(); await loadData(); }
  catch { /* ignore */ } finally { sessionCollecting.value = false; }
}

async function loadSessionStats() {
  try { sessionStats.value = (await budgetApi.getSessionStats()).stats || null; } catch { /* ignore */ }
}

async function loadAllTimeSpend() {
  try { allTimeSpend.value = (await budgetApi.getAllTimeSpend()).total_cost_usd; } catch { /* ignore */ }
}

function openAddLimit() { budgetFormMode.value = 'create'; selectedLimit.value = null; showBudgetForm.value = true; }
function openEditLimit(limit: BudgetLimit) { budgetFormMode.value = 'edit'; selectedLimit.value = limit; showBudgetForm.value = true; }
async function handleDeleteLimit(limit: BudgetLimit) {
  try { await budgetApi.deleteLimit(limit.entity_type, limit.entity_id); showToast('Budget limit deleted', 'success'); await loadData(); }
  catch { showToast('Failed to delete budget limit', 'error'); }
}
function handleBudgetSaved() { showBudgetForm.value = false; showToast('Budget limit saved', 'success'); loadData(); }
function handleBudgetCancelled() { showBudgetForm.value = false; }

function getDefaultProjectionWindow(accountId: number): string | null {
  const windows = monitoringStatus.value?.windows?.filter(w => w.account_id === accountId && w.window_type !== 'no_data') || [];
  if (!windows.length) return null;
  // Gemini: prefer best model (gemini-3-pro > gemini-3-flash > gemini-2.5-pro)
  const geminiPriority = ['gemini-3-pro', 'gemini-3-flash', 'gemini-2.5-pro'];
  for (const prefix of geminiPriority) {
    const match = windows.find(w => w.window_type.includes(prefix));
    if (match) return match.window_type;
  }
  // Codex: prefer base model primary window (shortest name with _primary_window)
  const primaryWindows = windows.filter(w => w.window_type.endsWith('_primary_window'));
  if (primaryWindows.length > 0) {
    primaryWindows.sort((a, b) => a.window_type.length - b.window_type.length);
    return primaryWindows[0].window_type;
  }
  // Claude: prefer five_hour (Opus 5 Hour)
  const fiveHour = windows.find(w => w.window_type === 'five_hour');
  if (fiveHour) return fiveHour.window_type;
  return windows[0].window_type;
}

function toggleCard(accountId: number) {
  if (expandedCards.value.has(accountId)) {
    expandedCards.value.delete(accountId);
  } else {
    expandedCards.value.add(accountId);
    if (!selectedProjectionWindow.value[accountId]) {
      const defaultWin = getDefaultProjectionWindow(accountId);
      if (defaultWin) selectedProjectionWindow.value[accountId] = defaultWin;
    }
    // Load trend histories for this account's windows when expanding
    const accountWindows = monitoringStatus.value?.windows?.filter(w => w.account_id === accountId);
    if (accountWindows?.length) loadTrendHistories(accountWindows);
  }
}

watch(selectedPeriod, () => { Promise.all([loadData(), loadMonitoringStatus()]); });
watch([customStartDate, customEndDate], () => { if (selectedPeriod.value === 'custom' && !customDateError.value) Promise.all([loadData(), loadMonitoringStatus()]); });
watch(activeEntityTab, loadEntityData);
watch(() => monitoringStatus.value?.polling_minutes, () => startMonitoringPolling());

onMounted(async () => {
  await Promise.all([collectSessionUsage(), pollNow(), loadSessionStats(), loadAllTimeSpend(), loadAgentsTeamsAndTriggers(), fetchRotationStatus()]);
  startMonitoringPolling();
  startRotationPolling();
});
onUnmounted(() => {
  stopMonitoringPolling();
  stopRotationPolling();
});
</script>

<template>
  <div class="token-usage-dashboard">
    <AppBreadcrumb :items="[{ label: 'Dashboards', action: () => router.push({ name: 'dashboards' }) }, { label: 'Token Usage' }]" />
    <PageHeader title="Token Usage" subtitle="Monitor AI spending across agents and teams">
      <template #actions>
        <div class="period-selector">
          <button v-for="option in periodOptions" :key="option.key" class="period-btn" :class="{ active: selectedPeriod === option.key }" @click="selectedPeriod = option.key">{{ option.label }}</button>
        </div>
      </template>
    </PageHeader>
    <div v-if="selectedPeriod === 'custom'" class="custom-range">
      <div class="date-input-group"><label>Start Date</label><input type="date" v-model="customStartDate"></div>
      <div class="date-input-group"><label>End Date</label><input type="date" v-model="customEndDate"></div>
    </div>
    <div v-if="customDateError" class="date-error">{{ customDateError }}</div>
    <div v-if="selectedPeriod !== 'custom'" class="period-range-display">{{ dateRange.start_date }} &mdash; {{ dateRange.end_date }}</div>
    <!-- Rate limit proximity warnings -->
    <div v-if="highUsageWindows.length > 0" class="rate-limit-alerts">
      <div
        v-for="w in highUsageWindows"
        :key="`${w.account_id}_${w.window_type}`"
        class="rate-limit-alert"
        :class="w.threshold_level"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
          <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        <span>
          <strong>{{ w.threshold_level === 'critical' ? 'Critical' : 'Warning' }}:</strong>
          {{ w.account_name || 'Account ' + w.account_id }} is at {{ Math.round(w.percentage) }}% of {{ w.window_type }} rate limit.
          <template v-if="w.eta?.status === 'projected'"> Limit reached in {{ w.eta.message }}.</template>
        </span>
      </div>
    </div>

    <LoadingState v-if="sessionCollecting" message="Scanning local CLI sessions..." />
    <LoadingState v-else-if="isLoading" message="Loading usage data..." />

    <TokenBreakdownCard v-show="!isLoading" :total-input-tokens="totalInputTokens" :total-output-tokens="totalOutputTokens" :total-cache-read-tokens="totalCacheReadTokens" :total-cache-creation-tokens="totalCacheCreationTokens" :total-all-tokens="totalAllTokens" :cache-hit-rate="cacheHitRate" :period-label="periodLabel" :total-spend="totalSpend" :total-sessions="totalSessions" :total-turns="totalTurns" :total-executions="totalExecutions" :session-stats="sessionStats" :all-time-spend="allTimeSpend" />
    <MonitoringSection v-show="!isLoading" :monitoring-status="monitoringStatus" :monitoring-loading="monitoringLoading" :poll-now-loading="pollNowLoading" :monitoring-refreshing="monitoringRefreshing" :trend-histories="trendHistories" :expanded-cards="expandedCards" :selected-rate-windows="selectedRateWindows" :selected-projection-window="selectedProjectionWindow" :chart-time-range-start="chartTimeRangeStart" :chart-time-range-end="chartTimeRangeEnd" :rotation-sessions="rotationStatus?.sessions ?? []" :rotation-evaluator="rotationStatus?.evaluator ?? undefined" @poll-now="pollNow" @toggle-card="toggleCard" @update:selected-rate-windows="Object.assign(selectedRateWindows, $event)" @update:selected-projection-window="Object.assign(selectedProjectionWindow, $event)" />

    <!-- Cost Trend Chart -->
    <div class="section" v-show="!isLoading">
      <div class="section-header">
        <h2 class="section-title">Cost Trend</h2>
        <div class="chart-type-toggle">
          <button class="toggle-btn" :class="{ active: chartType === 'bar' }" @click="chartType = 'bar'" title="Bar Chart">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="12" width="4" height="9" rx="1"/><rect x="10" y="6" width="4" height="15" rx="1"/><rect x="17" y="3" width="4" height="18" rx="1"/></svg>
          </button>
          <button class="toggle-btn" :class="{ active: chartType === 'line' }" @click="chartType = 'line'" title="Line Chart">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="22 12 18 8 13 13 9 9 2 16"/><polyline points="16 8 22 8 22 14"/></svg>
          </button>
        </div>
      </div>
      <div class="chart-wrapper">
        <TokenUsageChart :data="summaryData" :chart-type="chartType" title="Daily Cost" />
        <div v-if="summaryData.length === 0" class="empty-chart-overlay"><p>No usage data for the selected period</p></div>
      </div>
    </div>

    <EntitySpendSection v-show="!isLoading" :entity-data="entityData" :active-entity-tab="activeEntityTab" @update:active-entity-tab="activeEntityTab = $event" />
    <div class="opencode-note" v-show="!isLoading"><span class="note-icon">i</span><span>OpenCode backend executions do not report token usage. Only Claude backend usage is tracked.</span></div>
    <BudgetLimitsSection v-show="!isLoading" :budget-limits="budgetLimits" :agents="agents" :teams="teams" :triggers="triggers" @open-add-limit="openAddLimit" @open-edit-limit="openEditLimit" @delete-limit="handleDeleteLimit" />

    <BudgetLimitForm v-if="showBudgetForm" :mode="budgetFormMode" :existing-limit="selectedLimit" :agents="agents" :teams="teams" :triggers="triggers" @saved="handleBudgetSaved" @cancelled="handleBudgetCancelled" />
  </div>
</template>

<style scoped>
.token-usage-dashboard { display: flex; flex-direction: column; gap: 24px; width: 100%; animation: fadeIn 0.4s ease; }
.rate-limit-alerts { display: flex; flex-direction: column; gap: 8px; }
.rate-limit-alert { display: flex; align-items: flex-start; gap: 10px; padding: 10px 14px; border-radius: 8px; font-size: 0.875rem; line-height: 1.4; }
.rate-limit-alert.warning { background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); color: #f59e0b; }
.rate-limit-alert.critical { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.35); color: #ef4444; }
.rate-limit-alert svg { flex-shrink: 0; margin-top: 2px; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
.period-selector { display: flex; gap: 4px; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 4px; }
.period-btn { padding: 8px 14px; border: none; border-radius: 6px; background: transparent; color: var(--text-tertiary); font-size: 0.8rem; font-weight: 500; cursor: pointer; transition: all var(--transition-fast); white-space: nowrap; }
.period-btn:hover { color: var(--text-primary); background: var(--bg-tertiary); }
.period-btn.active { color: var(--accent-cyan); background: var(--accent-cyan-dim); }
.custom-range { display: flex; gap: 16px; margin-bottom: 20px; padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 8px; }
.date-input-group label { display: block; font-size: 0.75rem; color: var(--text-tertiary); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.05em; }
.date-input-group input { padding: 8px 12px; border: 1px solid var(--border-default); border-radius: 6px; background: var(--bg-primary); color: var(--text-primary); font-size: 0.85rem; }
.date-input-group input:focus { border-color: var(--accent-cyan); outline: none; box-shadow: 0 0 0 3px var(--accent-cyan-dim); }
.period-range-display { font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-muted); text-align: right; margin-top: -20px; margin-bottom: 8px; }
.section { background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 12px; padding: 24px; margin-bottom: 20px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.section-title { font-family: var(--font-mono); font-size: 1rem; font-weight: 600; color: var(--text-primary); }
.chart-type-toggle { display: flex; gap: 4px; }
.toggle-btn { width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--border-subtle); border-radius: 6px; background: transparent; color: var(--text-tertiary); cursor: pointer; transition: all var(--transition-fast); }
.toggle-btn:hover { color: var(--text-primary); border-color: var(--border-default); }
.toggle-btn.active { color: var(--accent-cyan); background: var(--accent-cyan-dim); border-color: transparent; }
.toggle-btn svg { width: 16px; height: 16px; }
.chart-wrapper { position: relative; }
.empty-chart-overlay { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: var(--text-muted); font-size: 0.9rem; }
.opencode-note { display: flex; align-items: center; gap: 10px; padding: 12px 16px; margin-bottom: 20px; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-left: 3px solid var(--accent-cyan); border-radius: 8px; font-size: 0.8rem; color: var(--text-tertiary); line-height: 1.4; }
.note-icon { display: flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 50%; background: var(--accent-cyan-dim); color: var(--accent-cyan); font-size: 0.7rem; font-weight: 700; flex-shrink: 0; }
.date-error { color: #ef4444; font-size: 0.8rem; margin-top: -12px; margin-bottom: 16px; padding: 0 4px; }
@media (max-width: 900px) { .dashboard-header { flex-direction: column; } }
</style>
