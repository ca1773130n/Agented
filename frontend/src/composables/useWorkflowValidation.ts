/**
 * useWorkflowValidation — Graph validation composable for the workflow builder.
 *
 * Validates the workflow DAG for structural issues: missing triggers, cycles,
 * orphaned nodes, empty configs, and port type mismatches.
 *
 * Follows the pattern established by useTopologyValidation.ts.
 */

import type { Node, Edge, Connection } from '@vue-flow/core'
import type { WorkflowNodeData } from '../types/workflow'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ValidationResult {
  level: 'error' | 'warning'
  message: string
  nodeIds?: string[]
}

// ---------------------------------------------------------------------------
// Port type system
// ---------------------------------------------------------------------------

const NODE_OUTPUT_TYPES: Record<string, string> = {
  trigger: 'any',
  skill: 'text',
  command: 'text',
  agent: 'text',
  script: 'text',
  conditional: 'any',
  transform: 'json',
}

const NODE_INPUT_TYPES: Record<string, string> = {
  trigger: 'none',
  skill: 'any',
  command: 'text',
  agent: 'text',
  script: 'text',
  conditional: 'any',
  transform: 'any',
}

/**
 * Check if source output type is compatible with target input type.
 * 'any' is a universal adapter, and 'none' rejects all connections.
 */
function areTypesCompatible(sourceType: string, targetType: string): boolean {
  if (targetType === 'none') return false
  if (sourceType === 'any' || targetType === 'any') return true
  return sourceType === targetType
}

// ---------------------------------------------------------------------------
// Cycle detection (DFS-based, adapted from useTopologyValidation.ts)
// ---------------------------------------------------------------------------

