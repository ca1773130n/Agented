import { ref, type Ref } from 'vue'
import type { Node, Edge } from '@vue-flow/core'
import { projectApi, teamApi } from '../services/api'
import type { ProjectTeamEdge, CanvasEdgeType } from '../services/api'

export interface TeamNodeData {
  label: string
  color: string
  memberCount: number
  teamId: string
  leaderName?: string
  tierCounts?: { leader: number; senior: number; member: number }
}

export function useOrgCanvas(projectId: Ref<string>) {
  const nodes = ref<Node<TeamNodeData>[]>([])
  const edges = ref<Edge[]>([])
  const savedEdges = ref<ProjectTeamEdge[]>([])
  const isLoading = ref(false)

  function buildNodes(teams: { id: string; name: string; color: string; members?: any[] }[]) {
    nodes.value = teams.map((team, i) => {
      const members = team.members || []
      const leader = members.find((m: any) => m.tier === 'leader' || m.role === 'lead')
      const tierCounts = {
        leader: members.filter((m: any) => m.tier === 'leader').length,
        senior: members.filter((m: any) => m.tier === 'senior').length,
        member: members.filter((m: any) => !m.tier || m.tier === 'member').length,
      }
      return {
        id: team.id,
        type: 'team' as const,
        position: { x: i * 240, y: 0 },
        data: {
          label: team.name,
          color: team.color || '#00d4ff',
          memberCount: members.length,
          teamId: team.id,
          leaderName: leader?.name,
          tierCounts,
        },
      }
    })
  }

  function buildEdgesFromSaved() {
    edges.value = savedEdges.value.map((e) => ({
      id: `pte-${e.id}`,
      source: e.source_team_id,
      target: e.target_team_id,
      type: 'messageFlow' as const,
      animated: e.edge_type === 'inter_team' || e.edge_type === 'command',
      label: e.label || undefined,
      data: {
        edge_type: (e.edge_type || 'inter_team') as CanvasEdgeType,
        label: e.label,
        edgeId: e.id,
      },
    }))
  }

  async function loadEdges() {
    try {
      const resp = await projectApi.listTeamEdges(projectId.value)
      savedEdges.value = resp.edges || []
      buildEdgesFromSaved()
    } catch {
      savedEdges.value = []
    }
  }

  async function saveEdges() {
    // Delete old edges
    const existing = savedEdges.value
    for (const e of existing) {
      await projectApi.deleteTeamEdge(projectId.value, e.id)
    }

    // Also clean up old team_connections (best-effort)
    for (const e of existing) {
      try {
        const conns = await teamApi.listConnections(e.source_team_id)
        const matching = (conns.connections || []).find(
          (c) => c.target_team_id === e.target_team_id
        )
        if (matching) {
          await teamApi.deleteConnection(e.source_team_id, matching.id)
        }
      } catch {
        // team_connections cleanup is best-effort
      }
    }

    // Recreate from current edges
    for (const edge of edges.value) {
      const edgeType = (edge.data?.edge_type || 'inter_team') as string
      const label = edge.data?.label || (typeof edge.label === 'string' ? edge.label : undefined)
      await projectApi.createTeamEdge(projectId.value, {
        source_team_id: edge.source,
        target_team_id: edge.target,
        edge_type: edgeType,
        label,
      })

      // Dual-write to team_connections (SC#4 compliance)
      try {
        await teamApi.createConnection(edge.source, {
          target_team_id: edge.target,
          connection_type: edgeType,
        })
      } catch {
        // team_connections dual-write is best-effort
      }
    }

    // Reload to get fresh IDs
    await loadEdges()
  }

  async function savePositions() {
    const positions: Record<string, { x: number; y: number }> = {}
    for (const node of nodes.value) {
      positions[node.id] = { x: node.position.x, y: node.position.y }
    }
    await projectApi.updateTeamTopologyConfig(projectId.value, { positions })
  }

  async function loadPositions() {
    try {
      const project = await projectApi.get(projectId.value)
      const config = project.team_topology_config
        ? (typeof project.team_topology_config === 'string'
          ? JSON.parse(project.team_topology_config)
          : project.team_topology_config)
        : null
      if (config?.positions) {
        nodes.value = nodes.value.map((n) => ({
          ...n,
          position: config.positions[n.id] || n.position,
        }))
      }
      return !!config?.positions
    } catch {
      return false
    }
  }

  return {
    nodes,
    edges,
    savedEdges,
    isLoading,
    buildNodes,
    buildEdgesFromSaved,
    loadEdges,
    saveEdges,
    savePositions,
    loadPositions,
  }
}
