<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type {
  MonitoringStatus,
  RotationSession,
  SnapshotHistory,
  WindowSnapshot,
} from '../../services/api';
import { useTokenFormatting } from '../../composables/useTokenFormatting';
import RateLimitGauge from './RateLimitGauge.vue';
import CombinedUsageChart from './CombinedUsageChart.vue';
import RemainingTimeChart from './RemainingTimeChart.vue';
import {
  depletionUrgencyClass,
  formatDepletion,
  formatRate,
  formatRelativeReset,
  getGaugeAccentColor,
  getGaugeLabel,
  getRateWindowMinutes,
  getResetUrgency,
  getTrendKey,
  getWindowLabel,
  isRateAvailable,
  toRatePctPerHour,
} from './monitoringHelpers';
import { rateWindowLabels, type AccountCard, type CombinedHistoryEntry, type RateWindow } from './types';

const props = defineProps<{
  card: AccountCard;
  expanded: boolean;
  trendHistories: Record<string, SnapshotHistory>;
  selectedRateWindow: RateWindow;
  selectedProjectionWindowType: string | undefined;
  chartTimeRangeStart: string;
  chartTimeRangeEnd: string;
  rotationSession: RotationSession | undefined;
  getCountdownText: (accountId: number, windowType: string) => string | undefined;
}>();

const emit = defineEmits<{
  (e: 'toggle'): void;
  (e: 'select-rate-window', value: RateWindow): void;
  (e: 'select-projection-window', windowType: string): void;
}>();

const { t } = useI18n();
const { parseWindowType } = useTokenFormatting();

const rateWindow = computed<RateWindow>(() => props.selectedRateWindow || '24h');
const rateWindowMinutes = computed(() => getRateWindowMinutes(rateWindow.value));

function gaugeLabel(windowType: string): string {
  return getGaugeLabel(windowType, parseWindowType);
}

function windowLabel(windowType: string): string {
  return getWindowLabel(windowType, parseWindowType);
}

const visibleWindows = computed(() =>
  props.card.windows.filter((w: WindowSnapshot) => !w.no_data),
);

const allWindowsNoData = computed(() =>
  props.card.windows.every((w: WindowSnapshot) => w.no_data),
);

const sharedWith = computed(() => {
  const w = props.card.windows.find(
    (win: WindowSnapshot & { shared_with?: string[] }) => win.shared_with?.length,
  );
  return (w as WindowSnapshot & { shared_with?: string[] })?.shared_with;
});

// Authoritative lockout: Claude Code actually 429'd this account. Overrides
// the (possibly low) usage gauges with the real "limit reached · resets …".
const blockedInfo = computed(() => {
  const w = props.card.windows.find(
    (win: WindowSnapshot) =>
      !!win.rate_limited_until && new Date(win.rate_limited_until).getTime() > Date.now(),
  );
  if (!w?.rate_limited_until) return null;
  return { until: w.rate_limited_until, reason: w.rate_limit_reason || '' };
});

const dataBounds = computed(() => {
  let earliest = Infinity;
  let latest = 0;
  for (const w of props.card.windows) {
    const key = getTrendKey(props.card.account_id, w.window_type);
    const history = props.trendHistories[key]?.history || [];
    for (const h of history) {
      const t = new Date(h.recorded_at).getTime();
      if (t < earliest) earliest = t;
      if (t > latest) latest = t;
    }
  }
  return { earliest: earliest === Infinity ? 0 : earliest, latest };
});

const effectiveChartStart = computed(() => {
  const { earliest, latest } = dataBounds.value;
  if (latest <= 0) return props.chartTimeRangeStart;
  const rwMinutes = rateWindowMinutes.value;
  const windowStart = latest - rwMinutes * 60000;
  if (earliest > windowStart) {
    const span = latest - earliest;
    return new Date(earliest - span * 0.03).toISOString();
  }
  return new Date(windowStart).toISOString();
});

