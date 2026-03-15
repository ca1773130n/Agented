<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';
import { analyticsApi, ApiError } from '../services/api';
import type { HealthAlert } from '../services/api';

const router = useRouter();
const showToast = useToast();

const alerts = ref<HealthAlert[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const processingId = ref<number | null>(null);

const activeFilter = ref<string>('all');

const filtered = computed(() => {
  if (activeFilter.value === 'all') return alerts.value;
  if (activeFilter.value === 'acknowledged') return alerts.value.filter(a => a.acknowledged);
  if (activeFilter.value === 'active') return alerts.value.filter(a => !a.acknowledged);
  if (activeFilter.value === 'critical') return alerts.value.filter(a => a.severity === 'critical');
  if (activeFilter.value === 'warning') return alerts.value.filter(a => a.severity === 'warning');
  return alerts.value;
});

const counts = computed(() => ({
  all: alerts.value.length,
  active: alerts.value.filter(a => !a.acknowledged).length,
  acknowledged: alerts.value.filter(a => a.acknowledged).length,
  critical: alerts.value.filter(a => a.severity === 'critical').length,
  warning: alerts.value.filter(a => a.severity === 'warning').length,
}));

async function loadAlerts() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await analyticsApi.fetchHealthAlerts({ limit: 100 });
    alerts.value = data.alerts ?? [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load alerts';
    loadError.value = message;
  } finally {
    isLoading.value = false;
  }
}

