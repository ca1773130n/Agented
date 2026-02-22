import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'
import type { Node, Edge } from '@vue-flow/core'
import type { TopologyType } from '../../../services/api'
import { useTopologyValidation } from '../../../composables/useTopologyValidation'
import { useCanvasLayout } from '../../../composables/useCanvasLayout'

// Mock the api module for component tests
vi.mock('../../../services/api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../../services/api')
  return {
    ...actual,
    teamApi: {
      addMember: vi.fn().mockResolvedValue({ message: 'ok', member: { id: 1 } }),
      removeMember: vi.fn().mockResolvedValue({ message: 'ok' }),
      list: vi.fn().mockResolvedValue({ teams: [] }),
      get: vi.fn(),
      getAllAssignments: vi.fn().mockResolvedValue({ assignments: [] }),
      updateTopology: vi.fn().mockResolvedValue({}),
    },
    agentApi: {
      list: vi.fn().mockResolvedValue({ agents: [] }),
    },
    superAgentApi: {
      list: vi.fn().mockResolvedValue({ super_agents: [] }),
    },
  }
})

// Helper to create mock nodes
function makeNode(id: string, type: string = 'agent'): Node {
  return { id, type, position: { x: 0, y: 0 }, data: { label: id } }
}

// Helper to create mock edges
function makeEdge(source: string, target: string, label?: string): Edge {
  return { id: `e-${source}-${target}`, source, target, type: 'smoothstep', label }
}

describe('useTeamCanvas super_agent nodes', () => {
  it('creates super_agent nodes for members with super_agent_id', async () => {
    // Import useTeamCanvas inside test to ensure mocks are applied
    const { useTeamCanvas } = await import('../../../composables/useTeamCanvas')

    const team = ref({
      id: 'team-abc',
      name: 'Test',
      color: '#6366f1',
      topology: null,
      topology_config: '{}',
    } as any)
    const members = ref([
      { id: 1, team_id: 'team-abc', name: 'SA Leader', super_agent_id: 'sa-001', role: 'lead' },
    ])
    const assignments = ref([])

    const { nodes, syncFromTeam } = useTeamCanvas(team, members, assignments)
    syncFromTeam()

    expect(nodes.value).toHaveLength(1)
    expect(nodes.value[0].type).toBe('super_agent')
    expect(nodes.value[0].id).toBe('sa-001')
    expect((nodes.value[0].data as any).superAgentId).toBe('sa-001')
  })

  it('creates agent nodes for regular members', async () => {
    const { useTeamCanvas } = await import('../../../composables/useTeamCanvas')

    const team = ref({
      id: 'team-abc',
      name: 'Test',
      color: '#6366f1',
      topology: null,
      topology_config: '{}',
    } as any)
    const members = ref([
      { id: 2, team_id: 'team-abc', name: 'Agent Worker', agent_id: 'agent-001', role: 'member' },
    ])
    const assignments = ref([])

    const { nodes, syncFromTeam } = useTeamCanvas(team, members, assignments)
    syncFromTeam()

    expect(nodes.value).toHaveLength(1)
    expect(nodes.value[0].type).toBe('agent')
    expect(nodes.value[0].id).toBe('agent-001')
    expect((nodes.value[0].data as any).agentId).toBe('agent-001')
  })
})