const effectiveChartEnd = computed(() => {
  const { earliest, latest } = dataBounds.value;
  if (latest <= 0) return props.chartTimeRangeEnd;
  const rwMinutes = rateWindowMinutes.value;
  const dataSpan = latest - (earliest > 0 ? earliest : latest);
  let pad = Math.max(dataSpan * 0.03, rwMinutes * 60000 * 0.02);
  const hasAnyRate = props.card.windows.some(
    (w) => toRatePctPerHour(w, rateWindow.value) != null,
  );
  if (hasAnyRate) {
    const projectionMs = 2 * 3600000;
    pad = Math.max(pad, projectionMs * 1.05);
  }
  return new Date(latest + pad).toISOString();
});

const combinedHistories = computed<CombinedHistoryEntry[]>(() => {
  return props.card.windows
    .map((w: WindowSnapshot, idx: number) => {
      const key = getTrendKey(props.card.account_id, w.window_type);
      const history = props.trendHistories[key]?.history || [];
      return {
        windowType: w.window_type,
        label: windowLabel(w.window_type),
        history,
        color: getGaugeAccentColor(props.card.backend_type, w.window_type, idx) || undefined,
        ratePerHour: toRatePctPerHour(w, rateWindow.value),
        resetsAt: w.resets_at || null,
      };
    })
    .filter((wh) => wh.history.length >= 2);
});

const projectionHistory = computed<SnapshotHistory['history']>(() => {
  const windowType = props.selectedProjectionWindowType;
  if (!windowType) return [];
  const key = getTrendKey(props.card.account_id, windowType);
  return props.trendHistories[key]?.history || [];
});

const projectionWindows = computed(() =>
  props.card.windows.map((w: WindowSnapshot) => ({
    windowType: w.window_type,
    label: windowLabel(w.window_type),
  })),
);

const projectionResetAt = computed<string | null>(() => {
  const windowType = props.selectedProjectionWindowType;
  if (!windowType) return null;
  const w = props.card.windows.find(
    (win: WindowSnapshot) => win.window_type === windowType,
  );
  return w?.resets_at || null;
});

const projectionRatePerHour = computed<number | undefined>(() => {
  const windowType = props.selectedProjectionWindowType;
  if (!windowType) return undefined;
  const w = props.card.windows.find(
    (win: WindowSnapshot) => win.window_type === windowType,
  );
  if (!w) return undefined;
  return toRatePctPerHour(w, rateWindow.value);
});

function rateText(rates: WindowSnapshot['consumption_rates']): string {
  return formatRate(rates as MonitoringStatus['windows'][number]['consumption_rates'], rateWindow.value);
}

function rateAvailable(rates: WindowSnapshot['consumption_rates']): boolean {
  return isRateAvailable(rates as MonitoringStatus['windows'][number]['consumption_rates'], rateWindow.value);
}
</script>

