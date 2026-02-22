<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue';
import type { MonitoringStatus, SnapshotHistory, ConsumptionRates, RotationSession, RotationEvaluatorStatus, EtaProjection } from '../../services/api';
import { useTokenFormatting } from '../../composables/useTokenFormatting';
import RateLimitGauge from './RateLimitGauge.vue';
import CombinedUsageChart from './CombinedUsageChart.vue';
import RemainingTimeChart from './RemainingTimeChart.vue';

const { parseWindowType } = useTokenFormatting();

const props = defineProps<{
  monitoringStatus: MonitoringStatus | null;
  monitoringLoading: boolean;
  pollNowLoading: boolean;
  monitoringRefreshing: boolean;
  trendHistories: Record<string, SnapshotHistory>;
  expandedCards: Set<number>;
  selectedRateWindows: Record<number, '24h' | '48h' | '72h' | '96h' | '120h'>;
  selectedProjectionWindow: Record<number, string>;
  chartTimeRangeStart: string;
  chartTimeRangeEnd: string;
  rotationSessions?: RotationSession[];
  rotationEvaluator?: RotationEvaluatorStatus;
}>();

const emit = defineEmits<{
  (e: 'poll-now'): void;
  (e: 'toggle-card', accountId: number): void;
  (e: 'update:selectedRateWindows', value: Record<number, '24h' | '48h' | '72h' | '96h' | '120h'>): void;
  (e: 'update:selectedProjectionWindow', value: Record<number, string>): void;
}>();

// Window type display labels
const windowTypeLabels: Record<string, string> = {
  five_hour: 'Opus 5 Hour',
  seven_day: 'Opus 7 Day',
  seven_day_sonnet: 'Sonnet 7 Day',
  primary_window: 'Codex 5 Hour',
  secondary_window: 'Codex 7 Day',
  '5h_sliding': 'Opus 5 Hour',
  weekly: 'Opus 7 Day',
  rpd: 'RPD',
  tpm_60s: 'TPM (60s)',
};

type RateWindow = '24h' | '48h' | '72h' | '96h' | '120h';

const rateWindowLabels: Record<RateWindow, string> = {
  '24h': '24h',
  '48h': '48h',
  '72h': '72h',
  '96h': '96h',
  '120h': '120h',
};

const legacyWindowTypes = new Set(['5h_sliding', 'weekly', 'rpd', 'tpm_60s']);
const providerWindowTypes = new Set(['five_hour', 'seven_day', 'seven_day_sonnet']);
const backendTypeOrder: Record<string, number> = { claude: 0, codex: 1, gemini: 2, opencode: 3 };

function geminiModelOrder(windowType: string): number {
  if (windowType.includes('gemini-3-pro')) return 0;
  if (windowType.includes('gemini-3-flash')) return 1;
  if (windowType.includes('gemini-2.5-pro')) return 2;
  if (windowType.includes('gemini-2.5')) return 3;
  if (windowType.includes('gemini-2')) return 4;
  return 5;
}

function sortWindows(windows: MonitoringStatus['windows'], backendType: string): MonitoringStatus['windows'] {
  return [...windows].sort((a, b) => {
    if (backendType === 'gemini') {
      return geminiModelOrder(a.window_type) - geminiModelOrder(b.window_type);
    }
    return a.window_type.localeCompare(b.window_type);
  });
}

const gaugeAccentPalette = [
  '#8855ff', '#00d4ff', '#f59e0b', '#e879f9', '#10b981', '#3b82f6',
];

function getGaugeAccentColor(backendType: string, _windowType: string, index: number): string {
  if (backendType === 'claude') return '';
  return gaugeAccentPalette[index % gaugeAccentPalette.length];
}

function getGaugeLabel(windowType: string): string {
  const { model, window: win } = parseWindowType(windowType);
  const parts: string[] = [];
  if (model) parts.push(`<span class="gauge-model">${model}</span>`);
  if (win) parts.push(`<span class="gauge-window">${win}</span>`);
  return parts.join('') || windowType;
}

