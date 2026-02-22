<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

interface TriggerNodeData {
  label: string
  config: Record<string, unknown>
  executionStatus?: string
}

const props = defineProps<{
  id: string
  data: TriggerNodeData
}>()

const handleStyle = { background: '#6b7280' }

const statusClass = computed(() =>
  props.data.executionStatus ? `status-${props.data.executionStatus}` : '',
)

const subtypeBadge = computed(() => {
  const sub = props.data.config?.trigger_subtype
  return typeof sub === 'string' ? sub : 'manual'
})

const triggerName = computed(() => {
  const name = props.data.config?.trigger_name
  return typeof name === 'string' && name ? name : null
})

const needsConfig = computed(() => {
  const sub = props.data.config?.trigger_subtype
  if (sub === 'cron') {
    const expr = props.data.config?.cron_expression
    return !expr || (typeof expr === 'string' && !expr.trim())
  }
  return false // manual trigger has no required fields
})
</script>

<template>
  <div :class="['workflow-node', 'node-trigger', statusClass]">
    <div v-if="needsConfig" class="validation-dot" title="Required configuration missing"></div>
    <div class="node-header">
      <span class="node-icon">&#x26A1;</span>
      <span class="node-label">{{ data.label }}</span>
      <span class="node-badge trigger-badge">{{ subtypeBadge }}</span>
    </div>
    <div class="node-body">
      <span v-if="triggerName" class="trigger-name">{{ triggerName }}</span>
      <span v-else class="node-hint">Entry point</span>
    </div>
    <!-- Trigger nodes: output handle only (no input) -->
    <Handle type="source" :position="Position.Bottom" :style="handleStyle" />
  </div>
</template>

<style src="./workflow-node.css"></style>
<style scoped>
.node-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  white-space: nowrap;
}
.trigger-badge {
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
}
.node-hint {
  font-style: italic;
  opacity: 0.7;
}
.trigger-name {
  color: #fbbf24;
  font-size: 11px;
}
</style>
