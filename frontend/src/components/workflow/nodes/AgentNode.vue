<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

interface WorkflowAgentNodeData {
  label: string
  config: Record<string, unknown>
  executionStatus?: string
}

const props = defineProps<{
  id: string
  data: WorkflowAgentNodeData
}>()

const inputHandleStyle = { background: '#22d3ee' }
const outputHandleStyle = { background: '#22d3ee' }

const statusClass = computed(() =>
  props.data.executionStatus ? `status-${props.data.executionStatus}` : '',
)

const agentDisplay = computed(() => {
  const agentName = props.data.config?.agent_name
  if (typeof agentName === 'string' && agentName) return agentName
  const agentId = props.data.config?.agent_id
  return typeof agentId === 'string' && agentId ? agentId : 'Not configured'
})

const needsConfig = computed(() => {
  const id = props.data.config?.agent_id
  return !id || (typeof id === 'string' && !id.trim())
})
</script>

<template>
  <div :class="['workflow-node', 'node-agent', statusClass]">
    <div v-if="needsConfig" class="validation-dot" title="Required configuration missing"></div>
    <Handle type="target" :position="Position.Top" :style="inputHandleStyle" />
    <div class="node-header">
      <span class="node-icon">&#x1F916;</span>
      <span class="node-label">{{ data.label }}</span>
    </div>
    <div class="node-body">
      <span :class="['agent-display', { unconfigured: agentDisplay === 'Not configured' }]">{{
        agentDisplay
      }}</span>
    </div>
    <Handle type="source" :position="Position.Bottom" :style="outputHandleStyle" />
  </div>
</template>

<style src="./workflow-node.css"></style>
<style scoped>
.agent-display {
  color: #a78bfa;
}
.agent-display.unconfigured {
  color: var(--text-tertiary, #606070);
  font-style: italic;
}
</style>
