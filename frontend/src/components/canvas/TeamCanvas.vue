<script setup lang="ts">
import { ref, computed, markRaw, onMounted, onUnmounted, nextTick, toRef, provide } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import type { NodeTypesObject, EdgeTypesObject } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import AgentNode from './AgentNode.vue'
import SuperAgentNode from './SuperAgentNode.vue'
import MessageFlowEdge from './MessageFlowEdge.vue'
import AgentDetailPanel from './AgentDetailPanel.vue'
import CanvasSidebar from './CanvasSidebar.vue'
import CanvasToolbar from './CanvasToolbar.vue'
import ValidationPanel from './ValidationPanel.vue'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import { useTeamCanvas } from '../../composables/useTeamCanvas'
import { useCanvasLayout } from '../../composables/useCanvasLayout'
import { useTopologyValidation } from '../../composables/useTopologyValidation'
import type { Team, TeamAgentAssignment, TopologyType } from '../../services/api'
import { teamApi } from '../../services/api'
import ConfirmModal from '../base/ConfirmModal.vue'
import { useToast } from '../../composables/useToast';

const nodeTypes: NodeTypesObject = {
  agent: markRaw(AgentNode) as NodeTypesObject[string],
  super_agent: markRaw(SuperAgentNode) as NodeTypesObject[string],
}

const edgeTypes: EdgeTypesObject = {
  messageFlow: markRaw(MessageFlowEdge) as EdgeTypesObject[string],
}

const props = defineProps<{
  team: Team | null
  members: any[]
  assignments: TeamAgentAssignment[]
  availableAgents: any[]
  availableSuperAgents: any[]
}>()

const emit = defineEmits<{
  'update:topology': [payload: { topology: string | null; topology_config: any }]
  save: [payload: { topology: string | null; topology_config: any; positions: any }]
  'members-changed': []
  'navigate-to-agent': [agentId: string]
  'navigate-to-assignment': [payload: { type: string; name: string; id: string }]
}>()

// Provide navigation functions for AgentNode
provide('navigateToAgent', (agentId: string) => emit('navigate-to-agent', agentId))
provide('navigateToAssignment', (type: string, name: string, id: string) => emit('navigate-to-assignment', { type, name, id }))

const showToast = useToast();

// Confirm clear all state
const showClearAllConfirm = ref(false);

const teamRef = toRef(props, 'team')
const membersRef = toRef(props, 'members')
const assignmentsRef = toRef(props, 'assignments')

const {
  nodes, edges, syncFromTeam, syncToTeam, getPositions, isSyncing,
  buildEdgesFromTopology,
} = useTeamCanvas(
  teamRef,
  membersRef,
  assignmentsRef,
)
const { layoutNodes } = useCanvasLayout()

const savedTopologyRef = computed(() => props.team?.topology || null)

function getTierForNode(nodeId: string): string | undefined {
  const member = props.members.find(
    m => m.agent_id === nodeId || m.super_agent_id === nodeId
  )
  return member?.tier
}

const { isValidConnection: rawIsValidConnection, warnings, inferredTopology } = useTopologyValidation(
  nodes, edges, savedTopologyRef, getTierForNode
)

// Bypass validation for programmatic edge additions (addEdges API calls).
// isValidConnection is only intended for user-initiated drag connections.
let bypassValidation = false
const isValidConnection = (connection: any) => {
  if (bypassValidation) return true
  return rawIsValidConnection(connection)
}

const flowId = computed(() => 'team-canvas-' + (props.team?.id || 'default'))
const { onConnect, addEdges, addNodes, removeNodes, removeEdges, screenToFlowCoordinate, fitView, getSelectedNodes, getSelectedEdges, zoomIn, zoomOut } = useVueFlow(flowId.value)

// Selection state for toolbar
const hasSelection = computed(() =>
  getSelectedNodes.value.length > 0 || getSelectedEdges.value.length > 0
)

// Agent detail panel
const selectedAgentId = ref<string | null>(null)
const selectedAgentMemberId = ref<number | null>(null)

onConnect((params) => {
  addEdges([{ ...params, type: 'messageFlow', animated: true, data: { edge_type: 'messaging' } }])
  nextTick(() => {
    if (!isSyncing.value) {
      const result = syncToTeam()
      emit('update:topology', result)
    }
  })
})

