import { ref, type Ref } from 'vue'
import type { Node, Edge } from '@vue-flow/core'
import type {
  Team,
  TeamMember,
  TeamAgentAssignment,
  TopologyType,
  TopologyConfig,
  CanvasPositions,
} from '../services/api'

export interface AgentNodeData {
  label: string
  agentId: string
  role: string
  color: string
  tier?: 'leader' | 'senior' | 'member'
  assignments: { type: string; name: string; id: string }[]
}

export interface SuperAgentNodeData {
  label: string
  superAgentId: string
  role: string
  color: string
  tier?: 'leader' | 'senior' | 'member'
  sessionCount: number
  documentCount: number
  assignments: { type: string; name: string; id: string }[]
}

export interface SyncToTeamResult {
  topology: TopologyType | null
  topology_config: TopologyConfig
}

export function useTeamCanvas(
  team: Ref<Team | null>,
  members: Ref<TeamMember[]>,
  assignments: Ref<TeamAgentAssignment[]>,
) {
  const nodes = ref<Node<AgentNodeData | SuperAgentNodeData>[]>([])
  const edges = ref<Edge[]>([])
  const isSyncing = ref(false)

  function syncFromTeam(): void {
    isSyncing.value = true
    try {
      const t = team.value
      if (!t) {
        nodes.value = []
        edges.value = []
        return
      }

      const color = t.color || '#6366f1'
      const topologyConfig = parseTopologyConfig(t.topology_config)
      const savedPositions = topologyConfig?.positions || {}

      // Create nodes from members — handle both agent and super_agent member types
      const newNodes: Node<AgentNodeData | SuperAgentNodeData>[] = members.value.map((member, idx) => {
        if (member.super_agent_id) {
          // SuperAgent member — use super_agent_id as node ID (entity-prefixed, no collision risk)
          const saId = member.super_agent_id
          const position = savedPositions[saId]
            ? { x: savedPositions[saId].x, y: savedPositions[saId].y }
            : { x: idx * 250, y: 100 }

          return {
            id: saId,
            type: 'super_agent',
            position,
            data: {
              label: member.name || member.super_agent_name || 'Unknown SuperAgent',
              superAgentId: saId,
              role: member.role || 'lead',
              color: '#a855f7',
              tier: member.tier || undefined,
              sessionCount: 0,
              documentCount: 0,
              assignments: [],
            } as SuperAgentNodeData,
          }
        }

        // Regular agent member or manual member
        const agentId = member.agent_id || String(member.id) || `member-${idx}`
        const memberAssignments = assignments.value
          .filter((a) => a.agent_id === agentId)
          .map((a) => ({ type: a.entity_type, name: a.entity_name || a.entity_id, id: a.entity_id }))

        const position = savedPositions[agentId]
          ? { x: savedPositions[agentId].x, y: savedPositions[agentId].y }
          : { x: idx * 250, y: 100 }

        return {
          id: agentId,
          type: 'agent',
          position,
          data: {
            label: member.name || member.agent_name || 'Unknown Agent',
            agentId,
            role: member.role || 'member',
            color,
            tier: member.tier || undefined,
            assignments: memberAssignments,
          } as AgentNodeData,
        }
      })

      // Create edges: prefer stored raw edges, fall back to building from topology
      let newEdges: Edge[]
      if (topologyConfig?.edges && topologyConfig.edges.length > 0) {
        const nodeIds = new Set(newNodes.map((n) => n.id))
        newEdges = topologyConfig.edges
          .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
          .map((e) => ({
            id: e.id || `e-${e.source}-${e.target}`,
            source: e.source,
            target: e.target,
            type: 'messageFlow' as const,
            animated: e.type === 'messaging' || !e.type,
            data: {
              edge_type: e.type || 'messaging',
              label: e.label,
            },
          }))
      } else {
        newEdges = buildEdgesFromTopology(
          t.topology || null,
          topologyConfig,
          newNodes,
        )
      }

      nodes.value = newNodes
      edges.value = newEdges
    } finally {
      isSyncing.value = false
    }
  }

  function syncToTeam(): SyncToTeamResult {
    const currentEdges = edges.value
    const currentNodes = nodes.value
    const positions = getPositions()

    // Always serialize raw edges so they can be restored even for recognized topologies
    const rawEdges = currentEdges.map(e => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: typeof e.label === 'string' ? e.label : undefined,
      type: e.data?.edge_type || undefined,
    }))

    if (currentNodes.length === 0) {
      return { topology: null, topology_config: { positions, edges: rawEdges } }
    }

    // Analyze edges to determine topology
    if (currentEdges.length === 0 && currentNodes.length > 1) {
      // No edges with multiple agents = parallel
      return {
        topology: 'parallel',
        topology_config: {
          agents: currentNodes.map((n) => n.id),
          positions,
          edges: rawEdges,
        },
      }
    }

    if (currentEdges.length === 0 && currentNodes.length <= 1) {
      return { topology: null, topology_config: { positions, edges: rawEdges } }
    }

    // Check for generator-critic (exactly 2 nodes with bidirectional edges)
    if (currentNodes.length === 2) {
      const [a, b] = currentNodes
      const aToB = currentEdges.some((e) => e.source === a.id && e.target === b.id)
      const bToA = currentEdges.some((e) => e.source === b.id && e.target === a.id)
      if (aToB && bToA) {
        return {
          topology: 'generator_critic',
          topology_config: {
            generator: a.id,
            critic: b.id,
            positions,
            edges: rawEdges,
          },
        }
      }
    }

    // Check for hub-spoke (coordinator) — bidirectional hub
    const hubNode = findHubNode(currentNodes, currentEdges)
    if (hubNode) {
      const workerIds = currentNodes.filter((n) => n.id !== hubNode).map((n) => n.id)
      return {
        topology: 'coordinator',
        topology_config: {
          coordinator: hubNode,
          workers: workerIds,
          positions,
          edges: rawEdges,
        },
      }
    }

    // Check for hierarchical (tree root with outgoing-only edges to all others, no cycles)
    const treeRoot = findTreeRoot(currentNodes, currentEdges)
    if (treeRoot) {
      return {
        topology: 'hierarchical',
        topology_config: {
          lead: treeRoot,
          positions,
          edges: rawEdges,
        },
      }
    }

    // Check for linear chain (sequential)
    const chain = findLinearChain(currentNodes, currentEdges)
    if (chain) {
      return {
        topology: 'sequential',
        topology_config: {
          order: chain,
          positions,
          edges: rawEdges,
        },
      }
    }

    // Unknown topology — persist raw edges
    return {
      topology: null,
      topology_config: {
        positions,
        edges: rawEdges,
      },
    }
  }

  function getPositions(): CanvasPositions {
    const positions: CanvasPositions = {}
    for (const node of nodes.value) {
      positions[node.id] = { x: node.position.x, y: node.position.y }
    }
    return positions
  }

  return {
    nodes,
    edges,
    isSyncing,
    syncFromTeam,
    syncToTeam,
    getPositions,
    buildEdgesFromTopology,
  }
}

