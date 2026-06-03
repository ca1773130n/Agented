import { describe, it, expect, vi, beforeEach } from 'vitest'
import { applyGeneratedConfig } from '../useTeamGeneration'
import type { GeneratedTeamConfig } from '../../services/api'

vi.mock('../../services/api', () => ({
  teamApi: {
    create: vi.fn(),
    updateTopology: vi.fn(),
    addMember: vi.fn(),
    addAssignment: vi.fn(),
  },
  agentApi: { create: vi.fn() },
  userSkillsApi: { add: vi.fn() },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message = 'err') {
      super(message)
      this.status = status
    }
  },
}))

function makeConfig(over: Partial<GeneratedTeamConfig> = {}): GeneratedTeamConfig {
  return {
    name: 'Squad',
    description: 'A squad',
    topology: 'mesh',
    topology_config: {},
    color: '#abcdef',
    agents: [
      {
        agent_id: null,
        name: 'Alice',
        role: 'lead',
        valid: true,
        assignments: [
          {
            entity_type: 'skill',
            entity_id: 'sk-1',
            entity_name: 'Skill One',
            valid: true,
            needs_creation: true,
          },
        ],
      },
    ],
    ...over,
  } as unknown as GeneratedTeamConfig
}

const deps = { autoAgentDescription: (name: string) => `auto for ${name}` }

describe('applyGeneratedConfig', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    const { teamApi, agentApi, userSkillsApi } = await import('../../services/api')
    vi.mocked(teamApi.create).mockResolvedValue({ team: { id: 'team-1' } } as never)
    vi.mocked(teamApi.updateTopology).mockResolvedValue({} as never)
    vi.mocked(teamApi.addMember).mockResolvedValue({} as never)
    vi.mocked(teamApi.addAssignment).mockResolvedValue({} as never)
    vi.mocked(agentApi.create).mockResolvedValue({ agent_id: 'ag-1' } as never)
    vi.mocked(userSkillsApi.add).mockResolvedValue({} as never)
  })

  it('applies a full config cleanly and reports no issues', async () => {
    const { teamApi } = await import('../../services/api')
    const outcome = await applyGeneratedConfig(makeConfig(), deps)

    expect(outcome.teamId).toBe('team-1')
    expect(outcome.issues).toEqual([])
    expect(outcome.membersAdded).toBe(1)
    expect(outcome.assignmentsAdded).toBe(1)
    // The auto-created agent's id must flow into the assignment call.
    expect(teamApi.addAssignment).toHaveBeenCalledWith('team-1', 'ag-1', expect.objectContaining({ entity_id: 'sk-1' }))
  })

  it('returns a null teamId and attempts nothing else when the team shell has no id', async () => {
    const { teamApi, agentApi } = await import('../../services/api')
    vi.mocked(teamApi.create).mockResolvedValue({ team: undefined } as never)

    const outcome = await applyGeneratedConfig(makeConfig(), deps)

    expect(outcome.teamId).toBeNull()
    expect(outcome.issues).toEqual([])
    expect(agentApi.create).not.toHaveBeenCalled()
    expect(teamApi.addMember).not.toHaveBeenCalled()
  })

  // Regression: the old in-component flow swallowed every per-step failure and
  // still reported success. The outcome must now surface those failures.
  it('records an issue (not silent success) when agent creation fails', async () => {
    const { agentApi, teamApi } = await import('../../services/api')
    vi.mocked(agentApi.create).mockRejectedValue(new Error('500'))

    const outcome = await applyGeneratedConfig(makeConfig(), deps)

    expect(outcome.teamId).toBe('team-1') // shell created...
    expect(outcome.issues).toEqual([{ kind: 'agent', name: 'Alice' }]) // ...but honestly flagged
    expect(outcome.membersAdded).toBe(0)
    expect(teamApi.addMember).not.toHaveBeenCalled()
  })

  it('records member and assignment issues for non-conflict failures', async () => {
    const { teamApi } = await import('../../services/api')
    const cfg = makeConfig({
      agents: [
        {
          agent_id: 'ag-existing',
          name: 'Bob',
          role: 'member',
          valid: true,
          assignments: [
            { entity_type: 'skill', entity_id: 'sk-2', entity_name: 'Skill Two', valid: true, needs_creation: false },
          ],
        },
      ],
    } as unknown as Partial<GeneratedTeamConfig>)
    vi.mocked(teamApi.addMember).mockRejectedValue(new Error('500'))
    vi.mocked(teamApi.addAssignment).mockRejectedValue(new Error('500'))

    const outcome = await applyGeneratedConfig(cfg, deps)

    expect(outcome.issues).toEqual([
      { kind: 'member', name: 'Bob' },
      { kind: 'assignment', name: 'Skill Two' },
    ])
    expect(outcome.membersAdded).toBe(0)
    expect(outcome.assignmentsAdded).toBe(0)
  })

  it('treats 409 conflicts on member/assignment as benign (already exists)', async () => {
    const { teamApi, ApiError } = await import('../../services/api')
    const cfg = makeConfig({
      agents: [
        {
          agent_id: 'ag-existing',
          name: 'Bob',
          role: 'member',
          valid: true,
          assignments: [
            { entity_type: 'skill', entity_id: 'sk-2', entity_name: 'Skill Two', valid: true, needs_creation: false },
          ],
        },
      ],
    } as unknown as Partial<GeneratedTeamConfig>)
    vi.mocked(teamApi.addMember).mockRejectedValue(new ApiError(409, 'conflict'))
    vi.mocked(teamApi.addAssignment).mockRejectedValue(new ApiError(409, 'conflict'))

    const outcome = await applyGeneratedConfig(cfg, deps)

    expect(outcome.issues).toEqual([])
  })

  it('skips assignments explicitly marked invalid', async () => {
    const { teamApi } = await import('../../services/api')
    const cfg = makeConfig({
      agents: [
        {
          agent_id: 'ag-existing',
          name: 'Bob',
          role: 'member',
          valid: true,
          assignments: [
            { entity_type: 'skill', entity_id: 'sk-bad', entity_name: 'Bad', valid: false, needs_creation: true },
          ],
        },
      ],
    } as unknown as Partial<GeneratedTeamConfig>)

    const outcome = await applyGeneratedConfig(cfg, deps)

    expect(teamApi.addAssignment).not.toHaveBeenCalled()
    expect(outcome.assignmentsAdded).toBe(0)
    expect(outcome.issues).toEqual([])
  })
})