// Edge right-click context menu for edge type selection (PORG-01)
const contextMenu = ref<{ visible: boolean; x: number; y: number; edgeId: string }>({
  visible: false, x: 0, y: 0, edgeId: '',
})

const edgeTypeOptions = [
  { type: 'command' as const, label: 'Command', color: '#00d4ff' },
  { type: 'report' as const, label: 'Report', color: 'rgba(160, 160, 176, 0.6)' },
  { type: 'peer' as const, label: 'Peer', color: '#22c55e' },
  { type: 'messaging' as const, label: 'Messaging', color: 'rgba(168, 85, 247, 0.8)' },
]

function onEdgeContextMenu(event: { event: MouseEvent | TouchEvent; edge: any }) {
  event.event.preventDefault()
  const x = event.event instanceof MouseEvent ? event.event.clientX : event.event.touches?.[0]?.clientX ?? 0
  const y = event.event instanceof MouseEvent ? event.event.clientY : event.event.touches?.[0]?.clientY ?? 0
  contextMenu.value = {
    visible: true,
    x,
    y,
    edgeId: event.edge.id,
  }
}

function setEdgeType(type: 'command' | 'report' | 'peer' | 'messaging') {
  const edge = edges.value.find(e => e.id === contextMenu.value.edgeId)
  if (edge) {
    edge.data = { ...edge.data, edge_type: type }
    edge.animated = type === 'messaging'
  }
  contextMenu.value.visible = false
  nextTick(() => {
    if (!isSyncing.value) {
      const result = syncToTeam()
      emit('update:topology', result)
    }
  })
}

function closeContextMenu() {
  contextMenu.value.visible = false
}

function onDragOver(event: DragEvent) {
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}

async function onDrop(event: DragEvent) {
  const rawData = event.dataTransfer?.getData('application/vueflow')
  if (!rawData || !props.team) return
  const { type, data } = JSON.parse(rawData)
  const position = screenToFlowCoordinate({ x: event.clientX, y: event.clientY })

  if (type === 'super_agent') {
    // Persist as team member with super_agent_id
    try {
      await teamApi.addMember(props.team.id, {
        name: data.label,
        super_agent_id: data.superAgentId,
        role: 'lead',
      })
      const id = data.superAgentId || `super-${Date.now()}`
      addNodes({ id, type, position, data })
      emit('members-changed')
    } catch {
      showToast('Failed to add SuperAgent to team', 'error')
    }
  } else {
    // Existing agent drop logic
    const agentId = data.agentId
    try {
      await teamApi.addMember(props.team.id, {
        name: data.label,
        agent_id: agentId,
        role: 'member',
      })
      const id = agentId || `${type}-${Date.now()}`
      addNodes({ id, type, position, data })
      emit('members-changed')
    } catch {
      showToast('Failed to add agent to team', 'error')
    }
  }
}

// Handle node click to show detail panel
function onNodeClick(event: { node: any }) {
  const node = event.node
  selectedAgentId.value = node.id
  // Find the member id for API calls (support both agent and super_agent members)
  const member = props.members.find(
    m => m.agent_id === node.id || m.super_agent_id === node.id
  )
  selectedAgentMemberId.value = member?.id ?? null
}

function closeDetailPanel() {
  selectedAgentId.value = null
  selectedAgentMemberId.value = null
}

// Handle agent removal from detail panel
async function onRemoveAgent(agentId: string) {
  const member = props.members.find(
    m => m.agent_id === agentId || m.super_agent_id === agentId
  )
  if (!member || !props.team) return
  try {
    await teamApi.removeMember(props.team.id, member.id)
    removeNodes([agentId])
    closeDetailPanel()
    emit('members-changed')
    showToast('Agent removed from team', 'success')
  } catch {
    showToast('Failed to remove agent', 'error')
  }
}

// Handle tier change from detail panel
function onTierChanged(_memberId: number, _tier: string) {
  // Update the local member data and re-sync canvas to reflect tier changes
  emit('members-changed')
}

