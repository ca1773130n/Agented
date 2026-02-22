<script setup lang="ts">
import { markRaw, onMounted, nextTick, toRef, watch, computed } from 'vue'
import { VueFlow, useVueFlow, ConnectionMode } from '@vue-flow/core'
import type { Connection, Node, Edge, NodeTypesObject } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import TriggerNode from './nodes/TriggerNode.vue'
import SkillNode from './nodes/SkillNode.vue'
import CommandNode from './nodes/CommandNode.vue'
import WorkflowAgentNode from './nodes/AgentNode.vue'
import ScriptNode from './nodes/ScriptNode.vue'
import ConditionalNode from './nodes/ConditionalNode.vue'
import TransformNode from './nodes/TransformNode.vue'

import { useWorkflowCanvas } from '../../composables/useWorkflowCanvas'
import { useCanvasLayout } from '../../composables/useCanvasLayout'

// ---------------------------------------------------------------------------
// Node type registration (markRaw prevents Vue reactivity proxy issues)
// ---------------------------------------------------------------------------

const nodeTypes: NodeTypesObject = {
  trigger: markRaw(TriggerNode) as NodeTypesObject[string],
  skill: markRaw(SkillNode) as NodeTypesObject[string],
  command: markRaw(CommandNode) as NodeTypesObject[string],
  agent: markRaw(WorkflowAgentNode) as NodeTypesObject[string],
  script: markRaw(ScriptNode) as NodeTypesObject[string],
  conditional: markRaw(ConditionalNode) as NodeTypesObject[string],
  transform: markRaw(TransformNode) as NodeTypesObject[string],
}

// ---------------------------------------------------------------------------
// Props & Emits
// ---------------------------------------------------------------------------

const props = defineProps<{
  workflowId: string
  readOnly?: boolean
}>()

const emit = defineEmits<{
  saved: []
  'dirty-change': [isDirty: boolean]
  'node-selected': [nodeId: string | null]
  'canvas-changed': [nodes: Node[], edges: Edge[]]
}>()

// ---------------------------------------------------------------------------
// Composables
// ---------------------------------------------------------------------------

const workflowIdRef = toRef(props, 'workflowId')

const {
  nodes,
  edges,
  isDirty,
  currentVersion,
  isLoading,
  loadLatestVersion,
  saveVersion,
  addNode,
  removeNode,
  removeEdge: removeWorkflowEdge,
  getPositions,
  updateNodeConfig,
  updateNodeLabel,
} = useWorkflowCanvas(workflowIdRef)

const { layoutNodes } = useCanvasLayout()

const {
  onConnect,
  addEdges,
  screenToFlowCoordinate,
  fitView,
  getSelectedNodes,
  getSelectedEdges,
  getNodes,
  addSelectedNodes,
  removeSelectedNodes,
  zoomIn,
  zoomOut,
} = useVueFlow()

// ---------------------------------------------------------------------------
// Selection state
// ---------------------------------------------------------------------------

const hasSelection = computed(
  () => getSelectedNodes.value.length > 0 || getSelectedEdges.value.length > 0,
)

// ---------------------------------------------------------------------------
// Dirty tracking -> emit
// ---------------------------------------------------------------------------

watch(isDirty, (val) => {
  emit('dirty-change', val)
})

// ---------------------------------------------------------------------------
// Canvas change tracking -> emit for parent validation
// ---------------------------------------------------------------------------

watch(
  [nodes, edges],
  () => {
    emit('canvas-changed', nodes.value, edges.value)
  },
  { deep: true },
)

// ---------------------------------------------------------------------------
// Programmatic node highlighting
// ---------------------------------------------------------------------------

function highlightNodes(nodeIds: string[]) {
  // Deselect all first
  removeSelectedNodes(getNodes.value)
  // Select target nodes
  const idSet = new Set(nodeIds)
  const targetNodes = getNodes.value.filter((n) => idSet.has(n.id))
  if (targetNodes.length > 0) {
    addSelectedNodes(targetNodes)
  }
}

