<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

interface TransformNodeData {
  label: string
  config: Record<string, unknown>
  executionStatus?: string
}

const props = defineProps<{
  id: string
  data: TransformNodeData
}>()

const inputHandleStyle = { background: '#6b7280' }
const outputHandleStyle = { background: '#a78bfa' }

const statusClass = computed(() =>
  props.data.executionStatus ? `status-${props.data.executionStatus}` : '',
)

const operation = computed(() => {
  const op = props.data.config?.operation
  return typeof op === 'string' && op ? op : 'Not configured'
})

const needsConfig = computed(() => {
  const op = props.data.config?.operation
  return !op || (typeof op === 'string' && !op.trim())
})
</script>

<template>
  <div :class="['workflow-node', 'node-transform', statusClass]">
    <div v-if="needsConfig" class="validation-dot" title="Required configuration missing"></div>
    <Handle type="target" :position="Position.Top" :style="inputHandleStyle" />
    <div class="node-header">
      <span class="node-icon">&#x21C4;</span>
      <span class="node-label">{{ data.label }}</span>
    </div>
    <div class="node-body">
      <span :class="['operation', { unconfigured: operation === 'Not configured' }]">{{
        operation
      }}</span>
    </div>
    <Handle type="source" :position="Position.Bottom" :style="outputHandleStyle" />
  </div>
</template>

<style src="./workflow-node.css"></style>
<style scoped>
.node-icon {
  color: #a78bfa;
}
.operation {
  font-family: 'Geist Mono', monospace;
  font-size: 11px;
  color: #a78bfa;
}
.operation.unconfigured {
  color: var(--text-tertiary, #606070);
  font-style: italic;
  font-family: var(--font-family, 'Geist', sans-serif);
}
</style>
