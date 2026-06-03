import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import TeamsPage from '../TeamsPage.vue'
import type { Team } from '../../services/api'

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
})
