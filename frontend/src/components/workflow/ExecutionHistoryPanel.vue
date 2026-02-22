<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import type { WorkflowExecution, WorkflowNodeExecution } from '../../services/api';
import { workflowExecutionApi } from '../../services/api';

const props = defineProps<{
  workflowId: string;
  visible: boolean;
}>();

const emit = defineEmits<{
  'replay-execution': [executionId: string];
  close: [];
}>();

const executions = ref<WorkflowExecution[]>([]);
const isLoading = ref(false);
const loadError = ref<string | null>(null);

// Drill-down state
const expandedExecutionId = ref<string | null>(null);
const nodeExecutions = ref<WorkflowNodeExecution[]>([]);
const nodeLoading = ref(false);
const expandedNodeId = ref<string | null>(null);

async function loadExecutions(): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await workflowExecutionApi.list(props.workflowId);
    // Sort by most recent first
    executions.value = (data.executions || []).sort((a, b) => {
      const dateA = a.started_at ? new Date(a.started_at).getTime() : 0;
      const dateB = b.started_at ? new Date(b.started_at).getTime() : 0;
      return dateB - dateA;
    });
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : 'Failed to load executions';
  } finally {
    isLoading.value = false;
  }
}

async function toggleExecutionDetail(execId: string): Promise<void> {
  if (expandedExecutionId.value === execId) {
    expandedExecutionId.value = null;
    nodeExecutions.value = [];
    expandedNodeId.value = null;
    return;
  }

  expandedExecutionId.value = execId;
  expandedNodeId.value = null;
  nodeLoading.value = true;
  try {
    const data = await workflowExecutionApi.getNodeExecutions(props.workflowId, execId);
    nodeExecutions.value = data.node_executions || [];
  } catch {
    nodeExecutions.value = [];
  } finally {
    nodeLoading.value = false;
  }
}

function toggleNodeDetail(nodeId: string): void {
  expandedNodeId.value = expandedNodeId.value === nodeId ? null : nodeId;
}

function formatDuration(exec: WorkflowExecution | WorkflowNodeExecution): string {
  const startedAt = exec.started_at;
  const endedAt = exec.ended_at;

  if (!startedAt) return '--';
  if (!endedAt) return 'Running...';

  const start = new Date(startedAt).getTime();
  const end = new Date(endedAt).getTime();
  const diffMs = end - start;

  if (diffMs < 1000) return `${diffMs}ms`;
  const seconds = diffMs / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remSeconds = Math.floor(seconds % 60);
  return `${minutes}m ${remSeconds}s`;
}

function formatTime(dateStr?: string): string {
  if (!dateStr) return '--';
  const d = new Date(dateStr);
  return d.toLocaleString();
}

function truncateId(id: string): string {
  return id.length > 10 ? id.slice(0, 10) + '...' : id;
}

function statusClass(status: string): string {
  switch (status) {
    case 'running': return 'status-running';
    case 'completed': return 'status-completed';
    case 'failed': return 'status-failed';
    case 'cancelled': return 'status-cancelled';
    case 'skipped': return 'status-skipped';
    default: return 'status-pending';
  }
}

function formatJson(jsonStr?: string): string {
  if (!jsonStr) return 'null';
  try {
    return JSON.stringify(JSON.parse(jsonStr), null, 2);
  } catch {
    return jsonStr;
  }
}

// Load on mount and when visibility changes
onMounted(() => {
  if (props.visible) {
    loadExecutions();
  }
});

watch(
  () => props.visible,
  (val) => {
    if (val) {
      loadExecutions();
    }
  }
);
</script>

