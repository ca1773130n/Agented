import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import UsageHistoryPage from '../UsageHistoryPage.vue'
import type { HistoryStatsPeriod } from '../../services/api'

const mockPeriods = [
  {
    period_start: '2026-01-01',
    total_cost_usd: 12.5,
    total_input_tokens: 1_000_000,
    total_output_tokens: 500_000,
    total_cache_read_tokens: 0,
    total_cache_creation_tokens: 0,
    execution_count: 7,
    avg_rate_limit_pct: 10,
    max_rate_limit_pct: 20,
    snapshot_count: 3,
  },
] as unknown as HistoryStatsPeriod[]

vi.mock('../../services/api', () => ({
  budgetApi: { getHistoryStats: vi.fn() },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) { super(message); this.status = status }
  },
}))

describe('UsageHistoryPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(UsageHistoryPage, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { budgetApi } = await import('../../services/api')
    vi.mocked(budgetApi.getHistoryStats).mockResolvedValue({ periods: mockPeriods } as never)
  })

  it('renders the loading state while the request is in flight', async () => {
    const { budgetApi } = await import('../../services/api')
    vi.mocked(budgetApi.getHistoryStats).mockReturnValue(new Promise(() => {}) as never)
    const wrapper = mountComponent()
    // Loads via onMounted (isLoading starts false), so let that tick run — the
    // request never resolves, so loading stays on.
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
  })

  it('renders the summary + breakdown after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.summary-cards').exists()).toBe(true)
    expect(wrapper.text()).toContain('$12.50') // totalCost
  })

  it('shows the empty state (not an error) when there is genuinely no data', async () => {
    const { budgetApi } = await import('../../services/api')
    vi.mocked(budgetApi.getHistoryStats).mockResolvedValue({ periods: [] } as never)
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
    expect(wrapper.find('.ds-error-state').exists()).toBe(false)
  })

  // Regression: a failed load used to silently fall through to the empty state,
  // indistinguishable from real zero-data. It must now show a distinct error.
  it('shows a distinct error state (not empty) when the load fails, and retries', async () => {
    const { budgetApi, ApiError } = await import('../../services/api')
    vi.mocked(budgetApi.getHistoryStats).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(true)
    expect(wrapper.find('.ds-empty-state').exists()).toBe(false) // NOT masquerading as empty
    expect(wrapper.find('.summary-cards').exists()).toBe(false) // no misleading $0.00 cards
    expect(mockShowToast).toHaveBeenCalledWith('boom', 'error')

    vi.mocked(budgetApi.getHistoryStats).mockResolvedValueOnce({ periods: mockPeriods } as never)
    await wrapper.find('.ds-error-state button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(false)
    expect(wrapper.find('.summary-cards').exists()).toBe(true)
    expect(budgetApi.getHistoryStats).toHaveBeenCalledTimes(2)
  })
})
