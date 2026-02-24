<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import { useRouter } from 'vue-router';
import type { Execution } from '../services/api';
import { executionApi, triggerApi, ApiError } from '../services/api';
import ExecutionLogViewer from '../components/triggers/ExecutionLogViewer.vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import EmptyState from '../components/base/EmptyState.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const props = withDefaults(defineProps<{
  triggerId?: string;
}>(), {
  triggerId: '',
});

const router = useRouter();

const showToast = useToast();

const executions = ref<Execution[]>([]);
const isLoading = ref(true);
const selectedExecution = ref<Execution | null>(null);
const selectedStatus = ref('');
const triggerName = ref('');

const logModalRef = ref<HTMLElement | null>(null);
const logModalOpen = computed(() => !!selectedExecution.value);
useFocusTrap(logModalRef, logModalOpen);

useWebMcpTool({
  name: 'agented_execution_history_get_state',
  description: 'Returns the current state of the Execution History page',
  page: 'ExecutionHistory',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'ExecutionHistory',
        executionsCount: executions.value.length,
        isLoading: isLoading.value,
        selectedStatus: selectedStatus.value,
        triggerId: props.triggerId,
      }),
    }],
  }),
  deps: [executions, isLoading, selectedStatus],
});

const filteredExecutions = computed(() => {
  if (!selectedStatus.value) return executions.value;
  return executions.value.filter(e => e.status === selectedStatus.value);
});

const pageTitle = computed(() => {
  if (props.triggerId && triggerName.value) return `${triggerName.value} Executions`;
  if (props.triggerId) return 'Trigger Executions';
  return 'Execution History';
});