<template>
  <div v-if="visible" class="history-panel">
    <!-- Header -->
    <div class="history-header">
      <h3>Execution History</h3>
      <div class="header-actions">
        <button class="icon-btn" @click="loadExecutions" title="Refresh" :disabled="isLoading">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M23 4v6h-6M1 20v-6h6"/>
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
        </button>
        <button class="icon-btn" @click="emit('close')" title="Close">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="isLoading && executions.length === 0" class="loading-state">
      <div class="spinner"></div>
      <span>Loading executions...</span>
    </div>

    <!-- Error state -->
    <div v-else-if="loadError" class="error-state">
      <span>{{ loadError }}</span>
      <button class="retry-btn" @click="loadExecutions">Retry</button>
    </div>

    <!-- Empty state -->
    <div v-else-if="executions.length === 0" class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="12" cy="12" r="10"/>
        <path d="M12 6v6l4 2"/>
      </svg>
      <span>No executions yet. Run your workflow from the toolbar.</span>
    </div>

    <!-- Execution list -->
    <div v-else class="execution-list">
      <div
        v-for="exec in executions"
        :key="exec.id"
        class="execution-item"
      >
        <!-- Execution row -->
        <div class="execution-row" @click="toggleExecutionDetail(exec.id)">
          <div class="exec-row-left">
            <span class="exec-status-dot" :class="statusClass(exec.status)"></span>
            <span class="exec-id" :title="exec.id">{{ truncateId(exec.id) }}</span>
            <span class="exec-badge" :class="statusClass(exec.status)">{{ exec.status }}</span>
          </div>
          <div class="exec-row-right">
            <span class="exec-version">v{{ exec.version }}</span>
            <span class="exec-duration">{{ formatDuration(exec) }}</span>
            <span class="exec-expand">{{ expandedExecutionId === exec.id ? '&#x25B2;' : '&#x25BC;' }}</span>
          </div>
        </div>

        <!-- Execution time -->
        <div class="exec-time">{{ formatTime(exec.started_at) }}</div>

        <!-- Replay button -->
        <div class="exec-actions">
          <button class="replay-btn" @click.stop="emit('replay-execution', exec.id)" title="Replay execution">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            Replay
          </button>
        </div>

        <!-- Drill-down: Node executions -->
        <div v-if="expandedExecutionId === exec.id" class="node-detail-section">
          <div v-if="nodeLoading" class="node-loading">
            <div class="spinner-sm"></div>
            Loading nodes...
          </div>
          <div v-else-if="nodeExecutions.length === 0" class="node-empty">
            No node execution data available.
          </div>
          <div v-else class="node-execution-list">
            <div
              v-for="node in nodeExecutions"
              :key="node.id"
              class="node-execution-item"
            >
              <div class="node-exec-row" @click="toggleNodeDetail(node.node_id)">
                <span class="node-exec-id">{{ node.node_id }}</span>
                <span class="node-exec-type">{{ node.node_type }}</span>
                <span class="node-exec-badge" :class="statusClass(node.status)">{{ node.status }}</span>
                <span class="node-exec-duration">{{ formatDuration(node) }}</span>
              </div>

              <!-- Node detail expansion -->
              <div v-if="expandedNodeId === node.node_id" class="node-exec-detail">
                <div v-if="node.input_json" class="detail-section">
                  <div class="detail-label">Input</div>
                  <pre class="json-display">{{ formatJson(node.input_json) }}</pre>
                </div>
                <div v-if="node.output_json" class="detail-section">
                  <div class="detail-label">Output</div>
                  <pre class="json-display">{{ formatJson(node.output_json) }}</pre>
                </div>
                <div v-if="node.error" class="detail-section">
                  <div class="detail-label error-label">Error</div>
                  <pre class="json-display error-display">{{ node.error }}</pre>
                </div>
                <div class="detail-section">
                  <div class="detail-label">Timing</div>
                  <div class="timing-info">
                    <span>Start: {{ formatTime(node.started_at) }}</span>
                    <span>End: {{ formatTime(node.ended_at) }}</span>
                    <span>Duration: {{ formatDuration(node) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.history-panel {
  width: 380px;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-subtle);
}

.history-header h3 {
  font-size: 0.9rem;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary);
}

