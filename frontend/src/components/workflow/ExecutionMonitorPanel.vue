<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  executionId: string | null;
  executionStatus: string;
  nodeStates: Record<string, string>;
  isMonitoring: boolean;
  visible: boolean;
}>();

const emit = defineEmits<{
  cancel: [];
  close: [];
  'view-history': [];
}>();

const statusColor = computed(() => {
  switch (props.executionStatus) {
    case 'running': return '#3b82f6';
    case 'completed': return '#22c55e';
    case 'failed': return '#ef4444';
    case 'cancelled': return '#f59e0b';
    default: return '#6b7280';
  }
});

const statusLabel = computed(() => {
  return props.executionStatus.charAt(0).toUpperCase() + props.executionStatus.slice(1);
});

const nodeEntries = computed(() => {
  return Object.entries(props.nodeStates).map(([id, status]) => ({
    id,
    status,
  }));
});

const completedCount = computed(() => {
  return nodeEntries.value.filter((n) => n.status === 'completed').length;
});

const totalCount = computed(() => {
  return nodeEntries.value.length;
});

const progressPercent = computed(() => {
  if (totalCount.value === 0) return 0;
  return Math.round((completedCount.value / totalCount.value) * 100);
});

function nodeStatusClass(status: string): string {
  switch (status) {
    case 'running': return 'node-running';
    case 'completed': return 'node-completed';
    case 'failed': return 'node-failed';
    case 'skipped': return 'node-skipped';
    default: return 'node-pending';
  }
}

function nodeStatusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function truncateId(id: string): string {
  return id.length > 12 ? id.slice(0, 12) + '...' : id;
}
</script>

<template>
  <div v-if="visible" class="monitor-panel">
    <!-- Header -->
    <div class="monitor-header">
      <div class="header-left">
        <h3>Execution Monitor</h3>
        <span v-if="executionId" class="exec-id-badge" :title="executionId">{{ truncateId(executionId) }}</span>
      </div>
      <button class="close-btn" @click="emit('close')" title="Close">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 6L6 18M6 6l12 12"/>
        </svg>
      </button>
    </div>

    <!-- Status bar -->
    <div class="status-bar">
      <div class="status-indicator" :style="{ background: statusColor }"></div>
      <span class="status-label">{{ statusLabel }}</span>
      <span class="connection-badge" :class="{ live: isMonitoring }">
        {{ isMonitoring ? 'Live' : 'Disconnected' }}
      </span>
    </div>

    <!-- Progress -->
    <div v-if="totalCount > 0" class="progress-section">
      <div class="progress-text">{{ completedCount }}/{{ totalCount }} nodes completed</div>
      <div class="progress-bar-track">
        <div class="progress-bar-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
    </div>

    <!-- Node state list -->
    <div class="node-list">
      <div v-if="nodeEntries.length === 0" class="node-list-empty">
        <span>Waiting for node execution data...</span>
      </div>
      <div
        v-for="entry in nodeEntries"
        :key="entry.id"
        class="node-entry"
        :class="nodeStatusClass(entry.status)"
      >
        <span class="node-id" :title="entry.id">{{ truncateId(entry.id) }}</span>
        <span class="node-status-badge" :class="nodeStatusClass(entry.status)">
          {{ nodeStatusLabel(entry.status) }}
        </span>
      </div>
    </div>

    <!-- Actions -->
    <div class="monitor-actions">
      <button
        v-if="isMonitoring && executionStatus === 'running'"
        class="btn btn-cancel"
        @click="emit('cancel')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="18" height="18" rx="2"/>
        </svg>
        Cancel Execution
      </button>
      <button class="btn btn-history" @click="emit('view-history')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 6v6l4 2"/>
        </svg>
        View History
      </button>
    </div>
  </div>
</template>

<style scoped>
.monitor-panel {
  width: 320px;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-subtle);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.monitor-header h3 {
  font-size: 0.9rem;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary);
}

.exec-id-badge {
  font-size: 0.7rem;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.close-btn {
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

.close-btn:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.close-btn svg {
  width: 14px;
  height: 14px;
}

.status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-subtle);
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.connection-badge {
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(107, 114, 128, 0.2);
  color: #9ca3af;
  font-weight: 500;
}

.connection-badge.live {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.progress-section {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-subtle);
}

.progress-text {
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.progress-bar-track {
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #22c55e);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.node-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.node-list-empty {
  padding: 20px 16px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 0.8rem;
}

.node-entry {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 16px;
  transition: background 0.15s;
}

.node-entry:hover {
  background: var(--bg-elevated);
}

.node-id {
  font-size: 0.8rem;
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

.node-status-badge {
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
  text-transform: capitalize;
}

.node-pending {
  color: #6b7280;
}

.node-pending .node-status-badge,
.node-status-badge.node-pending {
  background: rgba(107, 114, 128, 0.15);
  color: #9ca3af;
}

.node-running .node-id {
  color: #3b82f6;
}

.node-running .node-status-badge,
.node-status-badge.node-running {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
  animation: pulse 1.5s infinite;
}

.node-completed .node-id {
  color: #22c55e;
}

.node-completed .node-status-badge,
.node-status-badge.node-completed {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.node-failed .node-id {
  color: #ef4444;
}

.node-failed .node-status-badge,
.node-status-badge.node-failed {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.node-skipped .node-id {
  color: #6b7280;
  opacity: 0.5;
}

.node-skipped .node-status-badge,
.node-status-badge.node-skipped {
  background: rgba(107, 114, 128, 0.1);
  color: #6b7280;
  opacity: 0.5;
}

.monitor-actions {
  padding: 12px 16px;
  border-top: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
}

.btn svg {
  width: 14px;
  height: 14px;
}

.btn-cancel {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.3);
  color: #ef4444;
}

.btn-cancel:hover {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.5);
}

.btn-history {
  background: var(--bg-tertiary);
  border-color: var(--border-default);
  color: var(--text-secondary);
}

.btn-history:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}
</style>
