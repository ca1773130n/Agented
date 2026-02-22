<script setup lang="ts">
/**
 * WorkflowSidebar — Draggable node palette for the workflow builder.
 *
 * Nodes are grouped into three categories: Entry Points, Execution, and Logic.
 * Dragging a node fires a dataTransfer with 'application/workflow-node' type
 * matching the WorkflowCanvas.vue onDrop handler.
 */

interface PaletteNode {
  type: string
  label: string
  icon: string
  description: string
}

interface NodeCategory {
  name: string
  nodes: PaletteNode[]
}

const nodeCategories: NodeCategory[] = [
  {
    name: 'Entry Points',
    nodes: [
      {
        type: 'trigger',
        label: 'Trigger',
        icon: '\u26A1',
        description: 'Workflow entry point',
      },
    ],
  },
  {
    name: 'Execution',
    nodes: [
      {
        type: 'skill',
        label: 'Skill',
        icon: '\u2728',
        description: 'Execute a registered skill',
      },
      {
        type: 'command',
        label: 'Command',
        icon: '\u2318',
        description: 'Run a CLI command',
      },
      {
        type: 'agent',
        label: 'Agent',
        icon: '\uD83E\uDD16',
        description: 'Delegate to an AI agent',
      },
      {
        type: 'script',
        label: 'Script',
        icon: '\uD83D\uDCC4',
        description: 'Run a script file',
      },
    ],
  },
  {
    name: 'Logic',
    nodes: [
      {
        type: 'conditional',
        label: 'Conditional',
        icon: '\u25C7',
        description: 'Branch on conditions',
      },
      {
        type: 'transform',
        label: 'Transform',
        icon: '\u21C4',
        description: 'Transform data',
      },
    ],
  },
]

function onDragStart(event: DragEvent, nodeType: string) {
  if (!event.dataTransfer) return
  event.dataTransfer.setData('application/workflow-node', nodeType)
  event.dataTransfer.effectAllowed = 'move'
}
</script>

<template>
  <div class="workflow-sidebar">
    <div class="sidebar-header">Node Palette</div>
    <p class="sidebar-instruction">Drag nodes onto the canvas to build your workflow</p>
    <div class="sidebar-divider"></div>

    <div v-for="category in nodeCategories" :key="category.name" class="node-category">
      <div class="category-label">{{ category.name }}</div>
      <div
        v-for="node in category.nodes"
        :key="node.type"
        class="node-drag-item"
        draggable="true"
        @dragstart="onDragStart($event, node.type)"
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
        <span class="node-icon">{{ node.icon }}</span>
        <div class="node-info">
          <span class="node-name">{{ node.label }}</span>
          <span class="node-desc">{{ node.description }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.workflow-sidebar {
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

.node-category {
  margin-bottom: 16px;
}

.category-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary, #606070);
  margin-bottom: 8px;
}

.node-drag-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: grab;
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  margin-bottom: 6px;
  transition:
    background 0.15s,
    border-color 0.15s;
}

.node-drag-item:hover {
  background: var(--bg-tertiary, #1a1a24);
  border-color: var(--accent-cyan, #00d4ff);
}

.node-drag-item:active {
  cursor: grabbing;
}

.drag-grip {
  color: var(--text-tertiary, #606070);
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.node-icon {
  font-size: 16px;
  flex-shrink: 0;
  width: 24px;
  text-align: center;
}

.node-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.node-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary, #f0f0f5);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-desc {
  font-size: 10px;
  color: var(--text-tertiary, #606070);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
