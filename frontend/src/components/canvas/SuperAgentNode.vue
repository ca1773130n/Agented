<script setup lang="ts">
import { computed, inject } from 'vue'
import { Handle, Position } from '@vue-flow/core'

interface AssignmentItem {
  type: string
  name: string
  id: string
}

export interface SuperAgentNodeData {
  label: string
  superAgentId: string
  role: string
  color: string
  sessionCount: number
  documentCount: number
  assignments: AssignmentItem[]
}

const props = defineProps<{
  id: string
  data: SuperAgentNodeData
}>()

const navigateToAgent = inject<(agentId: string) => void>('navigateToAgent', () => {})

function onNameClick() {
  navigateToAgent(props.data.superAgentId)
}

const initials = computed(() => {
  return (props.data.label || '?').charAt(0).toUpperCase()
})

const displayAssignments = computed(() => {
  const all = props.data.assignments || []
  if (all.length <= 4) return { visible: all, overflow: 0 }
  return { visible: all.slice(0, 3), overflow: all.length - 3 }
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
  <div class="sa-node">
    <Handle
      type="target"
      :position="Position.Top"
      :style="{ background: '#a855f7', boxShadow: '0 0 6px rgba(168, 85, 247, 0.4)' }"
    />

    <div class="sa-header">
      <div class="sa-avatar-wrapper">
        <div class="sa-avatar">
          {{ initials }}
        </div>
        <span class="sa-badge">SA</span>
      </div>
      <div class="sa-info">
        <span class="sa-name entity-link" @click.stop="onNameClick">{{ data.label }}</span>
        <span class="sa-role">{{ data.role }}</span>
      </div>
    </div>

    <div class="sa-meta">
      <span class="sa-meta-item" :title="`${data.sessionCount} session(s)`">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        {{ data.sessionCount }}
      </span>
      <span class="sa-meta-item" :title="`${data.documentCount} document(s)`">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
        {{ data.documentCount }}
      </span>
    </div>

    <div v-if="data.assignments && data.assignments.length > 0" class="assignment-pills">
      <span
        v-for="(assignment, idx) in displayAssignments.visible"
        :key="idx"
        :class="pillClass(assignment.type)"
      >
        <span class="pill-prefix">{{ pillPrefix(assignment.type) }}</span>
        {{ assignment.name }}
      </span>
      <span v-if="displayAssignments.overflow > 0" class="pill pill--overflow">
        +{{ displayAssignments.overflow }} more
      </span>
    </div>

    <Handle
      type="source"
      :position="Position.Bottom"
      :style="{ background: '#a855f7', boxShadow: '0 0 6px rgba(168, 85, 247, 0.4)' }"
    />
  </div>
</template>

<style scoped>
.sa-node {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-left: 3px solid transparent;
  border-image: linear-gradient(to bottom, #a855f7, #06b6d4) 1;
  border-image-slice: 0 0 0 1;
  border-radius: 8px;
  padding: 12px;
  min-width: 180px;
  max-width: 240px;
  font-family: var(--font-family, 'Geist', sans-serif);
  position: relative;
}

/* Fix border-image clipping on rounded corners */
.sa-node::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: linear-gradient(to bottom, #a855f7, #06b6d4);
  border-radius: 8px 0 0 8px;
}

.sa-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.sa-avatar-wrapper {
  position: relative;
  flex-shrink: 0;
}

.sa-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  font-weight: 700;
  font-size: 14px;
  background: linear-gradient(135deg, #a855f7, #7c3aed);
}

.sa-badge {
  position: absolute;
  bottom: -2px;
  right: -4px;
  background: #a855f7;
  color: #ffffff;
  font-size: 8px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 8px;
  line-height: 1.2;
  letter-spacing: 0.3px;
}

.sa-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.sa-name {
  color: var(--text-primary, #f0f0f5);
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sa-name.entity-link {
  cursor: pointer;
  transition: color 0.15s;
}

.sa-name.entity-link:hover {
  color: #a855f7;
  text-decoration: underline;
}

.sa-role {
  color: var(--text-tertiary, #606070);
  font-size: 11px;
  letter-spacing: 0.5px;
}

.sa-meta {
  display: flex;
  gap: 12px;
  margin-bottom: 6px;
}

.sa-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-tertiary, #606070);
}

.sa-meta-item svg {
  opacity: 0.7;
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

.pill--overflow {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-tertiary, #606070);
  font-style: italic;
}
</style>