describe('useTeamCanvas syncToTeam topology inference', () => {
  it('infers hierarchical for multi-level tree (A->B->D, A->C)', async () => {
    const { useTeamCanvas } = await import('../../../composables/useTeamCanvas')

    const team = ref({
      id: 'team-abc',
      name: 'Test',
      color: '#6366f1',
      topology: null,
      topology_config: '{}',
    } as any)
    const members = ref([
      { id: 1, team_id: 'team-abc', name: 'A', agent_id: 'a', role: 'lead' },
      { id: 2, team_id: 'team-abc', name: 'B', agent_id: 'b', role: 'member' },
      { id: 3, team_id: 'team-abc', name: 'C', agent_id: 'c', role: 'member' },
      { id: 4, team_id: 'team-abc', name: 'D', agent_id: 'd', role: 'member' },
    ])
    const assignments = ref([])

    const { nodes, edges, syncToTeam } = useTeamCanvas(team, members, assignments)

    // Multi-level tree: A -> B -> D, A -> C (not a hub-spoke because B has peer edge to D)
    nodes.value = [
      makeNode('a'),
      makeNode('b'),
      makeNode('c'),
      makeNode('d'),
    ]
    edges.value = [
      makeEdge('a', 'b'),
      makeEdge('a', 'c'),
      makeEdge('b', 'd'),
    ]

    const result = syncToTeam()
    expect(result.topology).toBe('hierarchical')
  })

  it('preserves generator_critic for bidirectional 2-node graph', async () => {
    const { useTeamCanvas } = await import('../../../composables/useTeamCanvas')

    const team = ref({
      id: 'team-abc',
      name: 'Test',
      color: '#6366f1',
      topology: null,
      topology_config: '{}',
    } as any)
    const members = ref([
      { id: 1, team_id: 'team-abc', name: 'Gen', agent_id: 'gen', role: 'member' },
      { id: 2, team_id: 'team-abc', name: 'Crit', agent_id: 'crit', role: 'member' },
    ])
    const assignments = ref([])

    const { nodes, edges, syncToTeam } = useTeamCanvas(team, members, assignments)

    nodes.value = [makeNode('gen'), makeNode('crit')]
    edges.value = [makeEdge('gen', 'crit'), makeEdge('crit', 'gen')]

    const result = syncToTeam()
    expect(result.topology).toBe('generator_critic')
  })
})

describe('useTopologyValidation', () => {
  it('accepts super_agent-to-agent connections', () => {
    const nodes = ref<Node[]>([
      makeNode('sa-001', 'super_agent'),
      makeNode('agent-001', 'agent'),
    ])
    const edges = ref<Edge[]>([])

    const { isValidConnection } = useTopologyValidation(nodes, edges)

    const result = isValidConnection({
      source: 'sa-001',
      target: 'agent-001',
      sourceHandle: null,
      targetHandle: null,
    })
    expect(result).toBe(true)
  })

  it('rejects connections from non-agent types', () => {
    const nodes = ref<Node[]>([
      makeNode('trigger-001', 'trigger'),
      makeNode('agent-001', 'agent'),
    ])
    const edges = ref<Edge[]>([])

    const { isValidConnection } = useTopologyValidation(nodes, edges)

    const result = isValidConnection({
      source: 'trigger-001',
      target: 'agent-001',
      sourceHandle: null,
      targetHandle: null,
    })
    expect(result).toBe(false)
  })

  it('infers hierarchical topology for tree-shaped graph', () => {
    // Tree: root -> child1 -> grandchild1, root -> child2 -> grandchild2
    const nodes = ref<Node[]>([
      makeNode('root'),
      makeNode('child1'),
      makeNode('child2'),
      makeNode('gc1'),
      makeNode('gc2'),
    ])
    const edges = ref<Edge[]>([
      makeEdge('root', 'child1'),
      makeEdge('root', 'child2'),
      makeEdge('child1', 'gc1'),
      makeEdge('child2', 'gc2'),
    ])

    const { inferredTopology } = useTopologyValidation(nodes, edges)
    expect(inferredTopology.value).toBe('hierarchical')
  })
})

describe('useCanvasLayout', () => {
  it('accepts ranker parameter without errors', () => {
    const { layoutNodes } = useCanvasLayout()

    const nodes: Node[] = [
      makeNode('a'),
      makeNode('b'),
      makeNode('c'),
    ]
    const edges: Edge[] = [
      makeEdge('a', 'b'),
      makeEdge('a', 'c'),
    ]

    const result = layoutNodes(nodes, edges, 'TB', 'tight-tree')
    expect(result).toHaveLength(3)
    // All nodes should have positions set (not all at 0,0)
    const positions = result.map(n => n.position)
    const hasDistinctPositions = positions.some(p => p.x !== 0 || p.y !== 0)
    expect(hasDistinctPositions).toBe(true)
  })
})

