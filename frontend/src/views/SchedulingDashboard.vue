<template>
  <div class="scheduling-dashboard">
    <AppBreadcrumb :items="[{ label: 'Dashboards', action: () => router.push({ name: 'dashboards' }) }, { label: 'Scheduling' }]" />
    <PageHeader title="Scheduling & Rotation" subtitle="Monitor agent execution scheduler and account rotation">
      <template #actions>
        <label class="auto-refresh-toggle">
          <input type="checkbox" v-model="autoRefresh" />
          <span>Auto-refresh (15s)</span>
        </label>
        <button class="refresh-btn" @click="refreshAll" :disabled="isLoading">
          <svg :class="{ spinning: isLoading }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M23 4v6h-6M1 20v-6h6"/>
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
          Refresh
        </button>
      </template>
    </PageHeader>

    <ErrorState
      v-if="error"
      title="Connection Error"
      :message="error"
      @retry="refreshAll"
    />

    <!-- Summary cards -->
    <div class="stats-grid">
      <StatCard title="Active Sessions" :value="rotationStatus?.sessions.length ?? 0" />
      <StatCard title="Queued" :value="schedulerStatus?.global_summary.queued ?? 0" color="var(--accent-amber)" />
      <StatCard title="Running" :value="schedulerStatus?.global_summary.running ?? 0" color="var(--accent-emerald)" />
      <StatCard title="Stopped" :value="schedulerStatus?.global_summary.stopped ?? 0" color="var(--accent-crimson)" />
    </div>

    <!-- Scheduler Sessions -->
    <section class="dashboard-section">
      <h2 class="section-header">Scheduler Sessions</h2>
      <div v-if="!schedulerStatus || schedulerStatus.sessions.length === 0" class="empty-state">
        <p>No scheduler sessions active</p>
      </div>
      <div v-else class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>Account ID</th>
              <th>State</th>
              <th>Stop Reason</th>
              <th>Resume Estimate</th>
              <th>Safe Polls</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="session in schedulerStatus.sessions" :key="session.account_id">
              <td class="mono">{{ session.account_name || session.account_id }}</td>
              <td>
                <span class="state-badge" :class="session.state">{{ session.state }}</span>
              </td>
              <td>{{ session.stop_reason || '—' }}</td>
              <td class="mono">{{ formatTime(session.resume_estimate) }}</td>
              <td class="mono">{{ session.consecutive_safe_polls }}</td>
              <td class="mono">{{ formatTime(session.updated_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Active Rotation Sessions -->
    <section class="dashboard-section">
      <h2 class="section-header">Active Rotation Sessions</h2>
      <div v-if="!rotationStatus || rotationStatus.sessions.length === 0" class="empty-state">
        <p>No active rotation sessions</p>
      </div>
      <div v-else class="rotation-cards">
        <div v-for="session in rotationStatus.sessions" :key="session.execution_id" class="rotation-card">
          <div class="rotation-card-header">
            <span class="mono execution-id">{{ session.execution_id }}</span>
            <span class="badge" :class="session.backend_type ?? ''">{{ session.backend_type ?? 'unknown' }}</span>
          </div>
          <div class="rotation-card-body">
            <div class="rotation-field">
              <span class="field-label">Account</span>
              <span class="mono">{{ getAccountName(session.account_id) }}</span>
            </div>
            <div class="rotation-field">
              <span class="field-label">Trigger</span>
              <span class="mono">{{ session.trigger_id ?? '—' }}</span>
            </div>
            <div class="rotation-field">
              <span class="field-label">Started</span>
              <span class="mono">{{ formatTime(session.started_at) }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Rotation Evaluator Status -->
    <section class="dashboard-section">
      <h2 class="section-header">Rotation Evaluator</h2>
      <div v-if="!rotationStatus" class="empty-state">
        <p>No evaluator data available</p>
      </div>
      <div v-else class="evaluator-grid">
        <div class="evaluator-stat">
          <span class="field-label">Interval</span>
          <span class="mono">{{ rotationStatus.evaluator.evaluation_interval_seconds }}s</span>
        </div>
        <div class="evaluator-stat">
          <span class="field-label">Hysteresis Threshold</span>
          <span class="mono">{{ rotationStatus.evaluator.hysteresis_threshold }}</span>
        </div>
        <div class="evaluator-stat">
          <span class="field-label">Active Evaluations</span>
          <span class="mono">{{ rotationStatus.evaluator.active_evaluations }}</span>
        </div>
        <div v-if="Object.keys(rotationStatus.evaluator.evaluation_states).length > 0" class="evaluator-states">
          <h3 class="subsection-header">Evaluation States</h3>
          <div v-for="(state, execId) in rotationStatus.evaluator.evaluation_states" :key="execId" class="eval-state-row">
            <span class="mono execution-id">{{ execId }}</span>
            <span class="field-label">Consecutive polls: <span class="mono">{{ state.consecutive_rotate_polls }}</span></span>
            <span class="field-label">Last: <span class="mono">{{ formatTime(state.last_evaluated) }}</span></span>
          </div>
        </div>
      </div>
    </section>

    <!-- Rotation Event Timeline -->
    <section class="dashboard-section">
      <h2 class="section-header">Rotation Event Timeline</h2>
      <RotationTimelineChart :events="rotationHistory" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import {
  schedulerApi,
  rotationApi,
  type SchedulerStatus,
  type RotationDashboardStatus,
  type RotationEvent,
} from '../services/api';
import { useWebMcpTool } from '../composables/useWebMcpTool';
import RotationTimelineChart from '../components/monitoring/RotationTimelineChart.vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import StatCard from '../components/base/StatCard.vue';
import ErrorState from '../components/base/ErrorState.vue';

const router = useRouter();

const schedulerStatus = ref<SchedulerStatus | null>(null);
const rotationStatus = ref<RotationDashboardStatus | null>(null);
const rotationHistory = ref<RotationEvent[]>([]);
const isLoading = ref(true);
const error = ref<string | null>(null);
const autoRefresh = ref(true);

const accountNameMap = computed(() => {
  const map: Record<number, string> = {};
  if (schedulerStatus.value?.sessions) {
    for (const s of schedulerStatus.value.sessions) {
      if (s.account_name) map[s.account_id] = s.account_name;
    }
  }
  return map;
});

function getAccountName(accountId: number | null): string {
  if (accountId === null) return '---';
  return accountNameMap.value[accountId] || String(accountId);
}

// WebMCP page-specific tool: exposes rotation status to verification agents
useWebMcpTool({
  name: 'agented_scheduling_get_rotation_status',
  description:
    'Returns the current rotation status including active sessions, recent rotation events, and countdown timers',
  page: 'SchedulingDashboard',
  execute: async () => {
    return {
      content: [
        {
          type: 'text' as const,
          text: JSON.stringify({
            page: 'SchedulingDashboard',
            loaded: !isLoading.value,
            has_error: !!error.value,
            scheduler: schedulerStatus.value
              ? {
                  session_count: schedulerStatus.value.sessions.length,
                  queued: schedulerStatus.value.global_summary.queued,
                  running: schedulerStatus.value.global_summary.running,
                  stopped: schedulerStatus.value.global_summary.stopped,
                }
              : null,
            rotation: rotationStatus.value
              ? {
                  active_sessions: rotationStatus.value.sessions.length,
                  evaluator_interval: rotationStatus.value.evaluator.evaluation_interval_seconds,
                  hysteresis_threshold: rotationStatus.value.evaluator.hysteresis_threshold,
                  active_evaluations: rotationStatus.value.evaluator.active_evaluations,
                }
              : null,
            rotation_history_count: rotationHistory.value.length,
            auto_refresh: autoRefresh.value,
          }),
        },
      ],
    };
  },
  deps: [schedulerStatus, rotationStatus, rotationHistory],
});

let statusInterval: ReturnType<typeof setInterval> | null = null;
let historyInterval: ReturnType<typeof setInterval> | null = null;

function formatTime(val: string | null | undefined): string {
  if (!val) return '—';
  try {
    return new Date(val).toLocaleString();
  } catch {
    return val;
  }
}

async function refreshStatus() {
  try {
    const [sched, rot] = await Promise.all([
      schedulerApi.getStatus(),
      rotationApi.getStatus(),
    ]);
    schedulerStatus.value = sched;
    rotationStatus.value = rot;
    error.value = null;
  } catch (err) {
    error.value = 'Failed to load scheduler/rotation status.';
  }
}

async function refreshHistory() {
  try {
    const data = await rotationApi.getHistory(undefined, 50);
    rotationHistory.value = data.events || [];
  } catch {
    // Non-critical — keep previous data
  }
}

async function refreshAll() {
  isLoading.value = true;
  await Promise.all([refreshStatus(), refreshHistory()]);
  isLoading.value = false;
}

function startAutoRefresh() {
  stopAutoRefresh();
  if (autoRefresh.value) {
    statusInterval = setInterval(refreshStatus, 15_000);
    historyInterval = setInterval(refreshHistory, 60_000);
  }
}

function stopAutoRefresh() {
  if (statusInterval) { clearInterval(statusInterval); statusInterval = null; }
  if (historyInterval) { clearInterval(historyInterval); historyInterval = null; }
}

watch(autoRefresh, (val) => {
  if (val) startAutoRefresh();
  else stopAutoRefresh();
});

onMounted(() => {
  refreshAll();
  startAutoRefresh();
});

onUnmounted(() => {
  stopAutoRefresh();
});
</script>

<style scoped>
.scheduling-dashboard {
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

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
}

.auto-refresh-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}

.auto-refresh-toggle input[type="checkbox"] {
  width: 14px;
  height: 14px;
  accent-color: var(--accent-cyan);
}

.refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--bg-tertiary);
  border-color: var(--border-strong);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.refresh-btn svg {
  width: 14px;
  height: 14px;
}

.refresh-btn svg.spinning {
  animation: spin 1s linear infinite;
}

/* Sections */
.dashboard-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 1.25rem 1.5rem;
}

.section-header {
  margin: 0 0 1rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.subsection-header {
  margin: 0.75rem 0 0.5rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.empty-state {
  text-align: center;
  padding: 2rem;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.empty-state p {
  margin: 0;
}

.mono {
  font-family: var(--font-mono);
  font-size: 0.8125rem;
}

/* Scheduler sessions table */
.table-wrapper {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
}

.data-table th {
  text-align: left;
  padding: 0.5rem 0.75rem;
  color: var(--text-tertiary);
  font-weight: 500;
  text-transform: uppercase;
  font-size: 0.6875rem;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-subtle);
}

.data-table td {
  padding: 0.6rem 0.75rem;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.data-table tbody tr:last-child td {
  border-bottom: none;
}

.data-table tbody tr:hover {
  background: var(--bg-tertiary);
}

.state-badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.state-badge.queued {
  background: rgba(234, 179, 8, 0.15);
  color: #eab308;
}

.state-badge.running {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.state-badge.stopped {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

/* Rotation session cards */
.rotation-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 0.75rem;
}

.rotation-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 0.75rem 1rem;
}

.rotation-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.execution-id {
  font-size: 0.75rem;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 180px;
}

.badge {
  display: inline-block;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  background: var(--bg-secondary);
  color: var(--text-tertiary);
}

.badge.claude { background: rgba(139, 92, 246, 0.15); color: var(--accent-violet); }
.badge.opencode { background: rgba(34, 197, 94, 0.15); color: var(--accent-emerald); }
.badge.gemini { background: rgba(6, 182, 212, 0.15); color: var(--accent-cyan); }
.badge.codex { background: rgba(234, 179, 8, 0.15); color: var(--accent-amber); }

.rotation-card-body {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.rotation-field {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.field-label {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

/* Evaluator grid */
.evaluator-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
}

.evaluator-stat {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.evaluator-states {
  width: 100%;
}

.eval-state-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.35rem 0;
  border-bottom: 1px solid var(--border-subtle);
}

.eval-state-row:last-child {
  border-bottom: none;
}
</style>
