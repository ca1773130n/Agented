<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import type { HealthAlert, HealthStatusResponse } from '../services/api';
import { analyticsApi, ApiError } from '../services/api';
import HealthAlertList from '../components/analytics/HealthAlertList.vue';
import LoadingState from '../components/base/LoadingState.vue';
import StatCard from '../components/base/StatCard.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

const isLoading = ref(true);
const isRunningCheck = ref(false);
const healthStatus = ref<HealthStatusResponse | null>(null);
const alerts = ref<HealthAlert[]>([]);
let refreshInterval: ReturnType<typeof setInterval> | null = null;

async function loadData() {
  try {
    const [statusRes, alertsRes] = await Promise.all([
      analyticsApi.fetchHealthStatus(),
      analyticsApi.fetchHealthAlerts({ limit: 50 }),
    ]);
    healthStatus.value = statusRes;
    alerts.value = alertsRes.alerts || [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load health data';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

async function refreshAlerts() {
  try {
    const alertsRes = await analyticsApi.fetchHealthAlerts({ limit: 50 });
    alerts.value = alertsRes.alerts || [];
    const statusRes = await analyticsApi.fetchHealthStatus();
    healthStatus.value = statusRes;
  } catch {
    // Silent refresh failure
  }
}

async function runHealthCheck() {
  isRunningCheck.value = true;
  try {
    await analyticsApi.runHealthCheck();
    showToast('Health check completed', 'success');
    await refreshAlerts();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to run health check';
    showToast(message, 'error');
  } finally {
    isRunningCheck.value = false;
  }
}

async function handleAcknowledge(alertId: number) {
  try {
    await analyticsApi.acknowledgeAlert(alertId);
    // Update locally
    const alert = alerts.value.find(a => a.id === alertId);
    if (alert) alert.acknowledged = true;
    showToast('Alert acknowledged', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to acknowledge alert';
    showToast(message, 'error');
  }
}

onMounted(() => {
  loadData();
  refreshInterval = setInterval(refreshAlerts, 30000);
});

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval);
});
</script>

<template>
  <div class="health-dashboard">

    <LoadingState v-if="isLoading" message="Loading health data..." />

    <template v-else>
      <!-- Status summary -->
      <div class="card status-card">
        <div class="status-card-inner">
          <div class="status-header">
            <div class="status-title-area">
              <div class="status-icon" :class="{ critical: (healthStatus?.critical_count ?? 0) > 0, ok: (healthStatus?.critical_count ?? 0) === 0 }">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                </svg>
              </div>
              <div>
                <h3>Bot Health Monitor</h3>
                <p class="status-subtitle">
                  <template v-if="healthStatus?.last_check_time">Last check: {{ new Date(healthStatus.last_check_time).toLocaleString() }}</template>
                  <template v-else>No health checks run yet</template>
                </p>
              </div>
            </div>
            <div class="status-actions">
              <button class="btn btn-primary" :disabled="isRunningCheck" @click="runHealthCheck">
                <svg v-if="isRunningCheck" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                </svg>
                {{ isRunningCheck ? 'Running...' : 'Run Health Check' }}
              </button>
            </div>
          </div>

          <div class="stats-grid">
            <StatCard title="Total Alerts" :value="healthStatus?.total_alerts ?? 0" />
            <StatCard title="Critical" :value="healthStatus?.critical_count ?? 0" color="var(--accent-crimson)" />
            <StatCard title="Warnings" :value="healthStatus?.warning_count ?? 0" color="var(--accent-amber)" />
            <StatCard title="Auto-refresh" value="30s" />
          </div>
        </div>
      </div>

      <!-- Alert list -->
      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            Health Alerts
          </h3>
          <span class="card-badge">{{ alerts.length }} total</span>
        </div>
        <HealthAlertList :alerts="alerts" @acknowledge="handleAcknowledge" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.health-dashboard {
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

.card {
  padding: 24px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-header h3 svg {
  width: 18px;
  height: 18px;
  color: var(--accent-cyan);
}

.card-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 4px 10px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.status-card {
  background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%);
  border-color: var(--border-default);
  padding: 0;
  overflow: hidden;
}

.status-card-inner {
  padding: 28px;
}

.status-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 28px;
  flex-wrap: wrap;
  gap: 16px;
}

.status-title-area {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.status-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
}

.status-icon svg {
  width: 24px;
  height: 24px;
  color: var(--text-secondary);
}

.status-icon.ok {
  background: var(--accent-emerald-dim);
  border-color: var(--accent-emerald);
}

.status-icon.ok svg {
  color: var(--accent-emerald);
}

.status-icon.critical {
  background: var(--accent-crimson-dim);
  border-color: var(--accent-crimson);
}

.status-icon.critical svg {
  color: var(--accent-crimson);
}

.status-title-area h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.status-subtitle {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

.status-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.spinner {
  width: 16px;
  height: 16px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 900px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .status-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
