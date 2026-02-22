<script setup lang="ts">
import { ref, computed, onMounted, nextTick, markRaw, toRef, onUnmounted } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import type { NodeTypesObject, EdgeTypesObject } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import TeamOrgNode from '../projects/TeamOrgNode.vue'
import MessageFlowEdge from './MessageFlowEdge.vue'
import { useOrgCanvas } from '../../composables/useOrgCanvas'
import { useCanvasLayout } from '../../composables/useCanvasLayout'
import { useToast } from '../../composables/useToast'
import { teamApi, projectApi } from '../../services/api'
import type { CanvasEdgeType, Team } from '../../services/api'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

const nodeTypes: NodeTypesObject = {
  team: markRaw(TeamOrgNode) as NodeTypesObject[string],
}

const edgeTypes: EdgeTypesObject = {
  messageFlow: markRaw(MessageFlowEdge) as EdgeTypesObject[string],
}

const props = defineProps<{
  projectId: string
  teams: { id: string; name: string; color: string; members?: any[] }[]
}>()

const emit = defineEmits<{
  'drill-down': [teamId: string]
  'team-added': [teamId: string]
  'team-removed': [teamId: string]
  save: []
}>()

const showToast = useToast()

const projectIdRef = toRef(props, 'projectId')
const {
  nodes,
  edges,
  buildNodes,
  loadEdges,
  saveEdges,
  savePositions,
  loadPositions,
} = useOrgCanvas(projectIdRef)

const { layoutNodes } = useCanvasLayout()
const { onConnect, addEdges, fitView, onNodesInitialized } = useVueFlow({
  id: `org-canvas-${props.projectId}`,
})

// Context menu state
const contextMenu = ref<{ visible: boolean; x: number; y: number; edgeId: string }>({
  visible: false,
  x: 0,
  y: 0,
  edgeId: '',
})

// Add team dropdown state
const showAddTeamDropdown = ref(false)
const availableTeams = ref<Team[]>([])
const isLoadingTeams = ref(false)

// Edge type options
const edgeTypeOptions: { type: CanvasEdgeType; label: string; desc: string; color: string }[] = [
  { type: 'command', label: 'Command', desc: 'Leader sends task', color: '#00d4ff' },
  { type: 'report', label: 'Report', desc: 'Member reports result', color: 'rgba(160,160,176,0.6)' },
  { type: 'peer', label: 'Peer', desc: 'Bidirectional collaboration', color: '#22c55e' },
  { type: 'inter_team', label: 'Inter-Team', desc: 'Cross-team connection', color: '#f59e0b' },
]

onConnect((params) => {
  addEdges([{
    ...params,
    type: 'messageFlow',
    animated: true,
    data: { edge_type: 'inter_team' as CanvasEdgeType },
  }])
})

function onNodeClick(event: { node: any }) {
  emit('drill-down', event.node.data.teamId)
}

function onEdgeContextMenu(event: { event: MouseEvent | TouchEvent; edge: any }) {
  if (event.event instanceof MouseEvent) {
    event.event.preventDefault()
    contextMenu.value = {
      visible: true,
      x: event.event.clientX,
      y: event.event.clientY,
      edgeId: event.edge.id,
    }
  }
}

function setEdgeType(type: CanvasEdgeType) {
  const edge = edges.value.find((e) => e.id === contextMenu.value.edgeId)
  if (edge) {
    edge.data = { ...edge.data, edge_type: type }
    edge.animated = type === 'inter_team' || type === 'command'
  }
  contextMenu.value.visible = false
}

function closeContextMenu() {
  contextMenu.value.visible = false
}

function handleAutoLayout() {
  nodes.value = layoutNodes(nodes.value, edges.value, 'TB')
  nextTick(() => fitView())
}

function handleFitView() {
  fitView()
}

async function handleSave() {
  try {
    await saveEdges()
    await savePositions()
    showToast('Team topology saved', 'success')
    emit('save')
  } catch {
    showToast('Failed to save team topology', 'error')
  }
}

async function loadAvailableTeams() {
  isLoadingTeams.value = true
  try {
    const resp = await teamApi.list()
    const currentTeamIds = new Set(props.teams.map((t) => t.id))
    availableTeams.value = (resp.teams || []).filter((t) => !currentTeamIds.has(t.id))
  } catch {
    availableTeams.value = []
  } finally {
    isLoadingTeams.value = false
  }
}

async function toggleAddTeamDropdown() {
  if (!showAddTeamDropdown.value) {
    await loadAvailableTeams()
  }
  showAddTeamDropdown.value = !showAddTeamDropdown.value
}

