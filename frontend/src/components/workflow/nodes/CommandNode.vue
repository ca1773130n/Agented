<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

interface CommandNodeData {
  label: string
  config: Record<string, unknown>
  executionStatus?: string
}

const props = defineProps<{
  id: string
  data: CommandNodeData
}>()

const inputHandleStyle = { background: '#22d3ee' }
const outputHandleStyle = { background: '#22d3ee' }

const statusClass = computed(() =>
  props.data.executionStatus ? `status-${props.data.executionStatus}` : '',
)

const commandPreview = computed(() => {
  const cmdName = props.data.config?.command_name
  if (typeof cmdName === 'string' && cmdName) return cmdName
  const cmd = props.data.config?.command
  if (typeof cmd !== 'string' || !cmd) return 'Not configured'
  return cmd.length > 40 ? cmd.slice(0, 40) + '...' : cmd
})

const needsConfig = computed(() => {
  const cmd = props.data.config?.command
  return !cmd || (typeof cmd === 'string' && !cmd.trim())
})
</script>

<template>
  <div :class="['workflow-node', 'node-command', statusClass]">
    <div v-if="needsConfig" class="validation-dot" title="Required configuration missing"></div>
    <Handle type="target" :position="Position.Top" :style="inputHandleStyle" />
    <div class="node-header">
      <span class="node-icon">&#x2318;</span>
      <span class="node-label">{{ data.label }}</span>
    </div>
    <div class="node-body">
      <code :class="['command-preview', { unconfigured: commandPreview === 'Not configured' }]">{{
        commandPreview
      }}</code>
    </div>
    <Handle type="source" :position="Position.Bottom" :style="outputHandleStyle" />
  </div>
</template>

<style src="./workflow-node.css"></style>
<style scoped>
.command-preview {
  font-family: 'Geist Mono', monospace;
  font-size: 11px;
  color: #4ade80;
  word-break: break-all;
}
.command-preview.unconfigured {
  color: var(--text-tertiary, #606070);
  font-style: italic;
  font-family: var(--font-family, 'Geist', sans-serif);
}
</style>