function getWindowLabel(windowType: string): string {
  if (windowTypeLabels[windowType]) return windowTypeLabels[windowType];
  const { model, window: win } = parseWindowType(windowType);
  return [model, win].filter(Boolean).join(' ') || windowType;
}

function getTrendKey(accountId: number, windowType: string): string {
  return `${accountId}_${windowType}`;
}

function getCardRateWindow(accountId: number): RateWindow {
  return props.selectedRateWindows[accountId] || '24h';
}

function getRateWindowMinutes(accountId: number): number {
  const rw = getCardRateWindow(accountId);
  switch (rw) {
    case '24h': return 1440;
    case '48h': return 2880;
    case '72h': return 4320;
    case '96h': return 5760;
    case '120h': return 7200;
    default: return 1440;
  }
}

function formatRate(rates: ConsumptionRates | undefined, accountId: number): string {
  if (!rates) return '--';
  const rw = getCardRateWindow(accountId);
  const val = rates[rw];
  if (val == null) return '--';
  const unit = rates.unit;
  if (unit === '%/hr') {
    return `${val.toFixed(1)}%/hr`;
  }
  if (val >= 1000) return `${(val / 1000).toFixed(1)}k tok/hr`;
  return `${Math.round(val)} tok/hr`;
}

function isRateAvailable(rates: ConsumptionRates | undefined, accountId: number): boolean {
  if (!rates) return false;
  const rw = getCardRateWindow(accountId);
  return rates[rw] != null;
}

function formatRelativeReset(resetsAt: string): string {
  const resetTime = new Date(resetsAt).getTime();
  const now = Date.now();
  const diffMs = resetTime - now;
  if (diffMs <= 0) return 'now';
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 60) return `${diffMin}m`;
  const days = Math.floor(diffMin / 1440);
  const hours = Math.floor((diffMin % 1440) / 60);
  const mins = diffMin % 60;
  if (days > 0) {
    return hours > 0 ? `${days}d ${hours}h` : `${days}d`;
  }
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
}

function getResetUrgency(resetsAt: string): 'soon' | 'normal' {
  const resetTime = new Date(resetsAt).getTime();
  const diffMin = (resetTime - Date.now()) / 60000;
  return diffMin <= 30 ? 'soon' : 'normal';
}

// Session indicator helper
function getSessionForAccount(accountId: number): RotationSession | undefined {
  return props.rotationSessions?.find(s => s.account_id !== null && s.account_id === accountId);
}

// Countdown timer state
const countdownInterval = ref<ReturnType<typeof setInterval> | null>(null);
const countdownTexts = ref<Record<string, string>>({});

function updateCountdowns() {
  if (!props.monitoringStatus?.windows?.length) return;
  for (const w of props.monitoringStatus.windows) {
    if (!w.resets_at) continue;
    const key = `${w.account_id}-${w.window_type}`;
    const diffMs = new Date(w.resets_at).getTime() - Date.now();
    let text: string;
    if (diffMs <= 0) {
      text = 'Resetting...';
    } else {
      const totalMin = Math.floor(diffMs / 60000);
      const d = Math.floor(totalMin / 1440);
      const h = Math.floor((totalMin % 1440) / 60);
      const m = totalMin % 60;
      if (h === 0 && m < 5) {
        const totalSec = Math.floor(diffMs / 1000);
        const dispMin = Math.floor(totalSec / 60);
        const dispSec = totalSec % 60;
        text = `${dispMin}m ${dispSec}s`;
      } else if (d > 0) text = h > 0 ? `${d}d ${h}h ${m}m` : `${d}d ${m}m`;
      else if (h > 0) text = m > 0 ? `${h}h ${m}m` : `${h}h`;
      else text = `${m}m`;
    }
    // Only update if changed to avoid unnecessary reactive notifications
    if (countdownTexts.value[key] !== text) {
      countdownTexts.value[key] = text;
    }
  }
}

function startCountdowns() {
  if (countdownInterval.value) clearInterval(countdownInterval.value);
  updateCountdowns();
  countdownInterval.value = setInterval(updateCountdowns, 10000);
}