async function addTeamToProject(teamId: string) {
  try {
    await projectApi.assignTeam(props.projectId, teamId)
    showToast('Team added to project', 'success')
    showAddTeamDropdown.value = false
    emit('team-added', teamId)
  } catch {
    showToast('Failed to add team', 'error')
  }
}

async function removeTeamFromProject(teamId: string) {
  try {
    await projectApi.unassignTeam(props.projectId, teamId)
    // Remove the node from canvas
    nodes.value = nodes.value.filter((n) => n.id !== teamId)
    // Remove any connected edges
    edges.value = edges.value.filter((e) => e.source !== teamId && e.target !== teamId)
    showToast('Team removed from project', 'success')
    emit('team-removed', teamId)
  } catch {
    showToast('Failed to remove team', 'error')
  }
}

// Close dropdowns on outside click
function handleDocumentClick(e: Event) {
  const target = e.target as HTMLElement
  if (!target.closest('.add-team-dropdown-container')) {
    showAddTeamDropdown.value = false
  }
  if (contextMenu.value.visible && !target.closest('.edge-context-menu')) {
    contextMenu.value.visible = false
  }
}

// Defer edges + layout until VueFlow has fully initialized all nodes
let nodesInit = false
let pendingInit: (() => void) | null = null

onNodesInitialized(() => {
  nodesInit = true
  if (pendingInit) {
    pendingInit()
    pendingInit = null
  }
})

onMounted(async () => {
  document.addEventListener('click', handleDocumentClick)
  buildNodes(props.teams)

  // Load edges and positions (API calls may complete after onNodesInitialized fires)
  const [, hasPositions] = await Promise.all([loadEdges(), loadPositions()])
  const loadedEdges = edges.value.slice()

  const applyEdgesAndLayout = () => {
    if (loadedEdges.length > 0) {
      edges.value = loadedEdges
    }
    if (!hasPositions) {
      handleAutoLayout()
    } else {
      nextTick(() => fitView())
    }
  }

  if (nodes.value.length > 0 && loadedEdges.length > 0) {
    edges.value = []
    if (nodesInit) {
      // Nodes already initialized (fast path), apply immediately
      applyEdgesAndLayout()
    } else {
      // Wait for nodes to initialize
      pendingInit = applyEdgesAndLayout
    }
  } else {
    if (!hasPositions) {
      handleAutoLayout()
    } else {
      nextTick(() => fitView())
    }
  }
})

onUnmounted(() => {
  document.removeEventListener('click', handleDocumentClick)
})

const hasNodes = computed(() => nodes.value.length > 0)
</script>

<template>
  <div v-if="hasNodes || teams.length > 0" class="org-canvas-container">
    <div class="canvas-header">
      <h3 class="canvas-title">Team Organization</h3>
      <div class="canvas-actions">
        <div class="add-team-dropdown-container">
          <button class="canvas-btn" @click.stop="toggleAddTeamDropdown" title="Add Team">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
              <line x1="8" y1="2" x2="8" y2="14" />
              <line x1="2" y1="8" x2="14" y2="8" />
            </svg>
            Add Team
          </button>
          <div v-if="showAddTeamDropdown" class="add-team-dropdown" @click.stop>
            <div v-if="isLoadingTeams" class="dropdown-loading">Loading teams...</div>
            <div v-else-if="availableTeams.length === 0" class="dropdown-empty">No teams available</div>
            <button
              v-else
              v-for="team in availableTeams"
              :key="team.id"
              class="dropdown-item"
              @click="addTeamToProject(team.id)"
            >
              <span class="dropdown-color" :style="{ backgroundColor: team.color }"></span>
              {{ team.name }}
            </button>
          </div>
        </div>
        <button class="canvas-btn" @click="handleAutoLayout" title="Auto Layout">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="1" y="1" width="5" height="5" rx="1" />
            <rect x="10" y="1" width="5" height="5" rx="1" />
            <rect x="1" y="10" width="5" height="5" rx="1" />
            <rect x="10" y="10" width="5" height="5" rx="1" />
          </svg>
          Layout
        </button>
        <button class="canvas-btn" @click="handleFitView" title="Fit View">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M1 5V2a1 1 0 011-1h3" />
            <path d="M11 1h3a1 1 0 011 1v3" />
            <path d="M15 11v3a1 1 0 01-1 1h-3" />
            <path d="M5 15H2a1 1 0 01-1-1v-3" />
          </svg>
          Fit
        </button>
        <button class="canvas-btn primary" @click="handleSave" title="Save">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M13 15H3a1 1 0 01-1-1V2a1 1 0 011-1h7l4 4v9a1 1 0 01-1 1z" />
            <path d="M11 15V9H5v6" />
            <path d="M5 1v4h4" />
          </svg>
          Save
        </button>
      </div>
    </div>
    <div class="canvas-viewport">
      <VueFlow
        :id="'org-canvas-' + projectId"
        v-model:nodes="nodes"
        v-model:edges="edges"
        :node-types="nodeTypes"
        :edge-types="edgeTypes"
        :default-edge-options="{ type: 'messageFlow', animated: true }"
        class="org-flow"
        @node-click="onNodeClick"
        @edge-context-menu="onEdgeContextMenu"
      >
        <Background :gap="20" />

        <!-- Remove team button on each node -->
        <template #node-team="nodeProps">
          <div class="node-wrapper">
            <TeamOrgNode v-bind="nodeProps" />
            <button
              class="node-remove-btn"
              title="Remove team from project"
              @click.stop="removeTeamFromProject(nodeProps.data.teamId)"
            >
              <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="4" y1="4" x2="12" y2="12" />
                <line x1="12" y1="4" x2="4" y2="12" />
              </svg>
            </button>
          </div>
        </template>
      </VueFlow>
    </div>

    <!-- Edge type context menu -->
    <Teleport to="body">
      <div
        v-if="contextMenu.visible"
        class="edge-context-menu"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click.stop
      >
        <div class="context-menu-title">Edge Type</div>
        <button
          v-for="opt in edgeTypeOptions"
          :key="opt.type"
          class="context-menu-item"
          @click="setEdgeType(opt.type)"
        >
          <span class="type-dot" :style="{ backgroundColor: opt.color }"></span>
          <div class="type-info">
            <span class="type-label">{{ opt.label }}</span>
            <span class="type-desc">{{ opt.desc }}</span>
          </div>
        </button>
        <button class="context-menu-item cancel" @click="closeContextMenu">Cancel</button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.org-canvas-container {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 12px;
  overflow: hidden;
}

