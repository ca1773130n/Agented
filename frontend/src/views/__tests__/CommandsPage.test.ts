import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import CommandsPage from '../CommandsPage.vue'
import type { Command } from '../../services/api'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ query: {}, params: {}, hash: '' }),
}))

const mockCommands = [
  { id: 1, name: 'deploy', description: 'Deploy app', content: '', arguments: '', enabled: 1, project_id: undefined, created_at: '2026-01-01T00:00:00Z' },
  { id: 2, name: 'rollback', description: 'Roll back', content: '', arguments: '', enabled: 1, project_id: undefined, created_at: '2026-01-02T00:00:00Z' },
] as unknown as Command[]

vi.mock('../../services/api', () => ({
  commandApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) { super(message); this.status = status }
  },
}))

describe('CommandsPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(CommandsPage, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { commandApi } = await import('../../services/api')
    vi.mocked(commandApi.list).mockResolvedValue({ commands: mockCommands, total_count: mockCommands.length })
    vi.mocked(commandApi.delete).mockResolvedValue({ message: 'Deleted' })
  })

  it('renders the loading state initially', async () => {
    const { commandApi } = await import('../../services/api')
    vi.mocked(commandApi.list).mockReturnValue(new Promise(() => {}))
    const wrapper = mountComponent()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
  })

  it('renders the command list after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.text()).toContain('deploy')
    expect(wrapper.text()).toContain('rollback')
    expect(wrapper.findAll('.command-card').length).toBe(2)
  })

  it('shows the empty state when there are no commands', async () => {
    const { commandApi } = await import('../../services/api')
    vi.mocked(commandApi.list).mockResolvedValue({ commands: [], total_count: 0 })
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
  })

  it('shows the error state and re-fetches on retry', async () => {
    const { commandApi, ApiError } = await import('../../services/api')
    vi.mocked(commandApi.list).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(true)
    expect(mockShowToast).toHaveBeenCalledWith('boom', 'error')

    vi.mocked(commandApi.list).mockResolvedValueOnce({ commands: mockCommands, total_count: mockCommands.length })
    await wrapper.find('.ds-error-state button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(false)
    expect(wrapper.text()).toContain('deploy')
    expect(commandApi.list).toHaveBeenCalledTimes(2)
  })

  it('deletes a command after confirmation', async () => {
    const { commandApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Cards may sort, so target by name rather than index.
    const deployCard = wrapper.findAll('.command-card').find((c) => c.text().includes('deploy'))
    expect(deployCard).toBeDefined()
    await deployCard!.find('.btn-danger').trigger('click')
    await flushPromises()

    await wrapper.find('.confirm-actions .btn-danger').trigger('click')
    await flushPromises()

    expect(commandApi.delete).toHaveBeenCalledWith(1)
  })
})
