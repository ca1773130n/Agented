import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import FindingsTriageBoardPage from '../FindingsTriageBoardPage.vue'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ query: {}, params: {} }),
}))

const mockFindings = [
  { id: 'find-1', title: 'SQL injection risk', severity: 'critical', status: 'open', bot: 'bot-security', owner: null, created_at: '2026-01-01T00:00:00Z' },
  { id: 'find-2', title: 'Unused import', severity: 'low', status: 'in_progress', bot: 'bot-pr-review', owner: 'me', created_at: '2026-01-02T00:00:00Z' },
]

vi.mock('../../services/api', () => ({
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) { super(message); this.status = status }
  },
}))

vi.mock('../../services/api/findings', () => ({
  findingsApi: { list: vi.fn(), update: vi.fn() },
}))

describe('FindingsTriageBoardPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(FindingsTriageBoardPage, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { findingsApi } = await import('../../services/api/findings')
    vi.mocked(findingsApi.list).mockResolvedValue({ findings: mockFindings } as never)
    vi.mocked(findingsApi.update).mockResolvedValue({} as never)
  })

  it('renders the loading state while findings load (board not shown yet)', async () => {
    const { findingsApi } = await import('../../services/api/findings')
    vi.mocked(findingsApi.list).mockReturnValue(new Promise(() => {}) as never)
    const wrapper = mountComponent()
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
    expect(wrapper.find('.kanban-board').exists()).toBe(false)
  })

  it('renders the kanban board with findings after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.kanban-board').exists()).toBe(true)
    expect(wrapper.text()).toContain('SQL injection risk')
    expect(wrapper.text()).toContain('Unused import')
  })

  // Regression: a failed load used to render an EMPTY kanban (looks like "no
  // findings"); it must now show a distinct error state instead.
  it('shows a distinct error state (not an empty board) when loading fails, and retries', async () => {
    const { findingsApi } = await import('../../services/api/findings')
    const { ApiError } = await import('../../services/api')
    vi.mocked(findingsApi.list).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(true)
    expect(wrapper.find('.kanban-board').exists()).toBe(false)
    expect(mockShowToast).toHaveBeenCalledWith('boom', 'error')

    vi.mocked(findingsApi.list).mockResolvedValueOnce({ findings: mockFindings } as never)
    await wrapper.find('.ds-error-state button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(false)
    expect(wrapper.find('.kanban-board').exists()).toBe(true)
    expect(findingsApi.list).toHaveBeenCalledTimes(2)
  })
})
