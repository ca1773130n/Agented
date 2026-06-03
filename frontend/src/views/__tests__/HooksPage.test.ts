import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import HooksPage from '../HooksPage.vue'
import type { Hook } from '../../services/api'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ query: {}, params: {}, hash: '' }),
}))

// Sorted ascending by name (useListFilter default), so 'Alpha Guard' renders
// first. Delete is still targeted by name to stay robust against ordering.
const mockHooks = [
  { id: 1, name: 'Alpha Guard', event: 'PreToolUse', description: 'Blocks bad tools', content: '', enabled: true, project_id: null, source_path: null, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
  { id: 2, name: 'Beta Logger', event: 'PostToolUse', description: 'Logs results', content: '', enabled: false, project_id: null, source_path: null, created_at: '2026-01-02T00:00:00Z', updated_at: '2026-01-02T00:00:00Z' },
] as unknown as Hook[]

vi.mock('../../services/api', () => ({
  hookApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) { super(message); this.status = status }
  },
}))

describe('HooksPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(HooksPage, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { hookApi } = await import('../../services/api')
    vi.mocked(hookApi.list).mockResolvedValue({ hooks: mockHooks, total_count: mockHooks.length })
    vi.mocked(hookApi.delete).mockResolvedValue({ message: 'Deleted' })
  })

  it('renders the loading state initially', async () => {
    const { hookApi } = await import('../../services/api')
    vi.mocked(hookApi.list).mockReturnValue(new Promise(() => {}))
    const wrapper = mountComponent()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
  })

  it('renders the hook list after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.text()).toContain('Alpha Guard')
    expect(wrapper.text()).toContain('Beta Logger')
    expect(wrapper.findAll('.hook-card').length).toBe(2)
  })

  it('shows the empty state when there are no hooks', async () => {
    const { hookApi } = await import('../../services/api')
    vi.mocked(hookApi.list).mockResolvedValue({ hooks: [], total_count: 0 })
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
  })

  it('shows the error state and re-fetches on retry', async () => {
    const { hookApi, ApiError } = await import('../../services/api')
    vi.mocked(hookApi.list).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(true)
    expect(mockShowToast).toHaveBeenCalledWith('boom', 'error')

    vi.mocked(hookApi.list).mockResolvedValueOnce({ hooks: mockHooks, total_count: mockHooks.length })
    await wrapper.find('.ds-error-state button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(false)
    expect(wrapper.text()).toContain('Alpha Guard')
    expect(hookApi.list).toHaveBeenCalledTimes(2)
  })

  it('deletes a hook after confirmation', async () => {
    const { hookApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Cards may sort, so target by name rather than index.
    const alphaCard = wrapper.findAll('.hook-card').find((c) => c.text().includes('Alpha Guard'))
    expect(alphaCard).toBeDefined()
    await alphaCard!.find('.btn-danger').trigger('click')
    await flushPromises()

    // ConfirmModal danger variant -> .btn-danger inside .confirm-actions.
    await wrapper.find('.confirm-actions .btn-danger').trigger('click')
    await flushPromises()

    expect(hookApi.delete).toHaveBeenCalledWith(1)
  })
})
