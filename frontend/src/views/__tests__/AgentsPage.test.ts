import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import AgentsPage from '../AgentsPage.vue'
import type { Agent } from '../../services/api'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ query: {}, params: {}, hash: '' }),
}))

const mockAgents = [
  { id: 'agent-1', name: 'Reviewer', description: 'Reviews PRs', role: 'reviewer', enabled: 1, backend_type: 'claude', created_at: '2026-01-01T00:00:00Z' },
  { id: 'agent-2', name: 'Scanner', description: 'Scans code', role: 'scanner', enabled: 0, backend_type: 'opencode', created_at: '2026-01-02T00:00:00Z' },
] as unknown as Agent[]

vi.mock('../../services/api', () => ({
  agentApi: { list: vi.fn(), run: vi.fn(), delete: vi.fn(), update: vi.fn() },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) { super(message); this.status = status }
  },
}))

describe('AgentsPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(AgentsPage, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { agentApi } = await import('../../services/api')
    vi.mocked(agentApi.list).mockResolvedValue({ agents: mockAgents })
    vi.mocked(agentApi.run).mockResolvedValue({ message: 'Started', agent_id: 'agent-1', execution_id: 'exec-1', status: 'running' })
    vi.mocked(agentApi.delete).mockResolvedValue({ message: 'Deleted' })
    vi.mocked(agentApi.update).mockResolvedValue({ message: 'Updated' })
  })

  it('renders the loading state initially', async () => {
    const { agentApi } = await import('../../services/api')
    vi.mocked(agentApi.list).mockReturnValue(new Promise(() => {}))
    const wrapper = mountComponent()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
  })

  it('renders the agent list after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.text()).toContain('Reviewer')
    expect(wrapper.text()).toContain('Scanner')
    expect(wrapper.findAll('.agent-card').length).toBe(2)
  })

  it('shows the empty state when there are no agents', async () => {
    const { agentApi } = await import('../../services/api')
    vi.mocked(agentApi.list).mockResolvedValue({ agents: [] })
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
  })

  it('shows the error state and re-fetches on retry', async () => {
    const { agentApi, ApiError } = await import('../../services/api')
    vi.mocked(agentApi.list).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(true)
    expect(mockShowToast).toHaveBeenCalledWith('boom', 'error')

    vi.mocked(agentApi.list).mockResolvedValueOnce({ agents: mockAgents })
    await wrapper.find('.ds-error-state button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(false)
    expect(wrapper.text()).toContain('Reviewer')
    expect(agentApi.list).toHaveBeenCalledTimes(2)
  })

  it('runs an enabled agent', async () => {
    const { agentApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // First agent is enabled -> its run (.btn-success) is clickable.
    await wrapper.findAll('.agent-card .btn-success')[0].trigger('click')
    await flushPromises()

    expect(agentApi.run).toHaveBeenCalledWith('agent-1')
  })

  it('deletes an agent after confirmation', async () => {
    const { agentApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    await wrapper.findAll('.agent-card .btn-danger')[0].trigger('click')
    await flushPromises()

    await wrapper.find('.confirm-actions .btn-danger').trigger('click')
    await flushPromises()

    expect(agentApi.delete).toHaveBeenCalledWith('agent-1')
  })
})
