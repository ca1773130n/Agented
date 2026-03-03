<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

interface ApprovalGateNodeData {
  label: string
  config: Record<string, unknown>
  executionStatus?: string
}

const props = defineProps<{
  id: string
  data: ApprovalGateNodeData
}>()

const inputHandleStyle = { background: '#6b7280' }

const statusClass = computed(() =>
  props.data.executionStatus ? `status-${props.data.executionStatus}` : '',
)

const timeoutDisplay = computed(() => {
  const seconds = props.data.config?.timeout_seconds
  if (typeof seconds !== 'number' || seconds <= 0) return '30m'
  if (seconds >= 3600) {
    const hours = Math.floor(seconds / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`
  }
  if (seconds >= 60) {
    return `${Math.floor(seconds / 60)}m`
  }
  return `${seconds}s`
})

const approvalStatus = computed(() => {
  const status = props.data.executionStatus
  if (status === 'pending_approval') return 'Pending'
  if (status === 'completed') return 'Approved'
  if (status === 'failed') return 'Rejected'
  return null
})

const statusBadgeClass = computed(() => {
  const status = props.data.executionStatus
  if (status === 'pending_approval') return 'badge-pending'
  if (status === 'completed') return 'badge-approved'
  if (status === 'failed') return 'badge-rejected'
  return ''
})
</script>

<template>
  <div :class="['workflow-node', 'node-approval-gate', statusClass]">
    <Handle type="target" :position="Position.Top" :style="inputHandleStyle" />
    <div class="node-header">
      <span class="node-icon">&#x23F8;</span>
      <span class="node-label">{{ data.label }}</span>
    </div>
    <div class="node-body">
      <div class="approval-info">
        <span class="timeout-display">Timeout: {{ timeoutDisplay }}</span>
      </div>
      <div v-if="approvalStatus" :class="['approval-badge', statusBadgeClass]">
        <span class="status-dot"></span>
        {{ approvalStatus }}
      </div>
    </div>
    <Handle type="source" :position="Position.Bottom" :style="inputHandleStyle" />
  </div>
</template>

<style src="./workflow-node.css"></style>
<style scoped>
.node-icon {
  font-size: 16px;
  color: #f59e0b;
}
.node-approval-gate {
  border-color: rgba(245, 158, 11, 0.4);
}
.approval-info {
  display: flex;
  align-items: center;
  gap: 8px;
}
.timeout-display {
  font-family: 'Geist Mono', monospace;
  font-size: 11px;
  color: #f59e0b;
}
.approval-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 6px;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 8px;
}
.badge-pending {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}
.badge-approved {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}
.badge-rejected {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.node-approval-gate.status-pending_approval {
  border-color: #f59e0b;
  box-shadow: 0 0 8px rgba(245, 158, 11, 0.4);
}
</style>
