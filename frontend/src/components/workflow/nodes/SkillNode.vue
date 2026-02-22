<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

interface SkillNodeData {
  label: string
  config: Record<string, unknown>
  executionStatus?: string
}

const props = defineProps<{
  id: string
  data: SkillNodeData
}>()

const inputHandleStyle = { background: '#6b7280' }
const outputHandleStyle = { background: '#22d3ee' }

const statusClass = computed(() =>
  props.data.executionStatus ? `status-${props.data.executionStatus}` : '',
)

const skillName = computed(() => {
  const name = props.data.config?.skill_name
  return typeof name === 'string' && name ? name : 'Not configured'
})

const needsConfig = computed(() => {
  const name = props.data.config?.skill_name
  return !name || (typeof name === 'string' && !name.trim())
})
</script>

<template>
  <div :class="['workflow-node', 'node-skill', statusClass]">
    <div v-if="needsConfig" class="validation-dot" title="Required configuration missing"></div>
    <Handle type="target" :position="Position.Top" :style="inputHandleStyle" />
    <div class="node-header">
      <span class="node-icon">&#x2728;</span>
      <span class="node-label">{{ data.label }}</span>
    </div>
    <div class="node-body">
      <span :class="['skill-name', { unconfigured: skillName === 'Not configured' }]">{{
        skillName
      }}</span>
    </div>
    <Handle type="source" :position="Position.Bottom" :style="outputHandleStyle" />
  </div>
</template>

<style src="./workflow-node.css"></style>
<style scoped>
.skill-name {
  color: #22d3ee;
}
.skill-name.unconfigured {
  color: var(--text-tertiary, #606070);
  font-style: italic;
}
</style>
