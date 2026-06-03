import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import RulesPage from '../RulesPage.vue'
import type { Rule } from '../../services/api'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ query: {}, params: {}, hash: '' }),
}))

const mockRules = [
  { id: 1, name: 'No Force Push', description: 'Block force pushes', rule_type: 'pre_check', condition: '', action: '', enabled: 1, project_id: undefined, created_at: '2026-01-01T00:00:00Z' },
  { id: 2, name: 'Require Tests', description: 'Tests must pass', rule_type: 'validation', condition: '', action: '', enabled: 1, project_id: undefined, created_at: '2026-01-02T00:00:00Z' },
] as unknown as Rule[]

vi.mock('../../services/api', () => ({
  ruleApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
  // useStreamingGeneration imports isAbortError from this module at load time.
  isAbortError: (e: unknown) => e instanceof DOMException && e.name === 'AbortError',
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) { super(message); this.status = status }
  },
}))

describe('RulesPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(RulesPage, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { ruleApi } = await import('../../services/api')
    vi.mocked(ruleApi.list).mockResolvedValue({ rules: mockRules, total_count: mockRules.length })
    vi.mocked(ruleApi.delete).mockResolvedValue({ message: 'Deleted' })
  })

  it('renders the loading state initially', async () => {
    const { ruleApi } = await import('../../services/api')
    vi.mocked(ruleApi.list).mockReturnValue(new Promise(() => {}))
    const wrapper = mountComponent()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
  })

  it('renders the rule list after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.text()).toContain('No Force Push')
    expect(wrapper.text()).toContain('Require Tests')
    expect(wrapper.findAll('.rule-card').length).toBe(2)
  })

  it('shows the empty state when there are no rules', async () => {
    const { ruleApi } = await import('../../services/api')
    vi.mocked(ruleApi.list).mockResolvedValue({ rules: [], total_count: 0 })
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
  })

  it('shows the error state and re-fetches on retry', async () => {
    const { ruleApi, ApiError } = await import('../../services/api')
    vi.mocked(ruleApi.list).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(true)
    expect(mockShowToast).toHaveBeenCalledWith('boom', 'error')

    vi.mocked(ruleApi.list).mockResolvedValueOnce({ rules: mockRules, total_count: mockRules.length })
    await wrapper.find('.ds-error-state button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(false)
    expect(wrapper.text()).toContain('No Force Push')
    expect(ruleApi.list).toHaveBeenCalledTimes(2)
  })

  it('deletes a rule after confirmation', async () => {
    const { ruleApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Target by name rather than index — the list is sorted by useListFilter.
    const card = wrapper.findAll('.rule-card').find((c) => c.text().includes('No Force Push'))
    expect(card).toBeDefined()
    await card!.find('.btn-danger').trigger('click')
    await flushPromises()

    // ConfirmModal renders its confirm action as `.confirm-actions .btn-danger` (variant=danger).
    await wrapper.find('.confirm-actions .btn-danger').trigger('click')
    await flushPromises()

    expect(ruleApi.delete).toHaveBeenCalledWith(1)
  })
})