.canvas-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
}

.canvas-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #f0f0f5);
  margin: 0;
}

.canvas-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.canvas-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: 6px;
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-secondary, #a0a0b0);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  font-size: 11px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  font-family: inherit;
}

.canvas-btn:hover {
  background: var(--bg-elevated, #222230);
  color: var(--text-primary, #f0f0f5);
}

.canvas-btn.primary {
  background: var(--accent-cyan, #00d4ff);
  color: #000;
  border-color: transparent;
}

.canvas-btn.primary:hover {
  opacity: 0.9;
}

.canvas-viewport {
  height: 350px;
  position: relative;
}

.org-flow {
  width: 100%;
  height: 100%;
}

.org-flow :deep(.vue-flow__background) {
  background: var(--bg-primary, #0a0a10);
}

.org-flow :deep(.vue-flow__background pattern circle) {
  fill: rgba(255, 255, 255, 0.06);
}

.org-flow :deep(.vue-flow__connection-path) {
  stroke: var(--accent-cyan, #00d4ff);
  stroke-width: 2;
  stroke-dasharray: 5;
}

/* Node wrapper for remove button on hover */
.node-wrapper {
  position: relative;
}

.node-remove-btn {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--bg-tertiary, #1a1a24);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.1));
  color: var(--text-tertiary, #606070);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s, background 0.15s;
}

.node-wrapper:hover .node-remove-btn {
  opacity: 1;
}

.node-remove-btn:hover {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.3);
}

/* Add team dropdown */
.add-team-dropdown-container {
  position: relative;
}

.add-team-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  min-width: 200px;
  max-height: 240px;
  overflow-y: auto;
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  z-index: 100;
  padding: 4px;
}

.dropdown-loading,
.dropdown-empty {
  padding: 12px 16px;
  color: var(--text-tertiary, #606070);
  font-size: 12px;
  text-align: center;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-primary, #f0f0f5);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s;
  font-family: inherit;
  text-align: left;
}

.dropdown-item:hover {
  background: var(--bg-tertiary, #1a1a24);
}

.dropdown-color {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>

<style>
/* Edge context menu — global because Teleported */
.edge-context-menu {
  position: fixed;
  z-index: 10000;
  min-width: 200px;
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
  padding: 6px;
}

.context-menu-title {
  padding: 6px 10px 4px;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-tertiary, #606070);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-primary, #f0f0f5);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s;
  font-family: inherit;
  text-align: left;
}

.context-menu-item:hover {
  background: var(--bg-tertiary, #1a1a24);
}

.context-menu-item.cancel {
  color: var(--text-tertiary, #606070);
  border-top: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  margin-top: 4px;
  padding-top: 8px;
  justify-content: center;
}

.type-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.type-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.type-label {
  font-weight: 500;
}

.type-desc {
  font-size: 10px;
  color: var(--text-tertiary, #606070);
}
</style>
