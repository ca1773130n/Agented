<script setup lang="ts">
import { computed, inject } from 'vue'
import { Handle, Position } from '@vue-flow/core'

interface AssignmentItem {
  type: string
  name: string
  id: string
}

interface AgentNodeData {
  label: string
  agentId: string
  role: string
  color: string
  tier?: 'leader' | 'senior' | 'member'
  assignments: AssignmentItem[]
}

const props = defineProps<{
  id: string
  data: AgentNodeData
}>()

const navigateToAgent = inject<(agentId: string) => void>('navigateToAgent', () => {})
const navigateToAssignment = inject<(type: string, name: string, id: string) => void>('navigateToAssignment', () => {})

function onAgentNameClick() {
  navigateToAgent(props.data.agentId)
}

function onPillClick(assignment: AssignmentItem) {
  navigateToAssignment(assignment.type, assignment.name, assignment.id)
}

const initials = computed(() => {
  return (props.data.label || '?').charAt(0).toUpperCase()
})

const displayAssignments = computed(() => {
  const all = props.data.assignments || []
  if (all.length <= 4) return { visible: all, overflow: 0 }
  return { visible: all.slice(0, 3), overflow: all.length - 3 }
})

const tierClass = computed(() => {
  switch (props.data.tier) {
    case 'leader': return 'tier-leader'
    case 'senior': return 'tier-senior'
    default: return ''
  }
})

const tierBorderColor = computed(() => {
  switch (props.data.tier) {
    case 'leader': return '#f59e0b'
    case 'senior': return '#8b5cf6'
    default: return props.data.color
  }
})

const tierBorderGlow = computed(() => {
  switch (props.data.tier) {
    case 'leader': return 'rgba(245, 158, 11, 0.2)'
    case 'senior': return 'rgba(139, 92, 246, 0.15)'
    default: return `${props.data.color}33`
  }
})

function pillClass(type: string): string {
  switch (type) {
    case 'skill':
      return 'pill pill--skill'
    case 'command':
      return 'pill pill--command'
    case 'hook':
      return 'pill pill--hook'
    case 'rule':
      return 'pill pill--rule'
    default:
      return 'pill'
  }
}

function pillPrefix(type: string): string {
  switch (type) {
    case 'skill':
      return 'S'
    case 'command':
      return 'C'
    case 'hook':
      return 'H'
    case 'rule':
      return 'R'
    default:
      return ''
  }
}
</script>

<template>
  <div
    class="agent-node"
    :class="tierClass"
    :style="{
      borderLeftColor: tierBorderColor,
      borderColor: tierBorderGlow,
    }"
  >
    <span v-if="data.tier === 'leader'" class="tier-badge tier-badge--leader">L</span>
    <span v-else-if="data.tier === 'senior'" class="tier-badge tier-badge--senior">S</span>
    <Handle type="target" :position="Position.Top" :style="{ background: data.color, boxShadow: `0 0 6px ${data.color}66` }" />

    <div class="agent-header">
      <div class="agent-avatar" :style="{ backgroundColor: data.color }">
        {{ initials }}
      </div>
      <div class="agent-info">
        <span class="agent-name entity-link" @click.stop="onAgentNameClick">{{ data.label }}</span>
        <span class="agent-role">{{ data.role }}</span>
      </div>
    </div>

    <div v-if="data.assignments && data.assignments.length > 0" class="assignment-pills">
      <span
        v-for="(assignment, idx) in displayAssignments.visible"
        :key="idx"
        :class="pillClass(assignment.type)"
        class="pill-clickable"
        @click.stop="onPillClick(assignment)"
      >
        <span class="pill-prefix">{{ pillPrefix(assignment.type) }}</span>
        {{ assignment.name }}
      </span>
      <span v-if="displayAssignments.overflow > 0" class="pill pill--overflow">
        +{{ displayAssignments.overflow }} more
      </span>
    </div>

    <Handle type="source" :position="Position.Bottom" :style="{ background: data.color, boxShadow: `0 0 6px ${data.color}66` }" />
  </div>
</template>

<style scoped>
.agent-node {
  position: relative;
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-left: 3px solid;
  border-radius: 8px;
  padding: 12px;
  min-width: 180px;
  max-width: 240px;
  font-family: var(--font-family, 'Geist', sans-serif);
}

.tier-leader {
  border-left-color: #f59e0b !important;
  box-shadow: 0 0 8px rgba(245, 158, 11, 0.2), 0 2px 8px rgba(0, 0, 0, 0.3);
}

.tier-senior {
  border-left-color: #8b5cf6 !important;
  box-shadow: 0 0 8px rgba(139, 92, 246, 0.15), 0 2px 8px rgba(0, 0, 0, 0.3);
}

.tier-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  z-index: 1;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
}

.tier-badge--leader {
  background: #f59e0b;
}

.tier-badge--senior {
  background: #8b5cf6;
}

.agent-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.agent-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  font-weight: 700;
  font-size: 14px;
  flex-shrink: 0;
}

.agent-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.agent-name {
  color: var(--text-primary, #f0f0f5);
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-name.entity-link {
  cursor: pointer;
  transition: color 0.15s;
}

.agent-name.entity-link:hover {
  color: var(--accent-cyan, #00d4ff);
  text-decoration: underline;
}

.agent-role {
  color: var(--text-tertiary, #606070);
  font-size: 11px;
  letter-spacing: 0.5px;
}

.assignment-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.pill {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}

.pill-prefix {
  font-weight: 700;
  font-size: 9px;
  opacity: 0.7;
}

.pill--skill {
  background: rgba(34, 211, 238, 0.15);
  color: #22d3ee;
}

.pill--command {
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
}

.pill--hook {
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
}

.pill--rule {
  background: rgba(168, 85, 247, 0.15);
  color: #a855f7;
}

.pill-clickable {
  cursor: pointer;
  transition: opacity 0.15s;
}

.pill-clickable:hover {
  opacity: 0.8;
  text-decoration: underline;
}

.pill--overflow {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-tertiary, #606070);
  font-style: italic;
}
</style>
