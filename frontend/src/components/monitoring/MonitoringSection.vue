<script setup lang="ts">
import { computed, toRef } from 'vue';
import type {
  MonitoringStatus,
  RotationEvaluatorStatus,
  RotationSession,
  SnapshotHistory,
} from '../../services/api';
import { useMonitoringCountdowns } from '../../composables/useMonitoringCountdowns';
import { buildAccountCards, groupCardsByBackend } from './monitoringHelpers';
import type { RateWindow } from './types';
import MonitoringHeader from './MonitoringHeader.vue';
import MonitoringAccountCard from './MonitoringAccountCard.vue';

const props = defineProps<{
  monitoringStatus: MonitoringStatus | null;
  monitoringLoading: boolean;
  pollNowLoading: boolean;
  monitoringRefreshing: boolean;
  trendHistories: Record<string, SnapshotHistory>;
  expandedCards: Set<number>;
  selectedRateWindows: Record<number, RateWindow>;
  selectedProjectionWindow: Record<number, string>;
  chartTimeRangeStart: string;
  chartTimeRangeEnd: string;
  rotationSessions?: RotationSession[];
  rotationEvaluator?: RotationEvaluatorStatus;
}>();

const emit = defineEmits<{
  (e: 'poll-now'): void;
  (e: 'toggle-card', accountId: number): void;
  (e: 'update:selectedRateWindows', value: Record<number, RateWindow>): void;
  (e: 'update:selectedProjectionWindow', value: Record<number, string>): void;
}>();

const { getCountdownText } = useMonitoringCountdowns(toRef(props, 'monitoringStatus'));

const monitoringAccountCards = computed(() => buildAccountCards(props.monitoringStatus));
const monitoringCardsByBackend = computed(() => groupCardsByBackend(monitoringAccountCards.value));

function getSessionForAccount(accountId: number): RotationSession | undefined {
  return props.rotationSessions?.find(
    (s) => s.account_id !== null && s.account_id === accountId,
  );
}

function getCardRateWindow(accountId: number): RateWindow {
  return props.selectedRateWindows[accountId] || '24h';
}

function handleSelectRateWindow(accountId: number, value: RateWindow) {
  emit('update:selectedRateWindows', { [accountId]: value });
}

function handleSelectProjectionWindow(accountId: number, windowType: string) {
  const updated = { ...props.selectedProjectionWindow, [accountId]: windowType };
  emit('update:selectedProjectionWindow', updated);
}
</script>

<template>
  <div class="section">
    <MonitoringHeader
      :monitoring-status="monitoringStatus"
      :monitoring-refreshing="monitoringRefreshing"
      :poll-now-loading="pollNowLoading"
      @poll-now="emit('poll-now')"
    />

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
          <MonitoringAccountCard
            v-for="card in group.cards"
            :key="card.account_id"
            :card="card"
            :expanded="expandedCards.has(card.account_id)"
            :trend-histories="trendHistories"
            :selected-rate-window="getCardRateWindow(card.account_id)"
            :selected-projection-window-type="selectedProjectionWindow[card.account_id]"
            :chart-time-range-start="chartTimeRangeStart"
            :chart-time-range-end="chartTimeRangeEnd"
            :rotation-session="getSessionForAccount(card.account_id)"
            :get-countdown-text="getCountdownText"
            @toggle="emit('toggle-card', card.account_id)"
            @select-rate-window="(v) => handleSelectRateWindow(card.account_id, v)"
            @select-projection-window="(wt) => handleSelectProjectionWindow(card.account_id, wt)"
          />
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

@media (max-width: 900px) {
  .monitoring-accounts-grid {
    grid-template-columns: 1fr;
  }
}
</style>