async function loadData() {
  isLoading.value = true;
  try {
    if (props.triggerId) {
      // Load trigger name
      try {
        const trigger = await triggerApi.get(props.triggerId);
        triggerName.value = trigger.name;
      } catch {
        triggerName.value = '';
      }

      const result = await executionApi.listForBot(props.triggerId, { limit: 100 });
      executions.value = result.executions || [];
    } else {
      const result = await executionApi.listAll({ limit: 100 });
      executions.value = result.executions || [];
    }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load execution history';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

watch(() => props.triggerId, loadData);

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
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

function viewLogs(execution: Execution) {
  selectedExecution.value = execution;
}

function closeLogs() {
  selectedExecution.value = null;
}

const RETRYABLE_STATUSES = new Set(['failed', 'timeout', 'cancelled', 'interrupted']);
const retryingId = ref<string | null>(null);

async function handleRetryExecution(execution: Execution) {
  if (retryingId.value) return;
  retryingId.value = execution.execution_id;
  try {
    await triggerApi.run(execution.trigger_id);
    showToast('Execution retry started', 'success');
    await loadData();
  } catch (err: any) {
    showToast(err.message || 'Failed to retry execution', 'error');
  } finally {
    retryingId.value = null;
  }
}

const cancellingId = ref<string | null>(null);

async function handleCancelExecution(executionId: string) {
  if (cancellingId.value) return;
  cancellingId.value = executionId;
  try {
    await executionApi.cancel(executionId);
    showToast('Execution cancelled', 'success');
    await loadData();
  } catch (err: any) {
    showToast(err.message || 'Failed to cancel execution', 'error');
  } finally {
    cancellingId.value = null;
  }
}

function onExecutionComplete(_status: string) {
  // Refresh the list
  loadData();
}

onMounted(loadData);
</script>

<template>
  <div class="execution-history">
    <AppBreadcrumb :items="[{ label: 'Dashboards', action: () => router.push({ name: 'dashboards' }) }, { label: 'Execution History' }]" />

    <PageHeader :title="pageTitle" subtitle="View execution logs and history">
      <template #actions>
        <div class="header-stats">
          <div class="stat-chip">
            <span class="stat-value">{{ executions.length }}</span>
            <span class="stat-label">Total Runs</span>
          </div>
          <div class="stat-chip success">
            <span class="stat-value">{{ executions.filter(e => e.status === 'success').length }}</span>
            <span class="stat-label">Success</span>
          </div>
          <div class="stat-chip failed">
            <span class="stat-value">{{ executions.filter(e => e.status === 'failed' || e.status === 'timeout').length }}</span>
            <span class="stat-label">Failed</span>
          </div>
        </div>
      </template>
    </PageHeader>

    <div class="card">
      <!-- Filter Bar -->
      <div class="filter-bar">
        <div class="filter-group">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <polygon points="22,3 2,3 10,12.46 10,19 14,21 14,12.46"/>
          </svg>
          <label>Filter by Status</label>
          <select v-model="selectedStatus">
            <option value="">All Statuses</option>
            <option value="running">Running</option>
            <option value="success">Success</option>
            <option value="failed">Failed</option>
            <option value="timeout">Timeout</option>
            <option value="cancelled">Cancelled</option>
            <option value="interrupted">Interrupted</option>
          </select>
        </div>
        <div class="filter-info">
          Showing {{ filteredExecutions.length }} of {{ executions.length }} executions
        </div>
      </div>

      <LoadingState v-if="isLoading" message="Loading execution history..." />

      <div v-else class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th v-if="!triggerId">Name</th>
              <th>Started</th>
              <th>Duration</th>
              <th>Source</th>
              <th>Backend</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="filteredExecutions.length === 0">
              <td :colspan="triggerId ? 6 : 7" class="table-empty">
                <EmptyState
                  title="No execution history available"
                  description="Executions will appear here when bots are run"
                />
              </td>
            </tr>
            <tr
              v-for="(execution, index) in filteredExecutions"
              :key="execution.execution_id"
              :style="{ '--delay': `${index * 20}ms` }"
            >
              <td v-if="!triggerId" class="cell-trigger">
                <span class="trigger-name">{{ execution.trigger_name || execution.trigger_id || '-' }}</span>
              </td>
              <td class="cell-date">{{ formatDate(execution.started_at) }}</td>
              <td class="cell-duration">
                <span v-if="execution.status === 'running'" class="running-duration">
                  <span class="spinner-small"></span>
                  Running...
                </span>
                <span v-else>{{ formatDuration(execution.duration_ms) }}</span>
              </td>
              <td class="cell-trigger">
                <span class="trigger-badge" :class="execution.trigger_type">
                  {{ execution.trigger_type }}
                </span>
              </td>
              <td class="cell-backend">
                <span class="backend-badge">{{ execution.backend_type }}</span>
              </td>
              <td>
                <span class="status-pill" :class="execution.status">
                  <span class="status-dot"></span>
                  {{ execution.status }}
                </span>
              </td>
              <td class="cell-actions">
                <button class="btn-icon" @click="viewLogs(execution)" title="View logs">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                </button>
                <button
                  v-if="execution.status === 'running'"
                  class="btn-icon btn-cancel"
                  :disabled="cancellingId === execution.execution_id"
                  @click="handleCancelExecution(execution.execution_id)"
                  title="Cancel execution"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="3" width="18" height="18" rx="2"/>
                  </svg>
                </button>
                <button
                  v-if="RETRYABLE_STATUSES.has(execution.status)"
                  class="btn-icon btn-retry"
                  :disabled="retryingId === execution.execution_id"
                  @click="handleRetryExecution(execution)"
                  title="Retry execution"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M1 4v6h6M23 20v-6h-6"/>
                    <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
                  </svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Log Viewer Modal -->
    <div v-if="selectedExecution" ref="logModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-execution-log" tabindex="-1" @click.self="closeLogs" @keydown.escape="closeLogs">
      <div class="log-modal">
        <div class="modal-header">
          <div class="modal-title">
            <h3 id="modal-title-execution-log">Execution Logs</h3>
            <span class="execution-id">{{ selectedExecution.execution_id }}</span>
          </div>
          <button class="close-btn" @click="closeLogs">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
        <ExecutionLogViewer
          :execution-id="selectedExecution.execution_id"
          :is-live="selectedExecution.status === 'running'"
          max-height="60vh"
          :show-header="true"
          @complete="onExecutionComplete"
          @close="closeLogs"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.execution-history {
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

/* Header Stats (inside PageHeader actions slot) */
.header-stats {
  display: flex;
  gap: 12px;
}

.stat-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 20px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
}

.stat-chip.success {
  border-color: var(--accent-emerald);
}

.stat-chip.success .stat-value {
  color: var(--accent-emerald);
}

.stat-chip.failed {
  border-color: var(--accent-crimson);
}

.stat-chip.failed .stat-value {
  color: var(--accent-crimson);
}

.stat-chip .stat-value {
  font-family: var(--font-mono);
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-chip .stat-label {
  font-size: 0.7rem;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 2px;
}

/* Card */
.card {
  padding: 24px;
}

/* Filter Bar */
.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  margin-bottom: 20px;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.filter-group svg {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
}

.filter-group label {
  font-size: 0.85rem;
  color: var(--text-secondary);
  white-space: nowrap;
}

.filter-group select {
  padding: 10px 16px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 0.875rem;
  background: var(--bg-secondary);
  color: var(--text-primary);
  min-width: 160px;
  cursor: pointer;
  transition: border-color var(--transition-fast);
}

.filter-group select:focus {
  border-color: var(--accent-cyan);
  outline: none;
}

.filter-info {
  font-size: 0.8rem;
  color: var(--text-muted);
}

/* Data Table */
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
  position: sticky;
  top: 0;
}

.data-table td {
  padding: 16px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.data-table tr {
  transition: background var(--transition-fast);
  animation: rowFadeIn 0.3s ease backwards;
  animation-delay: var(--delay, 0ms);
}

@keyframes rowFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.data-table tbody tr:hover {
  background: var(--bg-tertiary);
}

.cell-trigger {
  max-width: 180px;
}

.trigger-name {
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

.cell-duration {
  font-family: var(--font-mono);
  font-size: 0.8rem;
}

.running-duration {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--accent-cyan);
}

.spinner-small {
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

.backend-badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

/* Status Pill */
.status-pill {
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

.status-pill.running {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.status-pill.running .status-dot {
  background: var(--accent-cyan);
  animation: pulse 1.5s infinite;
}

.status-pill.success {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.status-pill.success .status-dot {
  background: var(--accent-emerald);
}

.status-pill.failed, .status-pill.timeout {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.status-pill.failed .status-dot, .status-pill.timeout .status-dot {
  background: var(--accent-crimson);
}

.status-pill.cancelled {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.status-pill.cancelled .status-dot {
  background: #f59e0b;
}

.status-pill.interrupted {
  background: rgba(107, 114, 128, 0.15);
  color: #9ca3af;
}

.status-pill.interrupted .status-dot {
  background: #9ca3af;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Actions */
.cell-actions {
  text-align: center;
}

.btn-icon {
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all var(--transition-fast);
}

.btn-icon:hover {
  background: var(--bg-elevated);
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
}

.btn-icon.btn-cancel {
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.3);
}

.btn-icon.btn-cancel:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.5);
}

.btn-icon.btn-retry {
  color: var(--accent-cyan);
  border-color: rgba(0, 212, 255, 0.3);
}

.btn-icon.btn-retry:hover:not(:disabled) {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
}

.btn-icon.btn-retry:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-icon.btn-cancel:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-icon svg {
  width: 16px;
  height: 16px;
}

/* Empty State */
.table-empty {
  padding: 60px 40px !important;
}

/* Modal */

@keyframes overlayFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.log-modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  width: 90%;
  max-width: 900px;
  max-height: 90vh;
  overflow: hidden;
  animation: modalSlideIn 0.3s ease;
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
}

@keyframes modalSlideIn {
  from { opacity: 0; transform: translateY(-20px) scale(0.95); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.modal-title h3 {
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.execution-id {
  display: block;
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 4px;
  font-family: var(--font-mono);
}

.close-btn {
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition-fast);
  color: var(--text-tertiary);
}

.close-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-color: var(--border-default);
}

.close-btn svg {
  width: 16px;
  height: 16px;
}

@media (max-width: 900px) {
  .header-stats {
    width: 100%;
    justify-content: space-between;
  }

  .filter-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .filter-group select {
    min-width: 100%;
  }
}
</style>
