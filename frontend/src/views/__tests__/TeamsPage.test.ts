import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import TeamsPage from '../TeamsPage.vue'
import type { Team } from '../../services/api'

// Streaming generation is mocked so the generate flow resolves synchronously.
const mockStartStream = vi.fn()
vi.mock('../../composables/useStreamingGeneration', () => ({
  useStreamingGeneration: () => ({ log: ref([]), phase: ref(''), startStream: mockStartStream }),
}))

// The multi-step apply is unit-tested on its own; here we drive the page's
// outcome-reporting branch, so stub it to return a controlled outcome.
const mockApply = vi.fn()
vi.mock('../../composables/useTeamGeneration', () => ({
  applyGeneratedConfig: (...args: unknown[]) => mockApply(...args),
}))

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ query: {}, params: {}, hash: '' }),
}))

const mockTeams = [
  { id: 'team-1', name: 'Alpha Squad', description: 'First', color: '#aaa', created_at: '2026-01-01T00:00:00Z', member_count: 2 },
  { id: 'team-2', name: 'Bravo Squad', description: 'Second', color: '#bbb', created_at: '2026-01-02T00:00:00Z', member_count: 0 },
] as unknown as Team[]

vi.mock('../../services/api', () => ({
  teamApi: {
    list: vi.fn(),
    create: vi.fn(),
    delete: vi.fn(),
    updateTopology: vi.fn(),
    addMember: vi.fn(),
    addAssignment: vi.fn(),
  },
  agentApi: { list: vi.fn(), create: vi.fn() },
  userSkillsApi: { add: vi.fn() },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) { super(message); this.status = status }
  },
}))

describe('TeamsPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(TeamsPage, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { teamApi, agentApi } = await import('../../services/api')
    vi.mocked(teamApi.list).mockResolvedValue({ teams: mockTeams, total_count: 2 } as never)
    vi.mocked(agentApi.list).mockResolvedValue({ agents: [] } as never)
  })

  it('renders the loading state initially', async () => {
    const { teamApi } = await import('../../services/api')
    vi.mocked(teamApi.list).mockReturnValue(new Promise(() => {}) as never)
    const wrapper = mountComponent()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
  })

  it('renders the team list after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.text()).toContain('Alpha Squad')
    expect(wrapper.text()).toContain('Bravo Squad')
    expect(wrapper.findAll('.team-card').length).toBe(2)
  })

  it('shows the empty state when there are no teams', async () => {
    const { teamApi } = await import('../../services/api')
    vi.mocked(teamApi.list).mockResolvedValue({ teams: [], total_count: 0 } as never)
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
  })

  it('shows the error state and re-fetches on retry', async () => {
    const { teamApi, ApiError } = await import('../../services/api')
    vi.mocked(teamApi.list).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(true)
    expect(mockShowToast).toHaveBeenCalledWith('boom', 'error')

    vi.mocked(teamApi.list).mockResolvedValueOnce({ teams: mockTeams, total_count: 2 } as never)
    await wrapper.find('.ds-error-state button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(false)
    expect(wrapper.text()).toContain('Alpha Squad')
    expect(teamApi.list).toHaveBeenCalledTimes(2)
  })

  // Page-level wiring of the silent-failure fix: when applyGeneratedConfig
  // reports issues, the page must surface an ERROR toast (not the success one).
  it('reports an error toast when the generated config applies with issues', async () => {
    const genConfig = {
      name: 'Generated', description: '', topology: 'mesh', topology_config: {}, color: '#123', agents: [],
    }
    mockStartStream.mockResolvedValue({ config: genConfig, warnings: [] })
    mockApply.mockResolvedValue({ teamId: 'team-9', issues: [{ kind: 'agent', name: 'X' }], membersAdded: 0, assignmentsAdded: 0 })

    const wrapper = mount(TeamsPage, {
      global: {
        provide: { showToast: mockShowToast },
        stubs: {
          teleport: true,
          // Decouple from the real review UI — just expose a save trigger.
          TeamConfigReview: { name: 'TeamConfigReview', template: '<button class="stub-save" @click="$emit(\'save\', config)"></button>', props: ['config'] },
        },
      },
    })
    await flushPromises()

    // Open generate modal, enter a long-enough description, submit.
    await wrapper.find('.btn-ai').trigger('click')
    await wrapper.find('textarea').setValue('a description that is long enough')
    await wrapper.findAll('.btn-ai').at(-1)!.trigger('click')
    await flushPromises()

    // Generated config is now under review — trigger save.
    await wrapper.find('.stub-save').trigger('click')
    await flushPromises()

    expect(mockApply).toHaveBeenCalledTimes(1)
    expect(mockShowToast).toHaveBeenCalledWith(expect.any(String), 'error')
    // And NOT a success toast.
    expect(mockShowToast).not.toHaveBeenCalledWith(expect.any(String), 'success')
  })

  it('reports a success toast when the generated config applies cleanly', async () => {
    const genConfig = {
      name: 'Generated', description: '', topology: 'mesh', topology_config: {}, color: '#123', agents: [],
    }
    mockStartStream.mockResolvedValue({ config: genConfig, warnings: [] })
    mockApply.mockResolvedValue({ teamId: 'team-9', issues: [], membersAdded: 1, assignmentsAdded: 1 })

    const wrapper = mount(TeamsPage, {
      global: {
        provide: { showToast: mockShowToast },
        stubs: {
          teleport: true,
          TeamConfigReview: { name: 'TeamConfigReview', template: '<button class="stub-save" @click="$emit(\'save\', config)"></button>', props: ['config'] },
        },
      },
    })
    await flushPromises()

    await wrapper.find('.btn-ai').trigger('click')
    await wrapper.find('textarea').setValue('a description that is long enough')
    await wrapper.findAll('.btn-ai').at(-1)!.trigger('click')
    await flushPromises()

    await wrapper.find('.stub-save').trigger('click')
    await flushPromises()

    expect(mockShowToast).toHaveBeenCalledWith(expect.any(String), 'success')
    expect(mockShowToast).not.toHaveBeenCalledWith(expect.any(String), 'error')
  })
})
