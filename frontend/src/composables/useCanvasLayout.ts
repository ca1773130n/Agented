import dagre from '@dagrejs/dagre'
const { graphlib, layout } = dagre
import type { Node, Edge } from '@vue-flow/core'

const NODE_WIDTH = 220
const NODE_HEIGHT = 140

export function useCanvasLayout() {
  function layoutNodes(
    nodes: Node[],
    edges: Edge[],
    direction: 'TB' | 'LR' = 'TB',
    ranker: 'network-simplex' | 'tight-tree' | 'longest-path' = 'network-simplex',
    tierMap?: Record<string, 'leader' | 'senior' | 'member'>,
  ): Node[] {
    if (nodes.length === 0) return []

    const g = new graphlib.Graph()
    g.setDefaultEdgeLabel(() => ({}))
    g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 100, ranker })

    const tierRank: Record<string, number> = { leader: 0, senior: 1, member: 2 }

    for (const node of nodes) {
      const nodeOpts: Record<string, any> = { width: NODE_WIDTH, height: NODE_HEIGHT }
      if (tierMap && tierMap[node.id]) {
        nodeOpts.rank = tierRank[tierMap[node.id]]
      }
      g.setNode(node.id, nodeOpts)
    }

    for (const edge of edges) {
      g.setEdge(edge.source, edge.target)
    }

    layout(g)

    return nodes.map((node) => {
      const nodeWithPosition = g.node(node.id)
      if (!nodeWithPosition) return node

      return {
        ...node,
        position: {
          x: nodeWithPosition.x - NODE_WIDTH / 2,
          y: nodeWithPosition.y - NODE_HEIGHT / 2,
        },
      }
    })
  }

  return { layoutNodes }
}
