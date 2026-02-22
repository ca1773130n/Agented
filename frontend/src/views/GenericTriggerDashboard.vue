<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { AuditRecord, Trigger, Execution } from '../services/api';
import { auditApi, triggerApi, executionApi, ApiError } from '../services/api';
import ExecutionLogViewer from '../components/triggers/ExecutionLogViewer.vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const props = defineProps<{
  triggerId?: string;
}>();

const route = useRoute();
const router = useRouter();
const triggerId = computed(() => (route.params.triggerId as string) || props.triggerId || '');

const showToast = useToast();

const trigger = ref<Trigger | null>(null);
const recentAudits = ref<AuditRecord[]>([]);
const recentExecutions = ref<Execution[]>([]);
const runningExecution = ref<Execution | null>(null);
const isRunning = ref(false);
const showLiveLog = ref(false);
const currentExecutionId = ref<string | null>(null);
let statusPollInterval: number | null = null;

useWebMcpTool({
  name: 'hive_trigger_dashboard_get_state',
  description: 'Returns the current state of the GenericTriggerDashboard',
  page: 'GenericTriggerDashboard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'GenericTriggerDashboard',
        triggerId: triggerId.value,
        triggerName: trigger.value?.name ?? null,
        isRunning: isRunning.value,
        recentAuditsCount: recentAudits.value.length,
        recentExecutionsCount: recentExecutions.value.length,
        hasRunningExecution: !!runningExecution.value,
        showLiveLog: showLiveLog.value,
      }),
    }],
  }),
  deps: [trigger, isRunning, recentAudits, recentExecutions, runningExecution, showLiveLog],
});

async function loadData() {
  const [botRes, historyRes, execRes] = await Promise.all([
    triggerApi.get(triggerId.value),
    auditApi.getHistory({ trigger_id: triggerId.value, limit: 5 }),
    executionApi.listForBot(triggerId.value, { limit: 5 }),
  ]);
  trigger.value = botRes;
  recentAudits.value = historyRes.audits || [];
  recentExecutions.value = execRes.executions || [];
  runningExecution.value = execRes.running_execution;

  // If there's a running execution, show the live log
  if (runningExecution.value) {
    currentExecutionId.value = runningExecution.value.execution_id;
    showLiveLog.value = true;
    startStatusPolling();
  }
  return trigger.value;
}

function startStatusPolling() {
  if (statusPollInterval) return;
  statusPollInterval = window.setInterval(async () => {
    try {
      const result = await executionApi.getRunning(triggerId.value);
      if (!result.running) {
        // Execution completed
        stopStatusPolling();
        runningExecution.value = null;
        loadData(); // Refresh to get updated history
      }
    } catch {
      // Ignore polling errors
    }
  }, 5000);
}

function stopStatusPolling() {
  if (statusPollInterval) {
    clearInterval(statusPollInterval);
    statusPollInterval = null;
  }
}

async function runTrigger() {
  if (!trigger.value || isRunning.value) return;
  isRunning.value = true;
  try {
    const result = await triggerApi.run(triggerId.value);
    showToast(`${trigger.value.name} started`, 'success');

    // Show live log for the new execution
    if (result.execution_id) {
      currentExecutionId.value = result.execution_id;
      showLiveLog.value = true;
      startStatusPolling();
    }

    // Refresh data to get the running execution
    setTimeout(loadData, 1000);
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to run trigger';
    showToast(message, 'error');
  } finally {
    isRunning.value = false;
  }
}

function onExecutionComplete(status: string) {
  showToast(`Execution ${status}`, status === 'success' ? 'success' : 'error');
  stopStatusPolling();
  runningExecution.value = null;
  loadData();
}

function closeLiveLog() {
  showLiveLog.value = false;
}

function viewExecutionLogs(execution: Execution) {
  currentExecutionId.value = execution.execution_id;
  showLiveLog.value = true;
}

