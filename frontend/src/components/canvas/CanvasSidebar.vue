<script setup lang="ts">
withDefaults(defineProps<{
  availableAgents: any[]
  availableSuperAgents?: any[]
}>(), {
  availableSuperAgents: () => [],
})

function onDragStart(event: DragEvent, agent: any) {
  if (!event.dataTransfer) return
  event.dataTransfer.setData(
    'application/vueflow',
    JSON.stringify({
      type: 'agent',
      data: {
        label: agent.name,
        agentId: agent.id,
        role: 'member',
        color: '#00d4ff',
        assignments: [],
      },
    }),
  )
  event.dataTransfer.effectAllowed = 'move'
}

function onSuperAgentDragStart(event: DragEvent, sa: any) {
  if (!event.dataTransfer) return
  event.dataTransfer.setData(
    'application/vueflow',
    JSON.stringify({
      type: 'super_agent',
      data: {
        label: sa.name,
        superAgentId: sa.id,
        role: 'lead',
        color: '#a855f7',
        sessionCount: 0,
        documentCount: 0,
        assignments: [],
      },
    }),
  )
  event.dataTransfer.effectAllowed = 'move'
}

function getInitial(name: string): string {
  return (name || '?').charAt(0).toUpperCase()
}
</script>

<template>
  <div class="canvas-sidebar">
    <div class="sidebar-header">Agents</div>
    <p class="sidebar-instruction">Drag agents onto the canvas to build your team</p>
    <div class="sidebar-divider"></div>
    <div v-if="availableAgents.length === 0" class="sidebar-empty">
      All agents are on the canvas
    </div>
    <div
      v-for="agent in availableAgents"
      :key="agent.id"
      class="agent-drag-item"
      draggable="true"
      @dragstart="onDragStart($event, agent)"
    >
      <span class="drag-grip">
        <svg width="8" height="14" viewBox="0 0 8 14" fill="none">
          <circle cx="2" cy="2" r="1.2" fill="currentColor" />
          <circle cx="6" cy="2" r="1.2" fill="currentColor" />
          <circle cx="2" cy="7" r="1.2" fill="currentColor" />
          <circle cx="6" cy="7" r="1.2" fill="currentColor" />
          <circle cx="2" cy="12" r="1.2" fill="currentColor" />
          <circle cx="6" cy="12" r="1.2" fill="currentColor" />
        </svg>
      </span>
      <span class="agent-avatar-small" :style="{ backgroundColor: agent.color || '#6366f1' }">
        {{ getInitial(agent.name) }}
      </span>
      <span class="agent-name">{{ agent.name }}</span>
    </div>

    <!-- SuperAgents section -->
    <div class="sidebar-divider sa-divider"></div>
    <div class="sidebar-header sa-header">SuperAgents</div>
    <div v-if="availableSuperAgents.length === 0" class="sidebar-empty">
      No SuperAgents available
    </div>
    <div
      v-for="sa in availableSuperAgents"
      :key="sa.id"
      class="agent-drag-item sa-drag-item"
      draggable="true"
      @dragstart="onSuperAgentDragStart($event, sa)"
    >
      <span class="drag-grip">
        <svg width="8" height="14" viewBox="0 0 8 14" fill="none">
          <circle cx="2" cy="2" r="1.2" fill="currentColor" />
          <circle cx="6" cy="2" r="1.2" fill="currentColor" />
          <circle cx="2" cy="7" r="1.2" fill="currentColor" />
          <circle cx="6" cy="7" r="1.2" fill="currentColor" />
          <circle cx="2" cy="12" r="1.2" fill="currentColor" />
          <circle cx="6" cy="12" r="1.2" fill="currentColor" />
        </svg>
      </span>
      <span class="agent-avatar-small sa-avatar" :style="{ backgroundColor: '#a855f7' }">
        SA
      </span>
      <span class="agent-name">{{ sa.name }}</span>
    </div>
  </div>
</template>

<style scoped>
.canvas-sidebar {
  width: 240px;
  background: var(--bg-secondary, #12121a);
  border-right: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  padding: 16px;
  overflow-y: auto;
  flex-shrink: 0;
}

.sidebar-header {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #f0f0f5);
  margin-bottom: 8px;
}

.sidebar-instruction {
  font-size: 11px;
  color: var(--text-tertiary, #606070);
  margin: 0 0 12px 0;
  line-height: 1.4;
}

.sidebar-divider {
  height: 1px;
  background: var(--border-subtle, rgba(255, 255, 255, 0.06));
  margin-bottom: 12px;
}

.sa-divider {
  margin-top: 16px;
}

.sa-header {
  color: #a855f7;
}

.sidebar-empty {
  font-size: 12px;
  color: var(--text-tertiary, #606070);
  text-align: center;
  padding: 24px 8px;
}

.agent-drag-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: grab;
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  margin-bottom: 6px;
  transition: background 0.15s, border-color 0.15s;
}

.agent-drag-item:hover {
  background: var(--bg-tertiary, #1a1a24);
  border-color: var(--accent-cyan, #00d4ff);
}

.sa-drag-item:hover {
  border-color: #a855f7;
}

.agent-drag-item:active {
  cursor: grabbing;
}

.drag-grip {
  color: var(--text-tertiary, #606070);
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.agent-avatar-small {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  font-weight: 700;
  font-size: 11px;
  flex-shrink: 0;
}

.sa-avatar {
  font-size: 9px;
  letter-spacing: 0.3px;
}

.agent-name {
  font-size: 12px;
  color: var(--text-primary, #f0f0f5);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
</style>
