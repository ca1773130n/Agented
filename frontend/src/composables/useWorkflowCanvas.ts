import { ref, watch, type Ref } from 'vue'
import type { Node, Edge } from '@vue-flow/core'
import { workflowApi } from '../services/api/workflows'

// ---------------------------------------------------------------------------
// Graph serialization types (mirror backend WorkflowGraph model)
// ---------------------------------------------------------------------------

export interface WorkflowGraphNode {
  id: string
  type: string
  label: string
  config: Record<string, unknown>
  error_mode: string
  retry_max: number
  retry_backoff_seconds: number
}

export interface WorkflowGraphEdge {
  source: string
  target: string
  sourceHandle?: string
  targetHandle?: string
}

export interface WorkflowGraph {
  nodes: WorkflowGraphNode[]
  edges: WorkflowGraphEdge[]
  settings?: { positions?: Record<string, { x: number; y: number }> }
}

// ---------------------------------------------------------------------------
// Node data interface (passed to every custom node component via `data`)
// ---------------------------------------------------------------------------

export interface WorkflowNodeData {
  label: string
  config: Record<string, unknown>
  error_mode: string
  retry_max: number
  retry_backoff_seconds: number
  executionStatus?: string
}

// ---------------------------------------------------------------------------
// Default labels per node type
// ---------------------------------------------------------------------------