// Handle Delete/Backspace key for node and edge deletion
function onKeyDown(event: KeyboardEvent) {
  if (event.key !== 'Delete' && event.key !== 'Backspace') return
  // Don't intercept if user is typing in an input
  const tag = (event.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

  const selNodes = getSelectedNodes.value
  const selEdges = getSelectedEdges.value

  if (selNodes.length > 0) {
    // Remove selected nodes (as team members — support both agent and super_agent)
    for (const node of selNodes) {
      const member = props.members.find(
        m => m.agent_id === node.id || m.super_agent_id === node.id
      )
      if (member && props.team) {
        teamApi.removeMember(props.team.id, member.id).catch(() => {})
      }
    }
    removeNodes(selNodes.map(n => n.id))
    emit('members-changed')
  }

  if (selEdges.length > 0) {
    removeEdges(selEdges.map(e => e.id))
    nextTick(() => {
      const result = syncToTeam()
      emit('update:topology', result)
    })
  }
}

onMounted(() => {
  syncFromTeam()

  const loadedEdges = edges.value.slice()

  // Defer edges until nodes have been rendered and measured by VueFlow.
  // Use addEdges() from the VueFlow store API to bypass v-model timing issues.
  if (nodes.value.length > 0 && loadedEdges.length > 0) {
    edges.value = []
    setTimeout(() => {
      bypassValidation = true
      addEdges(loadedEdges)
      bypassValidation = false
      nextTick(() => {
        const positions = getPositions()
        const hasPositions = Object.keys(positions).length > 0 &&
          Object.values(positions).some((p) => p.x !== 0 || p.y !== 0)
        if (!hasPositions && nodes.value.length > 0) {
          handleAutoLayout()
        } else if (nodes.value.length > 0) {
          setTimeout(() => fitView(), 50)
        }
      })
    }, 100)
  } else {
    nextTick(() => {
      const positions = getPositions()
      const hasPositions = Object.keys(positions).length > 0 &&
        Object.values(positions).some((p) => p.x !== 0 || p.y !== 0)
      if (!hasPositions && nodes.value.length > 0) {
        handleAutoLayout()
      } else if (nodes.value.length > 0) {
        setTimeout(() => fitView(), 50)
      }
    })
  }

  document.addEventListener('keydown', onKeyDown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown)
})

function getLayoutDirection(): 'TB' | 'LR' {
  const topo = props.team?.topology || inferredTopology.value
  switch (topo) {
    case 'parallel':
    case 'generator_critic':
      return 'LR'
    case 'sequential':
    case 'coordinator':
    case 'hierarchical':
    case 'human_in_loop':
    default:
      return 'TB'
  }
}

function handleAutoLayout() {
  const topo = props.team?.topology || inferredTopology.value

  // Build tier map for hierarchical layout
  let tierMap: Record<string, 'leader' | 'senior' | 'member'> | undefined
  if (topo === 'hierarchical') {
    tierMap = {}
    for (const member of props.members) {
      const nodeId = member.agent_id || member.super_agent_id
      if (nodeId && member.tier) {
        tierMap[nodeId] = member.tier as 'leader' | 'senior' | 'member'
      }
    }
    // Only use tierMap if it has entries
    if (Object.keys(tierMap).length === 0) tierMap = undefined
  }

  const ranker = topo === 'hierarchical' ? 'tight-tree' : 'network-simplex'
  nodes.value = layoutNodes(nodes.value, edges.value, getLayoutDirection(), ranker, tierMap)
  // Use setTimeout instead of nextTick — Vue Flow needs time to render after DOM update
  nextTick(() => {
    setTimeout(() => fitView(), 100)
  })
}

function handleFitView() {
  fitView()
}

function handleSetTopology(topology: string | null) {
  // Build a minimal config so buildEdgesFromTopology can auto-generate edges
  const currentNodes = nodes.value
  const nodeIds = currentNodes.map((n) => n.id)
  let config: Record<string, any> = {}

  if (topology === 'sequential' || topology === 'human_in_loop') {
    config = { order: nodeIds }
  } else if (topology === 'coordinator') {
    config = { coordinator: nodeIds[0] || null, workers: nodeIds.slice(1) }
  } else if (topology === 'generator_critic' && nodeIds.length >= 2) {
    config = { generator: nodeIds[0], critic: nodeIds[1] }
  } else if (topology === 'hierarchical') {
    config = { lead: nodeIds[0] || null }
  }
  // parallel & composite need no config (no edges generated)

  // Generate edges based on topology type
  const newEdges = buildEdgesFromTopology(
    (topology || null) as TopologyType | null,
    config,
    currentNodes,
  )

  // Replace current edges with topology-generated ones
  removeEdges(edges.value.map((e) => e.id))
  if (newEdges.length > 0) {
    bypassValidation = true
    addEdges(newEdges)
    bypassValidation = false
  }

  // Sync and emit topology change
  nextTick(() => {
    const result = syncToTeam()
    result.topology = (topology || null) as typeof result.topology
    emit('update:topology', result)
    handleAutoLayout()
  })
}

function handleSave() {
  const result = syncToTeam()
  emit('save', { ...result, positions: getPositions() })
}

function handleDeleteSelected() {
  const selNodes = getSelectedNodes.value
  const selEdges = getSelectedEdges.value

  if (selNodes.length > 0) {
    for (const node of selNodes) {
      const member = props.members.find(
        m => m.agent_id === node.id || m.super_agent_id === node.id
      )
      if (member && props.team) {
        teamApi.removeMember(props.team.id, member.id).catch(() => {})
      }
    }
    removeNodes(selNodes.map(n => n.id))
    emit('members-changed')
  }

  if (selEdges.length > 0) {
    removeEdges(selEdges.map(e => e.id))
    nextTick(() => {
      const result = syncToTeam()
      emit('update:topology', result)
    })
  }
}

function handleClearAll() {
  showClearAllConfirm.value = true;
}

function confirmClearAll() {
  showClearAllConfirm.value = false;

  // Remove all members from team via API (support both agent and super_agent)
  for (const node of nodes.value) {
    const member = props.members.find(
      m => m.agent_id === node.id || m.super_agent_id === node.id
    )
    if (member && props.team) {
      teamApi.removeMember(props.team.id, member.id).catch(() => {})
    }
  }

  removeEdges(edges.value.map(e => e.id))
  removeNodes(nodes.value.map(n => n.id))
  emit('members-changed')
  nextTick(() => {
    const result = syncToTeam()
    emit('update:topology', result)
  })
}

// Expose resyncFromTeam for parent to call on mode switch
defineExpose({ resyncFromTeam: syncFromTeam, fitView })
</script>

<template>
  <div class="team-canvas-container">
    <CanvasSidebar :available-agents="availableAgents" :available-super-agents="availableSuperAgents" />
    <div class="canvas-main">
      <CanvasToolbar
        :inferred-topology="inferredTopology"
        :saved-topology="team?.topology || null"
        :has-selection="hasSelection"
        :node-count="nodes.length"
        @auto-layout="handleAutoLayout"
        @fit-view="handleFitView"
        @save="handleSave"
        @delete-selected="handleDeleteSelected"
        @clear-all="handleClearAll"
        @zoom-in="zoomIn"
        @zoom-out="zoomOut"
        @set-topology="handleSetTopology"
      />
      <div class="canvas-wrapper" @dragover="onDragOver" @drop="onDrop">
        <VueFlow
          :id="'team-canvas-' + (team?.id || 'default')"
          v-model:nodes="nodes"
          v-model:edges="edges"
          :node-types="nodeTypes"
          :edge-types="edgeTypes"
          :is-valid-connection="isValidConnection"
          :default-edge-options="{ type: 'messageFlow', animated: true }"
          class="team-flow"
          @node-click="onNodeClick"
          @edge-context-menu="onEdgeContextMenu"
        >
          <Background :gap="20" />
          <Controls position="bottom-left" />
          <MiniMap position="bottom-right" />
        </VueFlow>
      </div>
      <ValidationPanel :warnings="warnings" />
    </div>
    <AgentDetailPanel
      v-if="selectedAgentId"
      :agent-id="selectedAgentId"
      :member-id="selectedAgentMemberId"
      :team-id="team?.id"
      :members="members"
      :assignments="assignments"
      @close="closeDetailPanel"
      @remove="onRemoveAgent"
      @tier-changed="onTierChanged"
    />

    <!-- Edge type context menu -->
    <Teleport to="body">
      <div v-if="contextMenu.visible" class="edge-context-overlay" @click="closeContextMenu">
        <div
          class="edge-context-menu"
          :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
          @click.stop
        >
          <div class="edge-context-title">Edge Type</div>
          <button
            v-for="opt in edgeTypeOptions"
            :key="opt.type"
            class="edge-context-item"
            :style="{ borderLeftColor: opt.color }"
            @click="setEdgeType(opt.type)"
          >
            <span class="edge-context-dot" :style="{ backgroundColor: opt.color }" />
            {{ opt.label }}
          </button>
        </div>
      </div>
    </Teleport>

    <ConfirmModal
      :open="showClearAllConfirm"
      title="Clear Canvas"
      message="Clear all nodes and edges from the canvas?"
      confirm-label="Clear All"
      variant="danger"
      @confirm="confirmClearAll"
      @cancel="showClearAllConfirm = false"
    />
  </div>
</template>

<style scoped>
.team-canvas-container {
  display: flex;
  height: 100%;
  overflow: hidden;
}

.canvas-main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

.canvas-wrapper {
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

.team-flow {
  width: 100%;
  height: 100%;
}

/* Vue Flow dark theme overrides */
.team-flow {
  --vf-node-bg: var(--bg-secondary, #12121a);
  --vf-node-color: var(--text-primary, #f0f0f5);
  --vf-node-text: var(--text-primary, #f0f0f5);
  --vf-handle: var(--accent-cyan, #00d4ff);
  --vf-connection-path: var(--accent-cyan, #00d4ff);
  --vf-edge: rgba(255, 255, 255, 0.25);
  --vf-edge-label-bg: var(--bg-secondary, #12121a);
  --vf-edge-label-color: var(--text-secondary, #a0a0b0);
}

.team-flow :deep(.vue-flow__background) {
  background: var(--bg-primary, #0a0a10);
}

.team-flow :deep(.vue-flow__background pattern circle) {
  fill: rgba(255, 255, 255, 0.06);
}

/* MiniMap dark styling */
.team-flow :deep(.vue-flow__minimap) {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 8px;
}

.team-flow :deep(.vue-flow__minimap-mask) {
  fill: rgba(0, 212, 255, 0.08);
  stroke: var(--accent-cyan, #00d4ff);
  stroke-width: 1;
}

.team-flow :deep(.vue-flow__minimap-node) {
  fill: rgba(255, 255, 255, 0.15);
  stroke: none;
}

/* Controls dark styling */
.team-flow :deep(.vue-flow__controls) {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
}

.team-flow :deep(.vue-flow__controls-button) {
  background: var(--bg-secondary, #12121a);
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  fill: var(--text-secondary, #a0a0b0);
}

.team-flow :deep(.vue-flow__controls-button:hover) {
  background: var(--bg-tertiary, #1a1a24);
  fill: var(--accent-cyan, #00d4ff);
}

/* Edge styling */
.team-flow :deep(.vue-flow__edge-path) {
  stroke: rgba(255, 255, 255, 0.25);
  stroke-width: 2;
}

.team-flow :deep(.vue-flow__edge.selected .vue-flow__edge-path) {
  stroke: var(--accent-cyan, #00d4ff);
}

.team-flow :deep(.vue-flow__edge-textbg) {
  fill: var(--bg-secondary, #12121a);
}

.team-flow :deep(.vue-flow__edge-text) {
  fill: var(--text-tertiary, #606070);
  font-size: 11px;
}

/* Connection line styling */
.team-flow :deep(.vue-flow__connection-path) {
  stroke: var(--accent-cyan, #00d4ff);
  stroke-width: 2;
  stroke-dasharray: 5;
}

/* Edge context menu */
.edge-context-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
}

.edge-context-menu {
  position: fixed;
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  padding: 4px;
  min-width: 140px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
  z-index: 10000;
}

.edge-context-title {
  font-size: 10px;
  color: var(--text-tertiary, #606070);
  padding: 4px 8px 2px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.edge-context-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  border: none;
  border-left: 3px solid transparent;
  background: transparent;
  color: var(--text-primary, #f0f0f5);
  font-size: 12px;
  cursor: pointer;
  border-radius: 4px;
  text-align: left;
}

.edge-context-item:hover {
  background: var(--bg-tertiary, #1a1a24);
}

.edge-context-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>
