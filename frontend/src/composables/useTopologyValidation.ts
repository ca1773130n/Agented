import { computed, type Ref } from 'vue'
import type { Node, Edge, Connection } from '@vue-flow/core'
import type { TopologyType } from '../services/api'

export function useTopologyValidation(
  nodes: Ref<Node[]>,
  edges: Ref<Edge[]>,
  topology?: Ref<string | null | undefined>,
  getTierForNode?: (nodeId: string) => string | undefined,
) {
  function isValidConnection(connection: Connection): boolean {
    // Reject self-connections
    if (connection.source === connection.target) return false

    // Reject duplicate edges
    const duplicate = edges.value.some(
      (e) => e.source === connection.source && e.target === connection.target,
    )
    if (duplicate) return false

    // Only allow connections between agent and super_agent node types
    const validTypes = new Set(['agent', 'super_agent'])
    const sourceNode = nodes.value.find((n) => n.id === connection.source)
    const targetNode = nodes.value.find((n) => n.id === connection.target)
    if (!sourceNode || !targetNode) return false
    if (!validTypes.has(sourceNode.type || '') || !validTypes.has(targetNode.type || '')) return false

    // Full tier-based hierarchy enforcement (only for hierarchical topology)
    if (topology?.value === 'hierarchical' && getTierForNode) {
      const sourceTier = getTierForNode(connection.source)
      const targetTier = getTierForNode(connection.target)

      if (sourceTier && targetTier) {
        const tierRank: Record<string, number> = { member: 0, senior: 1, leader: 2 }
        const sourceRank = tierRank[sourceTier] ?? 0
        const targetRank = tierRank[targetTier] ?? 0

        // In hierarchical topology, connections must flow upward:
        // - Members can only connect TO seniors or leaders (targetRank > sourceRank)
        // - Seniors can only connect TO leaders (targetRank > sourceRank)
        // - Leaders can connect to anyone (no restriction on outbound from leaders)
        if (sourceTier !== 'leader' && targetRank <= sourceRank) {
          return false
        }
      }
    }

    return true
  }

  const warnings = computed<string[]>(() => {
    const result: string[] = []
    const currentNodes = nodes.value
    const currentEdges = edges.value

    if (currentNodes.length < 2) return result

    // Check: multiple disconnected agents
    const connectedNodeIds = new Set<string>()
    for (const edge of currentEdges) {
      connectedNodeIds.add(edge.source)
      connectedNodeIds.add(edge.target)
    }
    const disconnectedCount = currentNodes.filter((n) => !connectedNodeIds.has(n.id)).length
    if (disconnectedCount > 0 && currentEdges.length > 0) {
      // Some connected, some not — warn (but 0 edges with multiple nodes is valid parallel topology)
      result.push(
        'Multiple disconnected agents detected. Consider adding a coordinator or defining an execution order.',
      )
    }

    // Check: sequential chain with dead ends
    const outDegree: Record<string, number> = {}
    const inDegree: Record<string, number> = {}
    for (const node of currentNodes) {
      outDegree[node.id] = 0
      inDegree[node.id] = 0
    }
    for (const edge of currentEdges) {
      if (outDegree[edge.source] !== undefined) outDegree[edge.source]++
      if (inDegree[edge.target] !== undefined) inDegree[edge.target]++
    }

    if (currentEdges.length > 0) {
      const sinks = currentNodes.filter(
        (n) => inDegree[n.id] > 0 && outDegree[n.id] === 0,
      )
      const sources = currentNodes.filter(
        (n) => outDegree[n.id] > 0 && inDegree[n.id] === 0,
      )
      // If there are sinks and sources but not forming a clean chain
      if (sinks.length > 0 && sources.length > 0 && sinks.length + sources.length < currentNodes.length) {
        // Check if it is not a clean chain
        const isCleanChain = sources.length === 1 && sinks.length === 1 &&
          currentNodes.every((n) => outDegree[n.id] <= 1 && inDegree[n.id] <= 1)
        if (!isCleanChain) {
          result.push(
            'Sequential chain detected but some agents have no clear input or output connection.',
          )
        }
      }
    }

    // Check: hub-spoke with no return edges
    for (const node of currentNodes) {
      const outgoing = currentEdges.filter((e) => e.source === node.id)
      const incoming = currentEdges.filter((e) => e.target === node.id)
      const otherNodes = currentNodes.filter((n) => n.id !== node.id)

      if (otherNodes.length < 2) continue

      const connectsToAllOut = otherNodes.every((other) =>
        outgoing.some((e) => e.target === other.id),
      )

      if (connectsToAllOut && incoming.length === 0) {
        result.push(
          'Coordinator pattern detected. Workers cannot report back to the coordinator without return edges.',
        )
        break
      }
    }

    // Check: bidirectional edges between more than 2 agents
    const bidirectionalPairs = new Set<string>()
    for (const edge of currentEdges) {
      const reverse = currentEdges.find(
        (e) => e.source === edge.target && e.target === edge.source,
      )
      if (reverse) {
        const key = [edge.source, edge.target].sort().join('-')
        bidirectionalPairs.add(key)
      }
    }
    const bidirectionalNodeIds = new Set<string>()
    for (const pair of bidirectionalPairs) {
      const [a, b] = pair.split('-')
      bidirectionalNodeIds.add(a)
      bidirectionalNodeIds.add(b)
    }
    if (bidirectionalNodeIds.size > 2) {
      result.push(
        'Bidirectional edges detected between more than 2 agents. Generator-critic topology supports exactly 2 agents.',
      )
    }

    // Check: cycle detection (other than gen-critic bidirectional)
    if (currentEdges.length > 0 && bidirectionalPairs.size === 0) {
      if (hasCycle(currentNodes, currentEdges)) {
        result.push(
          'Cycle detected in agent connections. Only generator-critic topology supports bidirectional connections.',
        )
      }
    }

    // Hint for unlabeled edges in complex graphs
    if (currentEdges.length > 2 && currentEdges.some(e => !e.label)) {
      result.push('Some edges have no labels. Adding labels like "delegation" or "reporting" clarifies the team structure.')
    }

    // Check: hierarchy violations in hierarchical topology
    if (topology?.value === 'hierarchical' && getTierForNode) {
      const tierRank: Record<string, number> = { member: 0, senior: 1, leader: 2 }
      const hierarchyViolation = currentEdges.some(e => {
        const sTier = getTierForNode(e.source)
        const tTier = getTierForNode(e.target)
        if (!sTier || !tTier) return false
        const sRank = tierRank[sTier] ?? 0
        const tRank = tierRank[tTier] ?? 0
        return sTier !== 'leader' && tRank <= sRank
      })
      if (hierarchyViolation) {
        result.push(
          'In hierarchical topology, members can only connect to seniors or leaders, and seniors can only connect to leaders.'
        )
      }
    }

    return result
  })

  const inferredTopology = computed<TopologyType | null>(() => {
    const currentNodes = nodes.value
    const currentEdges = edges.value

    if (currentNodes.length === 0) return null

    // No edges with multiple agents = parallel
    if (currentEdges.length === 0 && currentNodes.length > 1) {
      return 'parallel'
    }

    if (currentEdges.length === 0) return null

    // Generator-critic: exactly 2 nodes with bidirectional edges
    if (currentNodes.length === 2) {
      const [a, b] = currentNodes
      const aToB = currentEdges.some((e) => e.source === a.id && e.target === b.id)
      const bToA = currentEdges.some((e) => e.source === b.id && e.target === a.id)
      if (aToB && bToA) return 'generator_critic'
    }

    // Hub-spoke (coordinator)
    for (const node of currentNodes) {
      if (currentNodes.length < 3) break
      const outgoing = currentEdges.filter((e) => e.source === node.id)
      const incoming = currentEdges.filter((e) => e.target === node.id)
      const otherNodes = currentNodes.filter((n) => n.id !== node.id)
      const connectsToAll = otherNodes.every(
        (other) =>
          outgoing.some((e) => e.target === other.id) ||
          incoming.some((e) => e.source === other.id),
      )
      const peerEdges = currentEdges.filter(
        (e) => e.source !== node.id && e.target !== node.id,
      )
      if (connectsToAll && peerEdges.length === 0) return 'coordinator'
    }

    // Hierarchical: tree-shaped DAG (one root, no cycles, every non-root has exactly 1 parent)
    if (currentNodes.length >= 3 && !hasCycle(currentNodes, currentEdges)) {
      const inCount: Record<string, number> = {}
      const outCount: Record<string, number> = {}
      for (const node of currentNodes) {
        inCount[node.id] = 0
        outCount[node.id] = 0
      }
      for (const edge of currentEdges) {
        if (inCount[edge.target] !== undefined) inCount[edge.target]++
        if (outCount[edge.source] !== undefined) outCount[edge.source]++
      }
      const roots = currentNodes.filter(n => inCount[n.id] === 0 && outCount[n.id] > 0)
      const leaves = currentNodes.filter(n => outCount[n.id] === 0 && inCount[n.id] > 0)
      const allSingleParent = currentNodes.every(n => inCount[n.id] <= 1)
      if (roots.length === 1 && leaves.length >= 1 && allSingleParent) {
        return 'hierarchical'
      }
    }

    // Linear chain (sequential)
    const outDeg: Record<string, string[]> = {}
    const inDeg: Record<string, string[]> = {}
    for (const node of currentNodes) {
      outDeg[node.id] = []
      inDeg[node.id] = []
    }
    for (const edge of currentEdges) {
      if (outDeg[edge.source]) outDeg[edge.source].push(edge.target)
      if (inDeg[edge.target]) inDeg[edge.target].push(edge.source)
    }
    const allSingleDeg = currentNodes.every(
      (n) => outDeg[n.id].length <= 1 && inDeg[n.id].length <= 1,
    )
    const startNodes = currentNodes.filter((n) => inDeg[n.id].length === 0)
    if (allSingleDeg && startNodes.length === 1) {
      // Walk chain
      let current = startNodes[0].id
      const visited = new Set<string>()
      while (current && !visited.has(current)) {
        visited.add(current)
        const next = outDeg[current]
        current = next.length === 1 ? next[0] : ''
      }
      if (visited.size === currentNodes.length) return 'sequential'
    }

    return null
  })

  return {
    isValidConnection,
    warnings,
    inferredTopology,
  }
}

// -- Helpers --

function hasCycle(nodes: Node[], edges: Edge[]): boolean {
  const adjacency: Record<string, string[]> = {}
  for (const node of nodes) {
    adjacency[node.id] = []
  }
  for (const edge of edges) {
    if (adjacency[edge.source]) {
      adjacency[edge.source].push(edge.target)
    }
  }

  const visited = new Set<string>()
  const inStack = new Set<string>()

  function dfs(nodeId: string): boolean {
    visited.add(nodeId)
    inStack.add(nodeId)

    for (const neighbor of adjacency[nodeId] || []) {
      if (!visited.has(neighbor)) {
        if (dfs(neighbor)) return true
      } else if (inStack.has(neighbor)) {
        return true
      }
    }

    inStack.delete(nodeId)
    return false
  }

  for (const node of nodes) {
    if (!visited.has(node.id)) {
      if (dfs(node.id)) return true
    }
  }

  return false
}
