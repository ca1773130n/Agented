<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

interface ScriptNodeData {
  label: string
  config: Record<string, unknown>
  executionStatus?: string
}

const props = defineProps<{
  id: string
  data: ScriptNodeData
}>()

const inputHandleStyle = { background: '#22d3ee' }
const outputHandleStyle = { background: '#22d3ee' }

const statusClass = computed(() =>
  props.data.executionStatus ? `status-${props.data.executionStatus}` : '',
)

const language = computed(() => {
  const lang = props.data.config?.language
  return typeof lang === 'string' && lang ? lang : 'shell'
})

const scriptPreview = computed(() => {
  const script = props.data.config?.script
  if (typeof script !== 'string' || !script) return ''
  return script.length > 40 ? script.slice(0, 40) + '...' : script
})

const needsConfig = computed(() => {
  const script = props.data.config?.script
  return !script || (typeof script === 'string' && !script.trim())
})
</script>

<template>
  <div :class="['workflow-node', 'node-script', statusClass]">
    <div v-if="needsConfig" class="validation-dot" title="Required configuration missing"></div>
    <Handle type="target" :position="Position.Top" :style="inputHandleStyle" />
    <div class="node-header">
      <span class="node-icon">&#x1F4C4;</span>
      <span class="node-label">{{ data.label }}</span>
    </div>
    <div class="node-body">
      <span class="script-language">{{ language }}</span>
      <code v-if="scriptPreview" class="script-preview">{{ scriptPreview }}</code>
    </div>
    <Handle type="source" :position="Position.Bottom" :style="outputHandleStyle" />
  </div>
</template>

<style src="./workflow-node.css"></style>
<style scoped>
.node-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.script-language {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: rgba(167, 139, 250, 0.15);
  color: #a78bfa;
  display: inline-block;
  width: fit-content;
}
.script-preview {
  font-family: 'Geist Mono', monospace;
  font-size: 11px;
  color: var(--text-tertiary, #606070);
  word-break: break-all;
}
</style>