// -- Helpers --

function parseTopologyConfig(raw: string | TopologyConfig | undefined | null): TopologyConfig | null {
  if (!raw) return null
  if (typeof raw === 'object') return raw as TopologyConfig
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function buildEdgesFromTopology(
  topology: TopologyType | null,
  config: TopologyConfig | null,
  nodes: Node<AgentNodeData | SuperAgentNodeData>[],
): Edge[] {
  if (!config) return []

  // If topology is null but config has saved edges, restore them
  if (!topology) {
    if (config.edges && config.edges.length > 0) {
      const nodeIds = new Set(nodes.map((n) => n.id))
      return config.edges
        .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
        .map((e) => ({
          id: e.id || `e-${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          type: 'messageFlow',
          animated: e.type === 'messaging' || !e.type,
          data: {
            edge_type: e.type || 'messaging',
            label: e.label,
          },
        }))
    }
    return []
  }

  const nodeIds = new Set(nodes.map((n) => n.id))

  switch (topology) {
    case 'sequential': {
      const order = config.order || []
      const validOrder = order.length > 0
        ? order.filter((id) => nodeIds.has(id))
        : nodes.map((n) => n.id)
      const edgeList: Edge[] = []
      for (let i = 0; i < validOrder.length - 1; i++) {
        edgeList.push({
          id: `e-${validOrder[i]}-${validOrder[i + 1]}`,
          source: validOrder[i],
          target: validOrder[i + 1],
          type: 'messageFlow',
          animated: true,
          data: { edge_type: 'messaging', label: 'handoff' },
        })
      }
      return edgeList
    }

    case 'coordinator': {
      const coordinator = config.coordinator
      const workers = config.workers || []
      if (!coordinator || !nodeIds.has(coordinator)) return []
      const validWorkers = workers.filter((id) => nodeIds.has(id))
      const edgeList: Edge[] = []
      for (const worker of validWorkers) {
        edgeList.push({
          id: `e-${coordinator}-${worker}`,
          source: coordinator,
          target: worker,
          type: 'messageFlow',
          animated: true,
          data: { edge_type: 'messaging', label: 'delegation' },
        })
        edgeList.push({
          id: `e-${worker}-${coordinator}`,
          source: worker,
          target: coordinator,
          type: 'messageFlow',
          animated: true,
          data: { edge_type: 'messaging', label: 'reporting' },
        })
      }
      return edgeList
    }

    case 'generator_critic': {
      const generator = config.generator
      const critic = config.critic
      if (!generator || !critic || !nodeIds.has(generator) || !nodeIds.has(critic)) return []
      return [
        {
          id: `e-${generator}-${critic}`,
          source: generator,
          target: critic,
          type: 'messageFlow',
          animated: true,
          data: { edge_type: 'messaging', label: 'generates' },
        },
        {
          id: `e-${critic}-${generator}`,
          source: critic,
          target: generator,
          type: 'messageFlow',
          animated: true,
          data: { edge_type: 'messaging', label: 'critiques' },
        },
      ]
    }

    case 'parallel':
      // No edges for parallel topology
      return []

    case 'hierarchical': {
      // Build edges from lead outward following stored edges, all labeled 'delegation'
      const lead = config.lead
      if (!lead || !nodeIds.has(lead)) return []
      // If config has stored edges, use them with delegation labels
      if (config.edges && config.edges.length > 0) {
        return config.edges
          .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
          .map((e) => ({
            id: e.id || `e-${e.source}-${e.target}`,
            source: e.source,
            target: e.target,
            type: 'messageFlow',
            animated: e.type === 'messaging' || !e.type,
            data: {
              edge_type: e.type || 'messaging',
              label: e.label || 'delegation',
            },
          }))
      }
      // Fallback: star from lead to all others
      const edgeList: Edge[] = []
      for (const node of nodes) {
        if (node.id !== lead) {
          edgeList.push({
            id: `e-${lead}-${node.id}`,
            source: lead,
            target: node.id,
            type: 'messageFlow',
            animated: true,
            data: { edge_type: 'messaging', label: 'delegation' },
          })
        }
      }
      return edgeList
    }

    case 'human_in_loop': {
      // Same as sequential but add 'approval' label on edges targeting approval nodes
      const order = config.order || []
      const approvalNodes = new Set(config.approval_nodes || [])
      const validOrder = order.filter((id) => nodeIds.has(id))
      const edgeList: Edge[] = []
      for (let i = 0; i < validOrder.length - 1; i++) {
        const target = validOrder[i + 1]
        const edgeLabel = approvalNodes.has(target) ? 'approval' : 'handoff'
        edgeList.push({
          id: `e-${validOrder[i]}-${target}`,
          source: validOrder[i],
          target,
          type: 'messageFlow',
          animated: true,
          data: { edge_type: 'messaging', label: edgeLabel },
        })
      }
      return edgeList
    }

    case 'composite':
      // No auto-generated edges for composite (too complex to infer; rely on stored edges)
      return []

    default:
      return []
  }
}

function findHubNode(nodes: Node[], edges: Edge[]): string | null {
  if (nodes.length < 3) return null

  for (const node of nodes) {
    const outgoing = edges.filter((e) => e.source === node.id)
    const incoming = edges.filter((e) => e.target === node.id)
    const otherNodes = nodes.filter((n) => n.id !== node.id)

    // Hub connects to all others
    const connectsToAll = otherNodes.every(
      (other) =>
        outgoing.some((e) => e.target === other.id) ||
        incoming.some((e) => e.source === other.id),
    )

    // No peer-to-peer edges (edges between non-hub nodes)
    const peerEdges = edges.filter(
      (e) => e.source !== node.id && e.target !== node.id,
    )

    if (connectsToAll && peerEdges.length === 0) {
      return node.id
    }
  }

  return null
}

/**
 * Find a tree root: one node with outgoing edges that reach all others, no incoming edges to root,
 * and no cycles. This detects hierarchical delegation trees.
 */
function findTreeRoot(nodes: Node[], edges: Edge[]): string | null {
  if (nodes.length < 2) return null

  // Build adjacency (outgoing only — directed graph)
  const outgoing: Record<string, string[]> = {}
  const incomingCount: Record<string, number> = {}
  for (const node of nodes) {
    outgoing[node.id] = []
    incomingCount[node.id] = 0
  }
  for (const edge of edges) {
    if (outgoing[edge.source] !== undefined && incomingCount[edge.target] !== undefined) {
      outgoing[edge.source].push(edge.target)
      incomingCount[edge.target]++
    }
  }

  // Root has zero incoming and at least one outgoing
  const rootCandidates = nodes.filter(
    (n) => incomingCount[n.id] === 0 && outgoing[n.id].length > 0,
  )
  if (rootCandidates.length !== 1) return null

  const root = rootCandidates[0].id

  // BFS from root must reach all nodes (no cycles check: visited count == node count)
  const visited = new Set<string>()
  const queue = [root]
  visited.add(root)
  while (queue.length > 0) {
    const current = queue.shift()!
    for (const next of outgoing[current]) {
      if (visited.has(next)) {
        // Cycle or convergence — not a simple tree
        return null
      }
      visited.add(next)
      queue.push(next)
    }
  }

  // Must reach all nodes
  if (visited.size !== nodes.length) return null

  // Each non-root node must have exactly one incoming edge (tree property)
  for (const node of nodes) {
    if (node.id !== root && incomingCount[node.id] !== 1) return null
  }

  return root
}

function findLinearChain(nodes: Node[], edges: Edge[]): string[] | null {
  if (nodes.length < 2) return null

  // Build adjacency
  const outDegree: Record<string, string[]> = {}
  const inDegree: Record<string, string[]> = {}
  for (const node of nodes) {
    outDegree[node.id] = []
    inDegree[node.id] = []
  }
  for (const edge of edges) {
    if (outDegree[edge.source] && inDegree[edge.target]) {
      outDegree[edge.source].push(edge.target)
      inDegree[edge.target].push(edge.source)
    }
  }

  // Each node has at most 1 incoming and 1 outgoing
  for (const node of nodes) {
    if (outDegree[node.id].length > 1 || inDegree[node.id].length > 1) {
      return null
    }
  }

  // Find start node (no incoming)
  const startNodes = nodes.filter((n) => inDegree[n.id].length === 0)
  if (startNodes.length !== 1) return null

  // Walk the chain
  const chain: string[] = []
  let current = startNodes[0].id
  const visited = new Set<string>()
  while (current && !visited.has(current)) {
    visited.add(current)
    chain.push(current)
    const next = outDegree[current]
    current = next.length === 1 ? next[0] : ''
  }

  // Chain must include all nodes
  if (chain.length !== nodes.length) return null

  return chain
}