<template>
  <div
    class="monitoring-account-card"
    :class="{ expanded }"
    @click="emit('toggle')"
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
        v-if="blockedInfo"
        class="blocked-badge"
        :title="blockedInfo.reason || ''"
      >{{ t('monitoringAccountCard.limitReached') }} &middot; {{ t('monitoringAccountCard.resetsIn', { time: formatRelativeReset(blockedInfo.until) }) }}</span>
      <span
        v-if="sharedWith?.length"
        class="shared-creds-badge"
        :title="t('monitoringAccountCard.sharesCredentialsWith', { accounts: sharedWith.join(', ') })"
      >{{ t('monitoringAccountCard.shared') }}</span>
      <div v-if="rotationSession" class="session-indicator">
        <span class="session-dot"></span>
        <span class="session-label">
          {{ rotationSession.backend_type || t('monitoringAccountCard.running') }}
          &middot; {{ rotationSession.execution_id?.slice(0, 8) }}
        </span>
      </div>
      <svg class="expand-chevron" :class="{ expanded }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </div>

    <!-- No data message for accounts with no monitoring data -->
    <div v-if="allWindowsNoData" class="monitoring-no-data">
      <span class="no-data-icon">!</span>
      <span>{{ t('monitoringAccountCard.noMonitoringData') }}</span>
    </div>

    <!-- Gauges grid -->
    <div v-else class="monitoring-gauges-grid">
      <div
        v-for="(w, wIdx) in visibleWindows"
        :key="w.window_type"
        class="monitoring-gauge-cell"
      >
        <RateLimitGauge
          :percentage="w.percentage"
          :label="gaugeLabel(w.window_type)"
          :tokens-used="w.tokens_used"
          :tokens-limit="w.tokens_limit"
          :threshold-level="w.threshold_level"
          :accent-color="getGaugeAccentColor(card.backend_type, w.window_type, wIdx)"
        />
        <div class="gauge-rate-row">
          <span
            class="rate-display-inline"
            :class="{ muted: !rateAvailable(w.consumption_rates) }"
          >
            {{ rateText(w.consumption_rates) }}
          </span>
          <span v-if="w.resets_at" class="resets-at-badge" :class="getResetUrgency(w.resets_at)">
            <span class="resets-label">{{ t('monitoringAccountCard.resetsIn') }} </span>
            <span class="resets-time">{{ getCountdownText(card.account_id, w.window_type) || formatRelativeReset(w.resets_at) }}</span>
          </span>
          <span v-if="w.eta" class="depletion-badge" :class="depletionUrgencyClass(w.eta)">
            {{ formatDepletion(w.eta) }}
          </span>
        </div>
      </div>
    </div>

    <!-- Expanded section (click-to-expand) -->
    <template v-if="expanded">
      <!-- Combined usage chart: all windows on one graph -->
      <div
        v-if="combinedHistories.length > 0"
        class="monitoring-trend-section"
      >
        <div class="trend-section-header" @click.stop>
          <span class="trend-section-label">{{ t('monitoringAccountCard.allWindowsUsage') }}</span>
          <div class="rate-selector">
            <button
              v-for="(label, key) in rateWindowLabels"
              :key="key"
              class="rate-pill"
              :class="{ active: rateWindow === key }"
              @click.stop="emit('select-rate-window', key as RateWindow)"
            >
              {{ label }}
            </button>
          </div>
        </div>
        <CombinedUsageChart
          :window-histories="combinedHistories"
          :time-range-start="effectiveChartStart"
          :time-range-end="effectiveChartEnd"
        />
      </div>

      <!-- Remaining time projection chart with window selector -->
      <div class="monitoring-trend-section">
        <div class="projection-header">
          <span class="trend-section-label">{{ t('monitoringAccountCard.remainingCapacity') }}</span>
          <div class="projection-window-selector" @click.stop>
            <button
              v-for="pw in projectionWindows"
              :key="pw.windowType"
              class="rate-pill"
              :class="{ active: selectedProjectionWindowType === pw.windowType }"
              @click.stop="emit('select-projection-window', pw.windowType)"
            >
              {{ pw.label }}
            </button>
          </div>
        </div>
        <RemainingTimeChart
          v-if="projectionHistory.length >= 2"
          :history="projectionHistory"
          :label="t('monitoringAccountCard.windowRemaining', { window: windowLabel(selectedProjectionWindowType || '') })"
          :resets-at="projectionResetAt"
          :time-range-start="effectiveChartStart"
          :time-range-end="effectiveChartEnd"
          :rate-per-hour="projectionRatePerHour"
        />
        <div v-else class="trend-no-data">{{ t('monitoringAccountCard.notEnoughData') }}</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
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

.blocked-badge {
  padding: 3px 9px;
  border-radius: 6px;
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: rgba(239, 68, 68, 0.16);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.4);
  cursor: help;
  white-space: nowrap;
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
</style>