.header-actions {
  display: flex;
  gap: 6px;
}

.icon-btn {
  width: 28px;
  height: 28px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all 0.15s;
}

.icon-btn:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.icon-btn svg {
  width: 14px;
  height: 14px;
}

.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 20px;
  color: var(--text-tertiary);
  font-size: 0.85rem;
  text-align: center;
}

.empty-state svg {
  width: 32px;
  height: 32px;
  opacity: 0.4;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border-subtle);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-subtle);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  display: inline-block;
}

.error-state {
  color: var(--accent-crimson);
}

.retry-btn {
  padding: 4px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 0.8rem;
}

.retry-btn:hover {
  background: var(--bg-elevated);
}

.execution-list {
  flex: 1;
  overflow-y: auto;
}

.execution-item {
  border-bottom: 1px solid var(--border-subtle);
  padding: 10px 16px;
}

.execution-item:hover {
  background: var(--bg-elevated);
}

.execution-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  margin-bottom: 4px;
}

.exec-row-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.exec-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.exec-id {
  font-size: 0.8rem;
  font-family: var(--font-mono);
  color: var(--text-secondary);
}

.exec-badge {
  font-size: 0.65rem;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 500;
  text-transform: uppercase;
}

.exec-row-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.exec-version {
  font-size: 0.7rem;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.exec-duration {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.exec-expand {
  font-size: 0.6rem;
  color: var(--text-tertiary);
}

.exec-time {
  font-size: 0.7rem;
  color: var(--text-tertiary);
  margin-bottom: 6px;
}

.exec-actions {
  display: flex;
  gap: 4px;
}

.replay-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-secondary);
  font-size: 0.7rem;
  cursor: pointer;
  transition: all 0.15s;
}

.replay-btn:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.replay-btn svg {
  width: 10px;
  height: 10px;
}

/* Status color classes */
.status-pending {
  background: rgba(107, 114, 128, 0.15);
  color: #9ca3af;
}

.exec-status-dot.status-pending { background: #9ca3af; }
.exec-status-dot.status-running { background: #3b82f6; }
.exec-status-dot.status-completed { background: #22c55e; }
.exec-status-dot.status-failed { background: #ef4444; }
.exec-status-dot.status-cancelled { background: #f59e0b; }
.exec-status-dot.status-skipped { background: #6b7280; }

.status-running {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

.status-completed {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.status-failed {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.status-cancelled {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.status-skipped {
  background: rgba(107, 114, 128, 0.1);
  color: #6b7280;
}

/* Node execution drill-down */
.node-detail-section {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border-subtle);
}

.node-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 0;
  color: var(--text-tertiary);
  font-size: 0.8rem;
}

.node-empty {
  padding: 10px 0;
  color: var(--text-tertiary);
  font-size: 0.8rem;
}

.node-execution-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.node-execution-item {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  overflow: hidden;
}

.node-exec-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  cursor: pointer;
  font-size: 0.75rem;
}

.node-exec-row:hover {
  background: var(--bg-tertiary);
}

.node-exec-id {
  font-family: var(--font-mono);
  color: var(--text-primary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-exec-type {
  color: var(--text-tertiary);
  font-size: 0.65rem;
  text-transform: uppercase;
}

.node-exec-badge {
  font-size: 0.6rem;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 500;
  text-transform: uppercase;
}

.node-exec-duration {
  color: var(--text-tertiary);
  white-space: nowrap;
}

.node-exec-detail {
  padding: 8px 10px;
  border-top: 1px solid var(--border-subtle);
  background: var(--bg-tertiary);
}

.detail-section {
  margin-bottom: 8px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.detail-label {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 4px;
  text-transform: uppercase;
}

.error-label {
  color: #ef4444;
}

.json-display {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  padding: 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  color: var(--text-secondary);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}

.error-display {
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.3);
}

.timing-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 0.7rem;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}
</style>