// ---------------------------------------------------------------------------
// Connection handling
// ---------------------------------------------------------------------------

onConnect((params) => {
  const label = params.sourceHandle === 'true' ? 'True'
              : params.sourceHandle === 'false' ? 'False'
              : undefined
  addEdges([
    {
      ...params,
      id: `e-${params.source}-${params.target}${params.sourceHandle ? '-' + params.sourceHandle : ''}`,
      type: 'smoothstep',
      animated: true,
      ...(label ? { label } : {}),
    },
  ])
})

function isValidConnection(connection: Connection): boolean {
  // No self-connections
  if (connection.source === connection.target) return false

  // No duplicate edges
  const exists = edges.value.some(
    (e) =>
      e.source === connection.source &&
      e.target === connection.target &&
      (e.sourceHandle || null) === (connection.sourceHandle || null) &&
      (e.targetHandle || null) === (connection.targetHandle || null),
  )
  if (exists) return false

  return true
}

// ---------------------------------------------------------------------------
// Drag-and-drop from sidebar palette
// ---------------------------------------------------------------------------

function onDragOver(event: DragEvent) {
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'move'
  }
}

function onDrop(event: DragEvent) {
  const nodeType = event.dataTransfer?.getData('application/workflow-node')
  if (!nodeType || props.readOnly) return

  const position = screenToFlowCoordinate({
    x: event.clientX,
    y: event.clientY,
  })

  addNode(nodeType, position)
}

// ---------------------------------------------------------------------------
// Node/pane click
// ---------------------------------------------------------------------------

function onNodeClick(event: { node: { id: string } }) {
  emit('node-selected', event.node.id)
}

function onPaneClick() {
  emit('node-selected', null)
}

// ---------------------------------------------------------------------------
// Keyboard handling: Delete/Backspace
// ---------------------------------------------------------------------------

function onKeyDown(event: KeyboardEvent) {
  if (props.readOnly) return
  if (event.key !== 'Delete' && event.key !== 'Backspace') return

  const tag = (event.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

  const selNodes = getSelectedNodes.value
  const selEdges = getSelectedEdges.value

  if (selNodes.length > 0) {
    for (const node of selNodes) {
      removeNode(node.id)
    }
  }

  if (selEdges.length > 0) {
    for (const edge of selEdges) {
      removeWorkflowEdge(edge.id)
    }
  }
}

// ---------------------------------------------------------------------------
// Auto-layout
// ---------------------------------------------------------------------------

function handleAutoLayout() {
  nodes.value = layoutNodes(nodes.value, edges.value, 'TB')
  nextTick(() => fitView())
}

// ---------------------------------------------------------------------------
// Save
// ---------------------------------------------------------------------------

async function handleSave() {
  await saveVersion()
  emit('saved')
}

// ---------------------------------------------------------------------------
// Delete selected
// ---------------------------------------------------------------------------

function handleDeleteSelected() {
  const selNodes = getSelectedNodes.value
  const selEdges = getSelectedEdges.value

  if (selNodes.length > 0) {
    for (const n of selNodes) {
      removeNode(n.id)
    }
  }

  if (selEdges.length > 0) {
    for (const e of selEdges) {
      removeWorkflowEdge(e.id)
    }
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(async () => {
  await loadLatestVersion()
  await nextTick()

  // If positions are all at origin, auto-layout
  const positions = getPositions()
  const hasPositions =
    Object.keys(positions).length > 0 &&
    Object.values(positions).some((p) => p.x !== 0 || p.y !== 0)
  if (!hasPositions && nodes.value.length > 0) {
    handleAutoLayout()
  } else {
    fitView()
  }

  document.addEventListener('keydown', onKeyDown)
})

import { onUnmounted } from 'vue'
onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown)
})

// ---------------------------------------------------------------------------
// Expose for parent component
// ---------------------------------------------------------------------------