describe('buildEdgesFromTopology', () => {
  it('builds delegation edges for hierarchical topology', async () => {
    const { useTeamCanvas } = await import('../../../composables/useTeamCanvas')

    const team = ref({
      id: 'team-abc',
      name: 'Test',
      color: '#6366f1',
      topology: 'hierarchical' as TopologyType,
      topology_config: JSON.stringify({ lead: 'a' }),
    } as any)
    const members = ref([
      { id: 1, team_id: 'team-abc', name: 'A', agent_id: 'a', role: 'lead' },
      { id: 2, team_id: 'team-abc', name: 'B', agent_id: 'b', role: 'member' },
      { id: 3, team_id: 'team-abc', name: 'C', agent_id: 'c', role: 'member' },
    ])
    const assignments = ref([])

    const { edges, syncFromTeam } = useTeamCanvas(team, members, assignments)
    syncFromTeam()

    // Hierarchical fallback: star from lead to all others with 'delegation' labels
    expect(edges.value.length).toBeGreaterThanOrEqual(2)
    for (const edge of edges.value) {
      expect(edge.data?.label).toBe('delegation')
      expect(edge.type).toBe('messageFlow')
    }
  })

  it('builds handoff and approval edges for human_in_loop topology', async () => {
    const { useTeamCanvas } = await import('../../../composables/useTeamCanvas')

    const team = ref({
      id: 'team-abc',
      name: 'Test',
      color: '#6366f1',
      topology: 'human_in_loop' as TopologyType,
      topology_config: JSON.stringify({
        order: ['a', 'b', 'c'],
        approval_nodes: ['b'],
      }),
    } as any)
    const members = ref([
      { id: 1, team_id: 'team-abc', name: 'A', agent_id: 'a', role: 'member' },
      { id: 2, team_id: 'team-abc', name: 'B', agent_id: 'b', role: 'member' },
      { id: 3, team_id: 'team-abc', name: 'C', agent_id: 'c', role: 'member' },
    ])
    const assignments = ref([])

    const { edges, syncFromTeam } = useTeamCanvas(team, members, assignments)
    syncFromTeam()

    expect(edges.value).toHaveLength(2)
    // Edge a->b should be 'approval' (b is approval node)
    const abEdge = edges.value.find(e => e.source === 'a' && e.target === 'b')
    expect(abEdge?.data?.label).toBe('approval')
    expect(abEdge?.type).toBe('messageFlow')
    // Edge b->c should be 'handoff' (c is not approval node)
    const bcEdge = edges.value.find(e => e.source === 'b' && e.target === 'c')
    expect(bcEdge?.data?.label).toBe('handoff')
    expect(bcEdge?.type).toBe('messageFlow')
  })
})

describe('TopologyType includes new types', () => {
  it('hierarchical, human_in_loop, and composite are valid TopologyType values', () => {
    // TypeScript compilation test: these assignments would fail if the types were invalid
    const h: TopologyType = 'hierarchical'
    const hil: TopologyType = 'human_in_loop'
    const c: TopologyType = 'composite'
    expect(h).toBe('hierarchical')
    expect(hil).toBe('human_in_loop')
    expect(c).toBe('composite')
  })
})

describe('CanvasSidebar renders SuperAgents section', () => {
  it('renders SuperAgents header and items', async () => {
    const CanvasSidebar = (await import('../CanvasSidebar.vue')).default

    const wrapper = mount(CanvasSidebar, {
      props: {
        availableAgents: [
          { id: 'agent-001', name: 'Worker Agent', color: '#00d4ff' },
        ],
        availableSuperAgents: [
          { id: 'sa-001', name: 'Lead SA' },
          { id: 'sa-002', name: 'Research SA' },
        ],
      },
    })

    // Check that both sections exist
    expect(wrapper.text()).toContain('Agents')
    expect(wrapper.text()).toContain('SuperAgents')
    expect(wrapper.text()).toContain('Worker Agent')
    expect(wrapper.text()).toContain('Lead SA')
    expect(wrapper.text()).toContain('Research SA')

    // Check that there are 3 drag items total (1 agent + 2 super agents)
    const dragItems = wrapper.findAll('.agent-drag-item')
    expect(dragItems).toHaveLength(3)
  })
})