function formatDuration(ms?: number): string {
  if (!ms) return '-';
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`;
  }
  return `${seconds}s`;
}

onUnmounted(() => {
  stopStatusPolling();
});

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function getExecutionStatusClass(status?: string): string {
  switch (status) {
    case 'running': return 'status-running';
    case 'success': return 'status-success';
    case 'failed': return 'status-failed';
    default: return 'status-idle';
  }
}


</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="trigger">
    <template #default="{ reload: _reload }">
  <div class="trigger-dashboard">
    <AppBreadcrumb :items="[{ label: 'Dashboards', action: () => router.push({ name: 'dashboards' }) }, { label: trigger?.name || 'Trigger Dashboard' }]" />

    <template v-if="trigger">
      <!-- Trigger Status Card -->
      <div class="status-card">
        <div class="status-card-header">
          <div class="trigger-icon-lg">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="4" y="4" width="16" height="16" rx="2"/>
              <circle cx="9" cy="10" r="1.5" fill="currentColor"/>
              <circle cx="15" cy="10" r="1.5" fill="currentColor"/>
              <path d="M9 15h6"/>
              <path d="M12 2v2M12 20v2M2 12h2M20 12h2"/>
            </svg>
          </div>
          <div class="status-info">
            <h2>{{ trigger.name }}</h2>
            <div class="status-meta">
              <span class="meta-pill" :class="trigger.enabled ? 'enabled' : 'disabled'">
                {{ trigger.enabled ? 'Enabled' : 'Disabled' }}
              </span>
              <span class="meta-pill backend">{{ trigger.backend_type }}</span>
              <span class="meta-pill" :class="getExecutionStatusClass(trigger.execution_status?.status)">
                {{ trigger.execution_status?.status || 'idle' }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Quick Actions -->
      <div class="actions-row">
        <button class="action-btn primary" @click="runTrigger" :disabled="isRunning || !trigger.enabled || !!runningExecution">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="5,3 19,12 5,21"/>
          </svg>
          {{ runningExecution ? 'Running...' : (isRunning ? 'Starting...' : 'Run Trigger') }}
        </button>
        <button class="action-btn secondary" @click="router.push({ name: 'execution-history' })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>
          </svg>
          Execution History
        </button>
        <button class="action-btn secondary" @click="router.push({ name: 'trigger-history', params: { triggerId } })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12,6 12,12 16,14"/>
          </svg>
          Audit History
        </button>
      </div>

      <!-- Live Execution Panel -->
      <div v-if="showLiveLog && currentExecutionId" class="card execution-card">
        <div class="card-header">
          <div class="header-with-status">
            <h3>
              <span class="live-indicator" v-if="runningExecution"></span>
              {{ runningExecution ? 'Live Execution' : 'Execution Logs' }}
            </h3>
            <span class="execution-id-badge">{{ currentExecutionId }}</span>
          </div>
          <button class="btn-icon-sm" @click="closeLiveLog" title="Close">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
        <ExecutionLogViewer
          :execution-id="currentExecutionId"
          :is-live="!!runningExecution"
          max-height="400px"
          :show-header="false"
          @complete="onExecutionComplete"
        />
      </div>

      <!-- Recent Executions -->
      <div class="card">
        <div class="card-header">
          <h3>Recent Executions</h3>
          <span class="card-count">{{ recentExecutions.length }} latest</span>
        </div>

        <div v-if="recentExecutions.length === 0" class="empty-state">
          <div class="empty-icon">&#9671;</div>
          <p>No executions yet</p>
          <span>Run the bot to see results here</span>
        </div>

        <div v-else class="table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th>Started</th>
                <th>Duration</th>
                <th>Trigger</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(execution, index) in recentExecutions"
                :key="execution.execution_id"
                :style="{ '--delay': `${index * 20}ms` }"
              >
                <td class="cell-date">{{ formatDate(execution.started_at) }}</td>
                <td class="cell-duration">
                  <span v-if="execution.status === 'running'" class="running-text">
                    <span class="spinner-tiny"></span>
                    Running...
                  </span>
                  <span v-else>{{ formatDuration(execution.duration_ms) }}</span>
                </td>
                <td>
                  <span class="trigger-badge" :class="execution.trigger_type">
                    {{ execution.trigger_type }}
                  </span>
                </td>
                <td>
                  <span class="status-pill-exec" :class="execution.status">
                    <span class="status-dot"></span>
                    {{ execution.status }}
                  </span>
                </td>
                <td class="cell-log">
                  <button class="btn-icon-sm" title="View logs" @click="viewExecutionLogs(execution)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                      <circle cx="12" cy="12" r="3"/>
                    </svg>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Recent Audit Results -->
      <div v-if="recentAudits.length > 0" class="card">
        <div class="card-header">
          <h3>Recent Audit Results</h3>
          <span class="card-count">{{ recentAudits.length }} latest</span>
        </div>

        <div class="table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th>Project</th>
                <th>Date</th>
                <th>Findings</th>
                <th>Status</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(audit, index) in recentAudits"
                :key="audit.audit_id"
                :style="{ '--delay': `${index * 20}ms` }"
              >
                <td class="cell-project">
                  <span class="project-name">{{ audit.project_name || audit.project_path }}</span>
                </td>
                <td class="cell-date">{{ formatDate(audit.audit_date) }}</td>
                <td class="cell-result">
                  <span class="findings-total">{{ audit.total_findings }} findings</span>
                </td>
                <td><span class="status-pill" :class="audit.status">{{ audit.status }}</span></td>
                <td class="cell-log">
                  <button class="btn-icon-sm" title="View details" @click="router.push({ name: 'audit-detail', params: { auditId: audit.audit_id } })">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                      <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>
                    </svg>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Trigger Config Summary -->
      <div class="card">
        <div class="card-header">
          <h3>Configuration</h3>
        </div>
        <div class="config-grid">
          <div class="config-item">
            <span class="config-label">Detection Keyword</span>
            <span class="config-value mono">{{ trigger.detection_keyword }}</span>
          </div>
          <div class="config-item">
            <span class="config-label">Group ID</span>
            <span class="config-value mono">{{ trigger.group_id }}</span>
          </div>
          <div class="config-item">
            <span class="config-label">Project Paths</span>
            <span class="config-value">{{ trigger.path_count || 0 }} configured</span>
          </div>
          <div class="config-item">
            <span class="config-label">Backend</span>
            <span class="config-value">{{ trigger.backend_type }}</span>
          </div>
        </div>
        <div v-if="trigger.paths && trigger.paths.length > 0" class="config-paths">
          <span class="config-label">Registered Paths</span>
          <div class="path-chips">
            <span v-for="p in trigger.paths" :key="p.local_project_path" class="path-chip">
              {{ p.local_project_path }}
            </span>
          </div>
        </div>
      </div>
    </template>
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.trigger-dashboard {
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

/* Status Card */
.status-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 28px;
}

.status-card-header {
  display: flex;
  align-items: center;
  gap: 20px;
}

.trigger-icon-lg {
  width: 56px;
  height: 56px;
  background: linear-gradient(135deg, var(--accent-cyan), var(--accent-violet));
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.trigger-icon-lg svg {
  width: 28px;
  height: 28px;
  color: var(--bg-primary);
}

.status-info h2 {
  font-family: var(--font-mono);
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  margin-bottom: 8px;
}

.status-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.meta-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.meta-pill.enabled {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.meta-pill.disabled {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.meta-pill.backend {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.meta-pill.status-idle {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.meta-pill.status-running {
  background: var(--accent-amber-dim);
  color: var(--accent-amber);
}

.meta-pill.status-success {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.meta-pill.status-failed {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

/* Quick Actions */
.actions-row {
  display: flex;
  gap: 12px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all var(--transition-fast);
}

.action-btn svg {
  width: 18px;
  height: 18px;
}

.action-btn.primary {
  background: linear-gradient(135deg, var(--accent-cyan), var(--accent-violet));
  color: white;
}

.action-btn.primary:hover:not(:disabled) {
  box-shadow: var(--shadow-glow-cyan);
  transform: translateY(-1px);
}

.action-btn.primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.secondary {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.action-btn.secondary:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

/* Card */
.card {
  padding: 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-count {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

/* Table */
.table-wrapper {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th {
  color: var(--text-tertiary);
  font-weight: 500;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 14px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-primary);
}

.data-table td {
  padding: 16px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.data-table tr {
  animation: rowFadeIn 0.3s ease backwards;
  animation-delay: var(--delay, 0ms);
}

@keyframes rowFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.cell-project {
  max-width: 200px;
}

.project-name {
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cell-date {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.cell-prompt {
  max-width: 250px;
}

.prompt-text {
  font-size: 0.8rem;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}

.cell-result {
  font-family: var(--font-mono);
}

.findings-total {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 0.85rem;
}

.cell-log {
  text-align: center;
}

.btn-icon-sm {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  border: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background: var(--bg-tertiary);
  color: var(--accent-cyan);
  transition: all var(--transition-fast);
}

.btn-icon-sm:hover {
  background: var(--accent-cyan-dim);
}

.btn-icon-sm svg {
  width: 16px;
  height: 16px;
}

.status-pill {
  display: inline-block;
  padding: 5px 14px;
  border-radius: 20px;
  font-weight: 600;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.status-pill.pass {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.status-pill.fail {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

/* Config Grid */
.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.config-item {
  padding: 16px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
}

.config-label {
  display: block;
  font-size: 0.7rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

.config-value {
  font-size: 0.9rem;
  color: var(--text-primary);
  font-weight: 500;
}

.config-value.mono {
  font-family: var(--font-mono);
  font-size: 0.85rem;
}

.config-paths {
  margin-top: 16px;
  padding: 16px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
}

.path-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.path-chip {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  padding: 6px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  color: var(--text-secondary);
}

/* Empty & Loading States */

.empty-icon {
  font-size: 2.5rem;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.empty-state span {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

/* Execution Card Styles */
.execution-card {
  border-color: var(--accent-cyan);
}

.header-with-status {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-with-status h3 {
  display: flex;
  align-items: center;
  gap: 8px;
}

.live-indicator {
  width: 8px;
  height: 8px;
  background: var(--accent-emerald);
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.9); }
}

.execution-id-badge {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  padding: 4px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  color: var(--text-muted);
}

.cell-duration {
  font-family: var(--font-mono);
  font-size: 0.8rem;
}

.running-text {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--accent-cyan);
}

.spinner-tiny {
  width: 12px;
  height: 12px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.trigger-badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
}

.trigger-badge.manual {
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}

.trigger-badge.webhook {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.status-pill-exec {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  border-radius: 20px;
  font-weight: 600;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.status-pill-exec.running {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.status-pill-exec.running .status-dot {
  background: var(--accent-cyan);
  animation: pulse 1.5s infinite;
}

.status-pill-exec.success {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.status-pill-exec.success .status-dot {
  background: var(--accent-emerald);
}

.status-pill-exec.failed,
.status-pill-exec.timeout {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.status-pill-exec.failed .status-dot,
.status-pill-exec.timeout .status-dot {
  background: var(--accent-crimson);
}


</style>