onMounted(() => {
  if (props.monitoringStatus?.windows?.length) startCountdowns();
});

watch(() => props.monitoringStatus, () => {
  startCountdowns();
}, { deep: true });

onUnmounted(() => {
  if (countdownInterval.value) {
    clearInterval(countdownInterval.value);
    countdownInterval.value = null;
  }
});

// Depletion helpers
function formatDepletion(eta: EtaProjection): string {
  if (!eta || eta.minutes_remaining == null) return 'Unknown';
  const totalMin = Math.floor(eta.minutes_remaining);
  if (totalMin <= 0) return 'Now';
  const d = Math.floor(totalMin / 1440);
  const h = Math.floor((totalMin % 1440) / 60);
  const m = totalMin % 60;
  if (d > 0) return h > 0 ? `${d}d ${h}h` : `${d}d`;
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`;
  return `${m}m`;
}

function depletionUrgencyClass(eta: EtaProjection): string {
  if (!eta) return 'unknown';
  return eta.status || 'unknown';
}

function getCountdownText(accountId: number, windowType: string): string | undefined {
  return countdownTexts.value[`${accountId}-${windowType}`];
}

// rateWindowMinutes is now per-card via getRateWindowMinutes(accountId)

function getDataBounds(card: { account_id: number; windows: MonitoringStatus['windows'] }): { earliest: number; latest: number } {
  let earliest = Infinity;
  let latest = 0;
  for (const w of card.windows) {
    const key = getTrendKey(card.account_id, w.window_type);
    const history = props.trendHistories[key]?.history || [];
    for (const h of history) {
      const t = new Date(h.recorded_at).getTime();
      if (t < earliest) earliest = t;
      if (t > latest) latest = t;
    }
  }
  return { earliest: earliest === Infinity ? 0 : earliest, latest };
}

function getEffectiveChartStart(card: { account_id: number; windows: MonitoringStatus['windows'] }): string {
  const { earliest, latest } = getDataBounds(card);
  if (latest <= 0) return props.chartTimeRangeStart;

  const rwMinutes = getRateWindowMinutes(card.account_id);
  const windowStart = latest - rwMinutes * 60000;
  // If data starts after the window start, tighten to data with small padding
  if (earliest > windowStart) {
    const span = latest - earliest;
    return new Date(earliest - span * 0.03).toISOString();
  }
  return new Date(windowStart).toISOString();
}

function getEffectiveChartEnd(card: { account_id: number; windows: MonitoringStatus['windows'] }): string {
  const { latest } = getDataBounds(card);
  if (latest <= 0) return props.chartTimeRangeEnd;
  const { earliest } = getDataBounds(card);
  const rwMinutes = getRateWindowMinutes(card.account_id);
  const dataSpan = latest - (earliest > 0 ? earliest : latest);
  let pad = Math.max(dataSpan * 0.03, rwMinutes * 60000 * 0.02);
  // When any window has a rate, ensure enough room for the 2-hour projection line
  const hasAnyRate = card.windows.some(w => toRatePctPerHour(w, card.account_id) != null);
  if (hasAnyRate) {
    const projectionMs = 2 * 3600000;
    pad = Math.max(pad, projectionMs * 1.05);
  }
  return new Date(latest + pad).toISOString();
}

const monitoringAccountCards = computed(() => {
  if (!props.monitoringStatus?.windows?.length) return [];
  const grouped: Record<number, { account_name: string; plan: string; backend_type: string; windows: MonitoringStatus['windows'] }> = {};
  for (const w of props.monitoringStatus.windows) {
    if (!grouped[w.account_id]) {
      grouped[w.account_id] = { account_name: w.account_name, plan: w.plan || '', backend_type: w.backend_type, windows: [] };
    }
    grouped[w.account_id].windows.push(w);
  }
  const cards = Object.entries(grouped).map(([id, data]) => {
    const hasProvider = data.windows.some(w => providerWindowTypes.has(w.window_type) || w.window_type.endsWith('_window'));
    const filtered = hasProvider
      ? data.windows.filter(w => !legacyWindowTypes.has(w.window_type))
      : data.windows;
    return { account_id: Number(id), account_name: data.account_name, plan: data.plan, backend_type: data.backend_type, windows: sortWindows(filtered, data.backend_type) };
  }).sort((a, b) => {
    const typeA = backendTypeOrder[a.backend_type] ?? 99;
    const typeB = backendTypeOrder[b.backend_type] ?? 99;
    if (typeA !== typeB) return typeA - typeB;
    return a.account_name.localeCompare(b.account_name);
  });
  return cards;
});

const monitoringCardsByBackend = computed(() => {
  const groups: { backend_type: string; label: string; cards: typeof monitoringAccountCards.value }[] = [];
  const backendLabels: Record<string, string> = { claude: 'Claude', codex: 'Codex', gemini: 'Gemini', opencode: 'OpenCode' };
  let currentType = '';
  let currentGroup: typeof monitoringAccountCards.value = [];
  for (const card of monitoringAccountCards.value) {
    if (card.backend_type !== currentType) {
      if (currentGroup.length > 0) {
        groups.push({ backend_type: currentType, label: backendLabels[currentType] || currentType, cards: currentGroup });
      }
      currentType = card.backend_type;
      currentGroup = [];
    }
    currentGroup.push(card);
  }
  if (currentGroup.length > 0) {
    groups.push({ backend_type: currentType, label: backendLabels[currentType] || currentType, cards: currentGroup });
  }
  return groups;
});

// Convert a raw consumption rate to %/hr regardless of unit
function toRatePctPerHour(w: any, accountId?: number): number | undefined {
  const rates = w.consumption_rates;
  const rw = accountId != null ? getCardRateWindow(accountId) : '24h';
  const raw = rates?.[rw];
  if (raw == null) return undefined;
  // If unit is tok/hr, convert to %/hr using tokens_limit
  if (rates?.unit === 'tok/hr' && w.tokens_limit > 0) {
    return (raw / w.tokens_limit) * 100;
  }
  return raw; // already %/hr
}

// Pre-compute chart data to avoid creating new objects on every template render
const combinedHistoriesCache = computed(() => {
  const result: Record<number, { windowType: string; label: string; history: any[]; color?: string; ratePerHour?: number; resetsAt?: string | null }[]> = {};
  for (const card of monitoringAccountCards.value) {
    result[card.account_id] = card.windows
      .map((w: any, idx: number) => {
        const key = getTrendKey(card.account_id, w.window_type);
        const history = props.trendHistories[key]?.history || [];
        return {
          windowType: w.window_type,
          label: getWindowLabel(w.window_type),
          history,
          color: getGaugeAccentColor(card.backend_type, w.window_type, idx) || undefined,
          ratePerHour: toRatePctPerHour(w, card.account_id),
          resetsAt: w.resets_at || null,
        };
      })
      .filter((wh: any) => wh.history.length >= 2);
  }
  return result;
});

const projectionHistoryCache = computed(() => {
  const result: Record<number, any[]> = {};
  for (const card of monitoringAccountCards.value) {
    const windowType = props.selectedProjectionWindow[card.account_id];
    if (!windowType) { result[card.account_id] = []; continue; }
    const key = getTrendKey(card.account_id, windowType);
    result[card.account_id] = props.trendHistories[key]?.history || [];
  }
  return result;
});

function getProjectionWindows(card: { windows: MonitoringStatus['windows'] }) {
  return card.windows.map(w => ({
    windowType: w.window_type,
    label: getWindowLabel(w.window_type),
  }));
}

function getProjectionResetAt(accountId: number): string | null {
  const windowType = props.selectedProjectionWindow[accountId];
  if (!windowType) return null;
  const card = monitoringAccountCards.value.find(c => c.account_id === accountId);
  const w = card?.windows.find((win: any) => win.window_type === windowType);
  return w?.resets_at || null;
}

function getProjectionRatePerHour(accountId: number): number | undefined {
  const windowType = props.selectedProjectionWindow[accountId];
  if (!windowType) return undefined;
  const card = monitoringAccountCards.value.find(c => c.account_id === accountId);
  const w = card?.windows.find((win: any) => win.window_type === windowType);
  if (!w) return undefined;
  return toRatePctPerHour(w, accountId);
}

function handleProjectionWindowChange(accountId: number, windowType: string) {
  const updated = { ...props.selectedProjectionWindow, [accountId]: windowType };
  emit('update:selectedProjectionWindow', updated);
}
</script>

<template>
  <div class="section">
    <div class="section-header">
      <h2 class="section-title">
        Rate Limit Monitoring
        <span v-if="monitoringRefreshing || pollNowLoading" class="inline-refresh-spinner"></span>
      </h2>
      <div class="monitoring-header-actions">
        <span
          v-if="monitoringStatus"
          class="monitoring-status-badge"
          :class="{ active: monitoringStatus.enabled }"
        >
          {{ monitoringStatus.enabled ? 'Active' : 'Disabled' }}
        </span>
        <button
          v-if="monitoringStatus?.enabled"
          class="check-now-btn"
          :disabled="pollNowLoading"
          @click="emit('poll-now')"
        >
          <svg v-if="!pollNowLoading" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
          <div v-else class="btn-spinner"></div>
          {{ pollNowLoading ? 'Checking...' : 'Check Now' }}
        </button>
      </div>
    </div>

    <!-- Initial loading (no status yet) -->
    <div v-if="!monitoringStatus && (monitoringLoading || pollNowLoading)" class="monitoring-loading-full">
      <div class="loading-spinner-large"></div>
      <span>Loading rate limit data...</span>
    </div>

    <!-- Monitoring disabled -->
    <div v-else-if="!monitoringStatus || !monitoringStatus.enabled" class="monitoring-disabled">
      <span class="monitoring-mode-tag manual">MANUAL CHECK</span>
      <p>Enable monitoring in Settings to see live rate limit gauges and projections.</p>
    </div>

    <!-- Monitoring enabled but loading first data -->
    <div v-else-if="monitoringLoading && !monitoringStatus.windows?.length" class="monitoring-loading-full">
      <div class="loading-spinner-large"></div>
      <span>Polling rate limits...</span>
    </div>

    <!-- Monitoring enabled with no data -->
    <div v-else-if="!monitoringStatus.windows?.length" class="monitoring-collecting">
      <span class="monitoring-mode-tag active">MONITORING</span>
      <span>Gauges will appear after the first polling cycle.</span>
    </div>

    <!-- Monitoring enabled with data -->
    <div v-else class="monitoring-backend-groups">
      <div v-for="group in monitoringCardsByBackend" :key="group.backend_type" class="backend-group">
        <div class="backend-group-header">
          <div class="backend-group-icon" :class="group.backend_type">
            <svg v-if="group.backend_type === 'claude'" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z"/>
            </svg>
            <svg v-else-if="group.backend_type === 'codex'" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2l9.196 5.308v10.616L12 23.232l-9.196-5.308V7.308z"/>
            </svg>
            <svg v-else-if="group.backend_type === 'gemini'" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2l3.09 6.26L22 12l-6.91 3.74L12 22l-3.09-6.26L2 12l6.91-3.74z"/>
            </svg>
            <svg v-else-if="group.backend_type === 'opencode'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="16 18 22 12 16 6"/>
              <polyline points="8 6 2 12 8 18"/>
            </svg>
          </div>
          <span class="backend-group-label">{{ group.label }}</span>
        </div>
        <div class="monitoring-accounts-grid">
          <div
            v-for="card in group.cards"
            :key="card.account_id"
            class="monitoring-account-card"
            :class="{ expanded: expandedCards.has(card.account_id) }"
            @click="emit('toggle-card', card.account_id)"
          >
            <div class="account-card-header">
              <div class="account-card-icon" :class="card.backend_type">
                <svg v-if="card.backend_type === 'claude'" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z"/>
                </svg>
                <svg v-else-if="card.backend_type === 'codex'" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2l9.196 5.308v10.616L12 23.232l-9.196-5.308V7.308z"/>
                </svg>
                <svg v-else-if="card.backend_type === 'gemini'" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2l3.09 6.26L22 12l-6.91 3.74L12 22l-3.09-6.26L2 12l6.91-3.74z"/>
                </svg>
                <svg v-else-if="card.backend_type === 'opencode'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="16 18 22 12 16 6"/>
                  <polyline points="8 6 2 12 8 18"/>
                </svg>
              </div>
              <span class="account-card-name">{{ card.account_name }}</span>
              <span class="account-card-type" :class="card.backend_type">{{ card.backend_type }}</span>
              <span v-if="card.plan" class="plan-label">{{ card.plan }}</span>
              <span
                v-if="card.windows.some((w: any) => w.shared_with?.length)"
                class="shared-creds-badge"
                :title="'Shares credentials with: ' + card.windows.find((w: any) => w.shared_with?.length)?.shared_with?.join(', ')"
              >Shared</span>
              <div v-if="getSessionForAccount(card.account_id)" class="session-indicator">
                <span class="session-dot"></span>
                <span class="session-label">
                  {{ getSessionForAccount(card.account_id)?.backend_type || 'Running' }}
                  &middot; {{ getSessionForAccount(card.account_id)?.execution_id?.slice(0, 8) }}
                </span>
              </div>
              <svg class="expand-chevron" :class="{ expanded: expandedCards.has(card.account_id) }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </div>

            <!-- No data message for accounts with no monitoring data -->
            <div v-if="card.windows.every((w: any) => w.no_data)" class="monitoring-no-data">
              <span class="no-data-icon">!</span>
              <span>No monitoring data available. Check if the account's OAuth token is valid.</span>
            </div>

            <!-- Gauges grid -->
            <div v-else class="monitoring-gauges-grid">
              <div
                v-for="(w, wIdx) in card.windows.filter((w: any) => !w.no_data)"
                :key="w.window_type"
                class="monitoring-gauge-cell"
              >
                <RateLimitGauge
                  :percentage="w.percentage"
                  :label="getGaugeLabel(w.window_type)"
                  :tokens-used="w.tokens_used"
                  :tokens-limit="w.tokens_limit"
                  :threshold-level="w.threshold_level"
                  :accent-color="getGaugeAccentColor(card.backend_type, w.window_type, wIdx)"
                />
                <div class="gauge-rate-row">
                  <span
                    class="rate-display-inline"
                    :class="{ muted: !isRateAvailable(w.consumption_rates, card.account_id) }"
                  >
                    {{ formatRate(w.consumption_rates, card.account_id) }}
                  </span>
                  <span v-if="w.resets_at" class="resets-at-badge" :class="getResetUrgency(w.resets_at)">
                    <span class="resets-label">Resets in </span>
                    <span class="resets-time">{{ getCountdownText(card.account_id, w.window_type) || formatRelativeReset(w.resets_at) }}</span>
                  </span>
                  <span v-if="w.eta" class="depletion-badge" :class="depletionUrgencyClass(w.eta)">
                    {{ formatDepletion(w.eta) }}
                  </span>
                </div>
              </div>
            </div>

            <!-- Expanded section (click-to-expand) -->
            <template v-if="expandedCards.has(card.account_id)">
              <!-- Combined usage chart: all windows on one graph -->
              <div
                v-if="combinedHistoriesCache[card.account_id]?.length > 0"
                class="monitoring-trend-section"
              >
                <div class="trend-section-header" @click.stop>
                  <span class="trend-section-label">All Windows Usage</span>
                  <div class="rate-selector">
                    <button
                      v-for="(label, key) in rateWindowLabels"
                      :key="key"
                      class="rate-pill"
                      :class="{ active: getCardRateWindow(card.account_id) === key }"
                      @click.stop="emit('update:selectedRateWindows', { [card.account_id]: key as RateWindow })"
                    >
                      {{ label }}
                    </button>
                  </div>
                </div>
                <CombinedUsageChart
                  :window-histories="combinedHistoriesCache[card.account_id]"
                  :time-range-start="getEffectiveChartStart(card)"
                  :time-range-end="getEffectiveChartEnd(card)"
                />
              </div>

              <!-- Remaining time projection chart with window selector -->
              <div class="monitoring-trend-section">
                <div class="projection-header">
                  <span class="trend-section-label">Remaining Capacity</span>
                  <div class="projection-window-selector" @click.stop>
                    <button
                      v-for="pw in getProjectionWindows(card)"
                      :key="pw.windowType"
                      class="rate-pill"
                      :class="{ active: selectedProjectionWindow[card.account_id] === pw.windowType }"
                      @click.stop="handleProjectionWindowChange(card.account_id, pw.windowType)"
                    >
                      {{ pw.label }}
                    </button>
                  </div>
                </div>
                <RemainingTimeChart
                  v-if="(projectionHistoryCache[card.account_id]?.length ?? 0) >= 2"
                  :history="projectionHistoryCache[card.account_id]"
                  :label="getWindowLabel(selectedProjectionWindow[card.account_id] || '') + ' remaining'"
                  :resets-at="getProjectionResetAt(card.account_id)"
                  :time-range-start="getEffectiveChartStart(card)"
                  :time-range-end="getEffectiveChartEnd(card)"
                  :rate-per-hour="getProjectionRatePerHour(card.account_id)"
                />
                <div v-else class="trend-no-data">Not enough data yet</div>
              </div>
            </template>
          </div>
        </div><!-- .monitoring-accounts-grid -->
      </div><!-- .backend-group -->
    </div><!-- .monitoring-backend-groups -->
  </div>
</template>

<style scoped>
.section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.section-title {
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.inline-refresh-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  vertical-align: middle;
  margin-left: 8px;
}

.monitoring-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.monitoring-status-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.monitoring-status-badge.active {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
}

.check-now-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--accent-cyan);
  border-radius: 6px;
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.check-now-btn:hover:not(:disabled) {
  background: var(--accent-cyan);
  color: var(--bg-primary);
}

.check-now-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.check-now-btn svg {
  width: 14px;
  height: 14px;
}

.btn-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.monitoring-disabled {
  text-align: center;
  padding: 32px 16px;
  color: var(--text-muted);
  font-size: 0.9rem;
}

.monitoring-loading-full {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 48px 16px;
  color: var(--text-tertiary);
  font-size: 0.9rem;
}

.loading-spinner-large {
  width: 36px;
  height: 36px;
  border: 3px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.monitoring-collecting {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 16px;
  color: var(--text-tertiary);
  font-size: 0.9rem;
}

.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.monitoring-mode-tag {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 8px;
}

.monitoring-mode-tag.active {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
}

.monitoring-mode-tag.manual {
  background: rgba(255, 170, 0, 0.12);
  color: #d4a053;
}

.monitoring-backend-groups {
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.backend-group-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.backend-group-icon {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.backend-group-icon svg {
  width: 14px;
  height: 14px;
  color: white;
}

.backend-group-icon.claude { background: linear-gradient(135deg, #D97757, #bf6344); }
.backend-group-icon.codex { background: linear-gradient(135deg, #10A37F, #0d8a6a); }
.backend-group-icon.gemini { background: linear-gradient(135deg, #4285F4, #3575db); }
.backend-group-icon.opencode { background: linear-gradient(135deg, #00B894, #00a07e); }

.backend-group-label {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.monitoring-accounts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  max-width: 100%;
  gap: 20px;
}

@media (min-width: 900px) {
  .monitoring-accounts-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.monitoring-account-card {
  background: var(--bg-tertiary);
  border: 1px solid transparent;
  border-radius: 12px;
  padding: 20px;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.monitoring-account-card:hover {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 0 1px var(--accent-cyan-dim), 0 4px 16px rgba(0, 212, 255, 0.08);
}

.monitoring-account-card.expanded {
  border-color: var(--border-default);
}

.account-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.account-card-name {
  font-weight: 600;
  font-size: 1rem;
  color: var(--text-primary);
}

.account-card-icon {
  width: 22px;
  height: 22px;
  border-radius: 5px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.account-card-icon svg {
  width: 12px;
  height: 12px;
  color: white;
}

.account-card-icon.claude { background: linear-gradient(135deg, #D97757, #bf6344); }
.account-card-icon.codex { background: linear-gradient(135deg, #10A37F, #0d8a6a); }
.account-card-icon.gemini { background: linear-gradient(135deg, #4285F4, #3575db); }
.account-card-icon.opencode { background: linear-gradient(135deg, #00B894, #00a07e); }

.account-card-type {
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.account-card-type.claude {
  background: rgba(217, 119, 87, 0.15);
  color: #D97757;
}

.account-card-type.codex {
  background: rgba(16, 163, 127, 0.15);
  color: #10A37F;
}

.account-card-type.gemini {
  background: rgba(66, 133, 244, 0.15);
  color: #4285F4;
}

.account-card-type.opencode {
  background: rgba(0, 184, 148, 0.15);
  color: #00B894;
}

.plan-label {
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  background: rgba(99, 102, 241, 0.15);
  color: #818cf8;
}

.monitoring-no-data {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 16px;
  color: var(--text-muted);
  font-size: 0.85rem;
  background: var(--bg-secondary);
  border-radius: 10px;
  margin-bottom: 12px;
}

.no-data-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: rgba(234, 179, 8, 0.15);
  color: #eab308;
  font-size: 0.8rem;
  font-weight: 700;
  flex-shrink: 0;
}

.shared-creds-badge {
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 0.65rem;
  font-weight: 600;
  background: rgba(255, 170, 0, 0.15);
  color: #ffaa00;
  cursor: help;
}

.session-indicator {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(34, 197, 94, 0.12);
}

.session-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  flex-shrink: 0;
  animation: pulse-dot 2s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.session-label {
  font-size: 0.7rem;
  font-weight: 600;
  color: #86efac;
  white-space: nowrap;
}

.monitoring-gauges-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.monitoring-gauge-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 8px;
  background: var(--bg-secondary);
  border-radius: 10px;
}

.gauge-rate-row {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  margin-top: 4px;
}

.rate-display-inline {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.rate-display-inline.muted {
  color: var(--text-muted);
  font-weight: 400;
}

.resets-at-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 0.7rem;
  font-weight: 600;
  white-space: nowrap;
}

.resets-at-badge.soon {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
}

.resets-at-badge.normal {
  background: rgba(255, 170, 0, 0.12);
  color: #d4a053;
}

.resets-label {
  opacity: 0.7;
}

.resets-time {
  font-weight: 700;
  font-family: var(--font-mono);
}

.depletion-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 0.6rem;
  font-weight: 600;
  white-space: nowrap;
}

.depletion-badge.safe,
.depletion-badge.projected {
  background: rgba(34, 197, 94, 0.12);
  color: #22c55e;
}

.depletion-badge.at_limit {
  background: rgba(234, 179, 8, 0.12);
  color: #eab308;
}

.depletion-badge.no_data,
.depletion-badge.unknown {
  background: rgba(107, 114, 128, 0.12);
  color: #6b7280;
}

.expand-chevron {
  width: 18px;
  height: 18px;
  color: var(--text-muted);
  transition: transform 0.2s ease;
  flex-shrink: 0;
  margin-left: auto;
}

.expand-chevron.expanded {
  transform: rotate(180deg);
}

.monitoring-trend-section {
  padding: 12px 0;
  border-top: 1px solid var(--border-subtle);
}

.trend-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}

.trend-section-header .trend-section-label {
  margin-bottom: 0;
}

.trend-section-label {
  font-size: 0.7rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}

.projection-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}

.projection-window-selector {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.trend-no-data {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 80px;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.rate-selector {
  display: flex;
  gap: 4px;
}

.rate-pill {
  padding: 4px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  background: transparent;
  color: var(--text-muted);
  font-size: 0.7rem;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.rate-pill:hover {
  color: var(--text-primary);
  border-color: var(--border-default);
}

.rate-pill.active {
  color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
  border-color: transparent;
}

@media (max-width: 900px) {
  .monitoring-accounts-grid {
    grid-template-columns: 1fr;
  }
}
</style>