defineExpose({
  save: handleSave,
  autoLayout: handleAutoLayout,
  fitView,
  zoomIn,
  zoomOut,
  addNode,
  removeNode,
  hasSelection,
  deleteSelected: handleDeleteSelected,
  isDirty,
  isLoading,
  currentVersion,
  nodeCount: computed(() => nodes.value.length),
  nodes,
  updateNodeConfig,
  updateNodeLabel,
  highlightNodes,
})
</script>

<template>
  <div class="workflow-canvas-container">
    <div class="canvas-main">
      <div class="canvas-wrapper" @dragover="onDragOver" @drop="onDrop">
        <VueFlow
          v-model:nodes="nodes"
          v-model:edges="edges"
          :node-types="nodeTypes"
          :default-viewport="{ zoom: 0.8 }"
          :snap-to-grid="true"
          :snap-grid="[15, 15] as [number, number]"
          :connection-mode="ConnectionMode.Loose"
          :is-valid-connection="isValidConnection"
          :default-edge-options="{ type: 'smoothstep', animated: true }"
          fit-view-on-init
          class="workflow-flow"
          @node-click="onNodeClick"
          @pane-click="onPaneClick"
        >
          <Background :gap="20" />
          <Controls position="bottom-left" />
          <MiniMap position="bottom-right" />
        </VueFlow>
      </div>
    </div>
  </div>
</template>

<style scoped>
.workflow-canvas-container {
  display: flex;
  height: 100%;
  width: 100%;
}

.canvas-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

.canvas-wrapper {
  flex: 1;
  position: relative;
}

.workflow-flow {
  width: 100%;
  height: 100%;
}

/* Vue Flow dark theme overrides */
.workflow-flow {
  --vf-node-bg: var(--bg-secondary, #12121a);
  --vf-node-color: var(--text-primary, #f0f0f5);
  --vf-node-text: var(--text-primary, #f0f0f5);
  --vf-handle: var(--accent-cyan, #00d4ff);
  --vf-connection-path: var(--accent-cyan, #00d4ff);
  --vf-edge: rgba(255, 255, 255, 0.25);
  --vf-edge-label-bg: var(--bg-secondary, #12121a);
  --vf-edge-label-color: var(--text-secondary, #a0a0b0);
}

.workflow-flow :deep(.vue-flow__background) {
  background: var(--bg-primary, #0a0a10);
}

.workflow-flow :deep(.vue-flow__background pattern circle) {
  fill: rgba(255, 255, 255, 0.06);
}

/* MiniMap dark styling */
.workflow-flow :deep(.vue-flow__minimap) {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 8px;
}

.workflow-flow :deep(.vue-flow__minimap-mask) {
  fill: rgba(0, 212, 255, 0.08);
  stroke: var(--accent-cyan, #00d4ff);
  stroke-width: 1;
}

.workflow-flow :deep(.vue-flow__minimap-node) {
  fill: rgba(255, 255, 255, 0.15);
  stroke: none;
}

/* Controls dark styling */
.workflow-flow :deep(.vue-flow__controls) {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
}

.workflow-flow :deep(.vue-flow__controls-button) {
  background: var(--bg-secondary, #12121a);
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  fill: var(--text-secondary, #a0a0b0);
}

.workflow-flow :deep(.vue-flow__controls-button:hover) {
  background: var(--bg-tertiary, #1a1a24);
  fill: var(--accent-cyan, #00d4ff);
}

/* Edge styling */
.workflow-flow :deep(.vue-flow__edge-path) {
  stroke: rgba(255, 255, 255, 0.25);
  stroke-width: 2;
}

.workflow-flow :deep(.vue-flow__edge.selected .vue-flow__edge-path) {
  stroke: var(--accent-cyan, #00d4ff);
}

.workflow-flow :deep(.vue-flow__edge-textbg) {
  fill: var(--bg-secondary, #12121a);
}

.workflow-flow :deep(.vue-flow__edge-text) {
  fill: var(--text-tertiary, #606070);
  font-size: 11px;
}

/* Connection line styling */
.workflow-flow :deep(.vue-flow__connection-path) {
  stroke: var(--accent-cyan, #00d4ff);
  stroke-width: 2;
  stroke-dasharray: 5;
}
</style>
