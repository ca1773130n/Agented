<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

interface ConditionalNodeData {
  label: string
  config: Record<string, unknown>
  executionStatus?: string
}

const props = defineProps<{
  id: string
  data: ConditionalNodeData
}>()

const inputHandleStyle = { background: '#6b7280' }

const statusClass = computed(() =>
  props.data.executionStatus ? `status-${props.data.executionStatus}` : '',
)

const conditionType = computed(() => {
  const ct = props.data.config?.condition_type
  return typeof ct === 'string' && ct ? ct : 'has_text'
})

const needsConfig = computed(() => {
  const ct = props.data.config?.condition_type
  return !ct || (typeof ct === 'string' && !ct.trim())
})
</script>

<template>
  <div :class="['workflow-node', 'node-conditional', statusClass]">
    <div v-if="needsConfig" class="validation-dot" title="Required configuration missing"></div>
    <Handle type="target" :position="Position.Top" :style="inputHandleStyle" />
    <div class="node-header">
      <span class="node-icon">&#x25C7;</span>
      <span class="node-label">{{ data.label }}</span>
    </div>
    <div class="node-body">
      <span class="condition-type">{{ conditionType }}</span>
    </div>
    <div class="branch-labels">
      <span class="branch-label branch-true">true</span>
      <span class="branch-label branch-false">false</span>
    </div>
    <!-- True branch: left-offset output -->
    <Handle
      id="true"
      type="source"
      :position="Position.Bottom"
      :style="{ background: '#22c55e', left: '30%' }"
    />
    <!-- False branch: right-offset output -->
    <Handle
      id="false"
      type="source"
      :position="Position.Bottom"
      :style="{ background: '#ef4444', left: '70%' }"
    />
  </div>
</template>

<style src="./workflow-node.css"></style>
<style scoped>
.node-icon {
  font-size: 16px;
  color: #fbbf24;
}
.condition-type {
  font-family: 'Geist Mono', monospace;
  font-size: 11px;
  color: #fbbf24;
}
.branch-labels {
  display: flex;
  justify-content: space-between;
  padding: 4px 12px 8px;
}
.branch-label {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 6px;
}
.branch-true {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}
.branch-false {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}
</style>