const DEFAULT_LABELS: Record<string, string> = {
  trigger: 'New Trigger',
  skill: 'New Skill',
  command: 'New Command',
  agent: 'New Agent',
  script: 'New Script',
  conditional: 'New Condition',
  transform: 'New Transform',
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useWorkflowCanvas(workflowId: Ref<string>) {
  const nodes = ref<Node<WorkflowNodeData>[]>([])
  const edges = ref<Edge[]>([])
  const isDirty = ref(false)
  const currentVersion = ref<number | null>(null)
  const isLoading = ref(false)

  // Internal flag to suppress dirty-tracking during initial load
  let _loading = false

  // -----------------------------------------------------------------------
  // Load latest version from backend
  // -----------------------------------------------------------------------

  async function loadLatestVersion(): Promise<void> {
    isLoading.value = true
    _loading = true
    try {
      const response = await workflowApi.listVersions(workflowId.value)
      const versions = response.versions
      if (!versions || versions.length === 0) {
        nodes.value = []
        edges.value = []
        currentVersion.value = null
        isDirty.value = false
        return
      }

      const latest = versions[versions.length - 1]
      const graph: WorkflowGraph = JSON.parse(latest.graph_json)
      const positions = graph.settings?.positions || {}

      // Convert backend nodes -> VueFlow nodes
      const vfNodes: Node<WorkflowNodeData>[] = graph.nodes.map((n) => ({
        id: n.id,
        type: n.type,
        position: positions[n.id] || { x: 0, y: 0 },
        data: {
          label: n.label,
          config: n.config || {},
          error_mode: n.error_mode || 'stop',
          retry_max: n.retry_max ?? 0,
          retry_backoff_seconds: n.retry_backoff_seconds ?? 1,
        },
      }))

      // Convert backend edges -> VueFlow edges
      const conditionalNodeIds = new Set(
        graph.nodes.filter((n) => n.type === 'conditional').map((n) => n.id),
      )
      const vfEdges: Edge[] = graph.edges.map((e) => {
        const label =
          conditionalNodeIds.has(e.source) && e.sourceHandle === 'true'
            ? 'True'
            : conditionalNodeIds.has(e.source) && e.sourceHandle === 'false'
              ? 'False'
              : undefined
        return {
          id: `e-${e.source}-${e.target}${e.sourceHandle ? '-' + e.sourceHandle : ''}`,
          source: e.source,
          target: e.target,
          sourceHandle: e.sourceHandle || undefined,
          targetHandle: e.targetHandle || undefined,
          type: 'smoothstep',
          animated: true,
          ...(label ? { label } : {}),
        }
      })

      nodes.value = vfNodes
      edges.value = vfEdges
      currentVersion.value = latest.version
      isDirty.value = false
    } finally {
      isLoading.value = false
      // Use setTimeout to let the watcher fire first, then reset the flag
      setTimeout(() => {
        _loading = false
      }, 0)
    }
  }

  // -----------------------------------------------------------------------
  // Save current state back to backend
  // -----------------------------------------------------------------------

  async function saveVersion(): Promise<void> {
    isLoading.value = true
    try {
      const positions: Record<string, { x: number; y: number }> = {}
      for (const n of nodes.value) {
        positions[n.id] = { x: n.position.x, y: n.position.y }
      }

      const graph: WorkflowGraph = {
        nodes: nodes.value.map((n) => {
          const d = n.data as WorkflowNodeData | undefined
          return {
            id: n.id,
            type: n.type || 'skill',
            label: d?.label || 'Untitled',
            config: d?.config || {},
            error_mode: d?.error_mode || 'stop',
            retry_max: d?.retry_max ?? 0,
            retry_backoff_seconds: d?.retry_backoff_seconds ?? 1,
          }
        }),
        edges: edges.value.map((e) => ({
          source: e.source,
          target: e.target,
          sourceHandle: e.sourceHandle || undefined,
          targetHandle: e.targetHandle || undefined,
        })),
        settings: { positions },
      }

      const result = await workflowApi.createVersion(workflowId.value, {
        graph_json: JSON.stringify(graph),
      })

      currentVersion.value = result.version
      isDirty.value = false
    } finally {
      isLoading.value = false
    }
  }

  // -----------------------------------------------------------------------
  // Add a new node
  // -----------------------------------------------------------------------

  function addNode(
    type: string,
    position: { x: number; y: number },
    config?: Record<string, unknown>,
  ): void {
    const id = `node-${crypto.randomUUID().slice(0, 8)}`
    const label = DEFAULT_LABELS[type] || 'New Node'

    const newNode: Node<WorkflowNodeData> = {
      id,
      type,
      position,
      data: {
        label,
        config: config || {},
        error_mode: 'stop',
        retry_max: 0,
        retry_backoff_seconds: 1,
      },
    }

    nodes.value = [...nodes.value, newNode]
    isDirty.value = true
  }

  // -----------------------------------------------------------------------
  // Remove a node (and all connected edges)
  // -----------------------------------------------------------------------

  function removeNode(nodeId: string): void {
    nodes.value = nodes.value.filter((n) => n.id !== nodeId)
    edges.value = edges.value.filter((e) => e.source !== nodeId && e.target !== nodeId)
    isDirty.value = true
  }

  // -----------------------------------------------------------------------
  // Update node config (shallow merge; also updates error_mode/retry fields)
  // -----------------------------------------------------------------------

  function updateNodeConfig(nodeId: string, config: Record<string, unknown>): void {
    const idx = nodes.value.findIndex((n) => n.id === nodeId)
    if (idx === -1) return

    nodes.value = nodes.value.map((n) => {
      if (n.id !== nodeId || !n.data) return n
      const updatedData: WorkflowNodeData = {
        ...n.data,
        config: { ...(n.data.config ?? {}), ...config },
      }
      // error_mode, retry_max, retry_backoff_seconds live at data root, not inside config
      if ('error_mode' in config) updatedData.error_mode = config.error_mode as string
      if ('retry_max' in config) updatedData.retry_max = config.retry_max as number
      if ('retry_backoff_seconds' in config)
        updatedData.retry_backoff_seconds = config.retry_backoff_seconds as number
      return { ...n, data: updatedData }
    })
    isDirty.value = true
  }

  // -----------------------------------------------------------------------
  // Update node label
  // -----------------------------------------------------------------------

  function updateNodeLabel(nodeId: string, label: string): void {
    nodes.value = nodes.value.map((n) =>
      n.id === nodeId && n.data ? { ...n, data: { ...n.data, label } } : n,
    )
    isDirty.value = true
  }

  // -----------------------------------------------------------------------
  // Remove an edge
  // -----------------------------------------------------------------------

  function removeEdge(edgeId: string): void {
    edges.value = edges.value.filter((e) => e.id !== edgeId)
    isDirty.value = true
  }

  // -----------------------------------------------------------------------
  // Get current node positions
  // -----------------------------------------------------------------------

  function getPositions(): Record<string, { x: number; y: number }> {
    const positions: Record<string, { x: number; y: number }> = {}
    for (const n of nodes.value) {
      positions[n.id] = { x: n.position.x, y: n.position.y }
    }
    return positions
  }

  // -----------------------------------------------------------------------
  // Deep watcher for change tracking
  // -----------------------------------------------------------------------

  watch(
    [nodes, edges],
    () => {
      if (!_loading) {
        isDirty.value = true
      }
    },
    { deep: true },
  )

  return {
    nodes,
    edges,
    isDirty,
    currentVersion,
    isLoading,
    loadLatestVersion,
    saveVersion,
    addNode,
    removeNode,
    removeEdge,
    getPositions,
    updateNodeConfig,
    updateNodeLabel,
  }
}