function detectCycle(
  nodes: Node[],
  edges: Edge[],
): { hasCycle: boolean; cycleNodeIds: string[] } {
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
  const cycleNodes = new Set<string>()

  function dfs(nodeId: string, path: string[]): boolean {
    visited.add(nodeId)
    inStack.add(nodeId)
    path.push(nodeId)

    for (const neighbor of adjacency[nodeId] || []) {
      if (!visited.has(neighbor)) {
        if (dfs(neighbor, path)) return true
      } else if (inStack.has(neighbor)) {
        // Found a cycle -- collect node IDs in the cycle
        const cycleStart = path.indexOf(neighbor)
        for (let i = cycleStart; i < path.length; i++) {
          cycleNodes.add(path[i])
        }
        cycleNodes.add(neighbor)
        return true
      }
    }

    path.pop()
    inStack.delete(nodeId)
    return false
  }

  let hasCycle = false
  for (const node of nodes) {
    if (!visited.has(node.id)) {
      if (dfs(node.id, [])) {
        hasCycle = true
        break
      }
    }
  }

  return { hasCycle, cycleNodeIds: Array.from(cycleNodes) }
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useWorkflowValidation() {
  /**
   * Validate the entire graph and return an array of validation results.
   */
  function validateGraph(nodes: Node[], edges: Edge[]): ValidationResult[] {
    const results: ValidationResult[] = []

    if (nodes.length === 0) return results

    // -----------------------------------------------------------------------
    // 1. No trigger node (error)
    // -----------------------------------------------------------------------
    const triggerNodes = nodes.filter((n) => n.type === 'trigger')
    if (triggerNodes.length === 0) {
      results.push({
        level: 'error',
        message: 'Workflow must have at least one Trigger node as an entry point',
      })
    }

    // -----------------------------------------------------------------------
    // 2. Multiple trigger nodes (warning)
    // -----------------------------------------------------------------------
    if (triggerNodes.length > 1) {
      results.push({
        level: 'warning',
        message: `Multiple Trigger nodes detected (${triggerNodes.length}). Typically a workflow has one trigger.`,
        nodeIds: triggerNodes.map((n) => n.id),
      })
    }

    // -----------------------------------------------------------------------
    // 3. Orphaned nodes (warning) -- nodes with no edges (excluding triggers)
    // -----------------------------------------------------------------------
    const connectedNodeIds = new Set<string>()
    for (const edge of edges) {
      connectedNodeIds.add(edge.source)
      connectedNodeIds.add(edge.target)
    }
    const orphanedNodes = nodes.filter(
      (n) => !connectedNodeIds.has(n.id) && n.type !== 'trigger',
    )
    if (orphanedNodes.length > 0) {
      results.push({
        level: 'warning',
        message: `${orphanedNodes.length} orphaned node${orphanedNodes.length > 1 ? 's' : ''} with no connections`,
        nodeIds: orphanedNodes.map((n) => n.id),
      })
    }

    // Also check trigger nodes that have no outgoing edges (they should connect to something)
    if (edges.length > 0) {
      const triggerOrphans = triggerNodes.filter(
        (n) => !edges.some((e) => e.source === n.id),
      )
      if (triggerOrphans.length > 0) {
        results.push({
          level: 'warning',
          message: `${triggerOrphans.length} Trigger node${triggerOrphans.length > 1 ? 's' : ''} with no outgoing connections`,
          nodeIds: triggerOrphans.map((n) => n.id),
        })
      }
    }

    // -----------------------------------------------------------------------
    // 4. Cycle detection (error)
    // -----------------------------------------------------------------------
    const { hasCycle, cycleNodeIds } = detectCycle(nodes, edges)
    if (hasCycle) {
      results.push({
        level: 'error',
        message: 'Cycle detected in workflow graph. Workflows must be acyclic (DAG).',
        nodeIds: cycleNodeIds,
      })
    }

    // -----------------------------------------------------------------------
    // 5. Empty required config (warning)
    // -----------------------------------------------------------------------
    for (const node of nodes) {
      const nodeData = node.data as WorkflowNodeData
      const config = nodeData?.config as Record<string, unknown> | undefined
      if (!config) continue

      switch (node.type) {
        case 'command':
          if (!config.command || (typeof config.command === 'string' && !config.command.trim())) {
            results.push({
              level: 'warning',
              message: `Command node "${nodeData?.label || node.id}" has an empty command`,
              nodeIds: [node.id],
            })
          }
          break
        case 'script':
          if (!config.script || (typeof config.script === 'string' && !config.script.trim())) {
            results.push({
              level: 'warning',
              message: `Script node "${nodeData?.label || node.id}" has an empty script`,
              nodeIds: [node.id],
            })
          }
          break
        case 'conditional':
          if (!config.condition_type) {
            results.push({
              level: 'warning',
              message: `Conditional node "${nodeData?.label || node.id}" has no condition type set`,
              nodeIds: [node.id],
            })
          }
          break
      }
    }

    // -----------------------------------------------------------------------
    // 6. Port type compatibility (warning)
    // -----------------------------------------------------------------------
    for (const edge of edges) {
      const sourceNode = nodes.find((n) => n.id === edge.source)
      const targetNode = nodes.find((n) => n.id === edge.target)
      if (!sourceNode || !targetNode) continue

      const sourceOutputType = NODE_OUTPUT_TYPES[sourceNode.type || ''] || 'any'
      const targetInputType = NODE_INPUT_TYPES[targetNode.type || ''] || 'any'

      if (!areTypesCompatible(sourceOutputType, targetInputType)) {
        results.push({
          level: 'warning',
          message: `Port type mismatch: ${sourceNode.type} outputs "${sourceOutputType}" but ${targetNode.type} expects "${targetInputType}"`,
          nodeIds: [sourceNode.id, targetNode.id],
        })
      }
    }

    return results
  }

  /**
   * Check if a proposed connection is valid.
   */
  function isValidConnection(
    connection: Connection,
    nodes: Node[],
    edges: Edge[],
  ): boolean {
    // No self-connections
    if (connection.source === connection.target) return false

    // No duplicate edges
    const duplicate = edges.some(
      (e) =>
        e.source === connection.source &&
        e.target === connection.target &&
        (e.sourceHandle || null) === (connection.sourceHandle || null) &&
        (e.targetHandle || null) === (connection.targetHandle || null),
    )
    if (duplicate) return false

    // No connections TO a trigger node (triggers have no input)
    const targetNode = nodes.find((n) => n.id === connection.target)
    if (targetNode && targetNode.type === 'trigger') return false

    // Port type compatibility
    const sourceNode = nodes.find((n) => n.id === connection.source)
    if (sourceNode && targetNode) {
      const sourceOutputType = NODE_OUTPUT_TYPES[sourceNode.type || ''] || 'any'
      const targetInputType = NODE_INPUT_TYPES[targetNode.type || ''] || 'any'
      if (!areTypesCompatible(sourceOutputType, targetInputType)) return false
    }

    return true
  }

  return {
    validateGraph,
    isValidConnection,
  }
}