async function handleAcknowledge(alert: HealthAlert) {
  processingId.value = alert.id;
  try {
    await analyticsApi.acknowledgeAlert(alert.id);
    const idx = alerts.value.findIndex(a => a.id === alert.id);
    if (idx !== -1) alerts.value[idx] = { ...alerts.value[idx], acknowledged: true };
    showToast('Alert acknowledged', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to acknowledge alert';
    showToast(message, 'error');
  } finally {
    processingId.value = null;
  }
}

async function handleRunCheck() {
  try {
    await analyticsApi.runHealthCheck();
    showToast('Health check started', 'success');
    // Reload alerts after a brief delay to allow the check to complete
    setTimeout(loadAlerts, 2000);
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to run health check';
    showToast(message, 'error');
  }
}

function severityColor(s: string): string {
  const map: Record<string, string> = { critical: '#ef4444', warning: '#f59e0b' };
  return map[s] ?? '#6b7280';
}

function alertTypeLabel(type: string): string {
  const map: Record<string, string> = {
    consecutive_failure: 'Consecutive Failures',
    slow_execution: 'Slow Execution',
    missing_fire: 'Missing Trigger Fire',
    budget_exceeded: 'Budget Exceeded',
  };
  return map[type] ?? type;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString();
}

onMounted(loadAlerts);
</script>

<template>
  <div class="alert-grouping">

    <PageHeader
      title="Health Alerts"
      subtitle="Monitor bot health alerts with severity tracking and acknowledgment."
    >
      <template #actions>
        <button class="btn btn-ghost" @click="handleRunCheck">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
          Run Health Check
        </button>
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" message="Loading health alerts..." />

    <div v-else-if="loadError" class="card error-card">
      <div class="error-inner">
        <p>{{ loadError }}</p>
        <button class="btn btn-ghost" @click="loadAlerts">Retry</button>
      </div>
    </div>

    <template v-else>
      <div class="filter-tabs">
        <button
          v-for="[key, label] in [['all', 'All'], ['active', 'Active'], ['critical', 'Critical'], ['warning', 'Warning'], ['acknowledged', 'Acknowledged']]"
          :key="key"
          class="filter-tab"
          :class="{ active: activeFilter === key }"
          @click="activeFilter = key"
        >
          {{ label }}
          <span class="tab-count">{{ counts[key as keyof typeof counts] }}</span>
        </button>
      </div>

      <div class="groups-list">
        <div
          v-for="alert in filtered"
          :key="alert.id"
          class="card group-card"
          :class="{ 'is-acked': alert.acknowledged }"
        >
          <div class="group-header">
            <div class="severity-bar" :style="{ background: severityColor(alert.severity) }"></div>
            <div class="group-main">
              <div class="group-title-row">
                <div class="sev-badge" :style="{ color: severityColor(alert.severity), background: severityColor(alert.severity) + '20' }">
                  {{ alert.severity }}
                </div>
                <div class="type-badge">{{ alertTypeLabel(alert.alert_type) }}</div>
                <span class="trigger-tag">{{ alert.trigger_id }}</span>
              </div>
              <p class="group-message">{{ alert.message }}</p>
              <div v-if="alert.details" class="root-cause">
                <div class="rc-label">Details</div>
                <p class="rc-text">{{ alert.details }}</p>
              </div>
              <div class="group-meta">
                <span class="meta-item">Created: {{ formatDate(alert.created_at) }}</span>
                <span v-if="alert.acknowledged" class="status-pill acked">Acknowledged</span>
                <span v-else class="status-pill active-pill">Active</span>
              </div>
            </div>
            <div class="group-actions">
              <template v-if="!alert.acknowledged">
                <button class="btn btn-sm btn-ack" :disabled="processingId === alert.id" @click="handleAcknowledge(alert)">
                  {{ processingId === alert.id ? '...' : 'Acknowledge' }}
                </button>
              </template>
              <template v-else>
                <span class="acked-label">Acknowledged</span>
              </template>
            </div>
          </div>
        </div>

        <div v-if="filtered.length === 0" class="card empty-card">
          <div class="empty-inner">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="40" height="40" style="opacity: 0.3; color: var(--text-tertiary)">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <p>No alerts in this category</p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.alert-grouping {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.filter-tabs {
  display: flex;
  gap: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 4px;
  width: fit-content;
}

.filter-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 7px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.15s;
}

.filter-tab.active {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.tab-count {
  font-size: 0.72rem;
  font-weight: 700;
  background: var(--bg-elevated);
  color: var(--text-tertiary);
  padding: 1px 6px;
  border-radius: 10px;
}

.filter-tab.active .tab-count {
  background: var(--accent-cyan);
  color: #000;
}

.groups-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.error-card, .empty-card { padding: 48px; }

.error-inner, .empty-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.error-inner p, .empty-inner p {
  font-size: 0.875rem;
  color: var(--text-tertiary);
  margin: 0;
}

.group-card.is-acked { opacity: 0.55; }

.group-header {
  display: flex;
  gap: 0;
}

.severity-bar {
  width: 4px;
  flex-shrink: 0;
}

.group-main {
  flex: 1;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.group-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.sev-badge {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.type-badge {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-primary);
}

.trigger-tag {
  font-size: 0.7rem;
  padding: 2px 8px;
  background: rgba(6, 182, 212, 0.1);
  border: 1px solid rgba(6, 182, 212, 0.2);
  border-radius: 4px;
  color: var(--accent-cyan);
  font-family: monospace;
}

.group-message {
  font-size: 0.9rem;
  color: var(--text-primary);
  margin: 0;
  line-height: 1.5;
}

.root-cause {
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.rc-label {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}

.rc-text {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

.group-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.meta-item {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.status-pill {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: capitalize;
  margin-left: auto;
}

.status-pill.acked { background: rgba(107, 114, 128, 0.15); color: #6b7280; }
.status-pill.active-pill { background: rgba(239, 68, 68, 0.15); color: #ef4444; }

.group-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  justify-content: center;
  border-left: 1px solid var(--border-subtle);
}

.acked-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  font-style: italic;
}

.btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-sm { padding: 6px 12px; font-size: 0.8rem; }

.btn-ack {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  border: 1px solid rgba(245, 158, 11, 0.3);
  white-space: nowrap;
}

.btn-ack:hover:not(:disabled) { background: rgba(245, 158, 11, 0.25); }
.btn-ack:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-ghost {
  padding: 8px 14px;
  font-size: 0.875rem;
  background: transparent;
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 8px;
}

.btn-ghost:hover { border-color: var(--accent-cyan); color: var(--text-primary); }
</style>
