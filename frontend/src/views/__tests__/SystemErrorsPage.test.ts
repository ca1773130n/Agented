import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SystemErrorsPage from '../SystemErrorsPage.vue'
import type { SystemError } from '../../services/api'

// Mock boundary: the api barrel the composable + page both import from
// (`../services/api` -> services/api/index.ts). Mocking here lets the real
// useSystemErrors() logic run (load/filter/retry/state transitions) while the
// network layer is controllable. ApiError is re-exported from the barrel.
vi.mock('../../services/api', () => ({
  systemErrorApi: {
    listErrors: vi.fn(),
    getError: vi.fn(),
    updateError: vi.fn(),
    retryFix: vi.fn(),
    getCounts: vi.fn(),
  },
  settingsApi: {
    get: vi.fn(),
    set: vi.fn(),
  },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  },
}))

// Fresh timestamps so relativeTime() renders the locale-independent-ish
// "just now" bucket and rows are deterministic.
const now = new Date().toISOString()
const mockErrors = [
  {
    id: 'err-1',
    timestamp: now,
    source: 'backend',
    category: 'cli_error',
    message: 'CLI process exited with code 1',
    error_hash: 'hash-aaa',
    status: 'new',
  },
  {
    id: 'err-2',
    timestamp: now,
    source: 'frontend',
    category: 'frontend_error',
    message: 'Unhandled rejection in component',
    error_hash: 'hash-bbb',
    status: 'investigating',
  },
] as unknown as SystemError[]

describe('SystemErrorsPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(SystemErrorsPage, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { systemErrorApi } = await import('../../services/api')
    vi.mocked(systemErrorApi.listErrors).mockResolvedValue({
      errors: mockErrors,
      total_count: mockErrors.length,
    })
    // Polling helper (startPolling -> setInterval) calls this; harmless no-op.
    vi.mocked(systemErrorApi.getCounts).mockResolvedValue({ counts: { new: 2 } })
    const { settingsApi } = await import('../../services/api')
    vi.mocked(settingsApi.get).mockResolvedValue({ key: 'autofix_backend', value: '' })
    vi.mocked(settingsApi.set).mockResolvedValue({ key: 'autofix_backend', value: 'codex' })
  })

  // ---- autofix backend picker -------------------------------------------
  // Tier-2 autofix used to be hardcoded to claude with no way to change it,
  // while running unattended and editing the working tree.

  it('offers all four backends and shows codex when the setting is unset', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    const select = wrapper.find('#autofix-backend')
    expect(select.exists()).toBe(true)
    expect(select.findAll('option').map((o) => o.attributes('value'))).toEqual([
      'codex',
      'claude',
      'gemini',
      'opencode',
    ])
    // Unset is first-run, not an error — the server applies the same default,
    // so showing codex is accurate rather than a guess.
    expect((select.element as HTMLSelectElement).value).toBe('codex')
  })

  it('shows the stored backend rather than the default', async () => {
    const { settingsApi } = await import('../../services/api')
    vi.mocked(settingsApi.get).mockResolvedValue({ key: 'autofix_backend', value: 'opencode' })

    const wrapper = mountComponent()
    await flushPromises()

    expect((wrapper.find('#autofix-backend').element as HTMLSelectElement).value).toBe('opencode')
  })

  it('persists the operator choice', async () => {
    const { settingsApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    await wrapper.find('#autofix-backend').setValue('gemini')
    await flushPromises()

    expect(settingsApi.set).toHaveBeenCalledWith('autofix_backend', 'gemini')
  })

  it('does not leave the control showing a backend that failed to save', async () => {
    // The dropdown is a claim about which account is about to be billed, so a
    // failed write must not read as a successful one.
    const { settingsApi } = await import('../../services/api')
    vi.mocked(settingsApi.get).mockResolvedValue({ key: 'autofix_backend', value: 'codex' })
    vi.mocked(settingsApi.set).mockRejectedValue(new Error('boom'))

    const wrapper = mountComponent()
    await flushPromises()
    await wrapper.find('#autofix-backend').setValue('claude')
    await flushPromises()

    expect((wrapper.find('#autofix-backend').element as HTMLSelectElement).value).toBe('codex')
    expect(mockShowToast).toHaveBeenCalledWith(expect.stringContaining('autofix'), 'error')
  })

  it('falls back to the default when the settings read fails', async () => {
    const { settingsApi } = await import('../../services/api')
    vi.mocked(settingsApi.get).mockRejectedValue(new Error('unreachable'))

    const wrapper = mountComponent()
    await flushPromises()

    expect((wrapper.find('#autofix-backend').element as HTMLSelectElement).value).toBe('codex')
  })

  it('renders the loading state initially', async () => {
    const { systemErrorApi } = await import('../../services/api')
    // Never resolves -> isLoading stays true with no errors yet.
    vi.mocked(systemErrorApi.listErrors).mockReturnValue(new Promise(() => {}))

    const wrapper = mountComponent()
    // loadErrors() runs on mount; isLoading flips true synchronously but the
    // DOM needs a tick to reflect it.
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.spinner').exists()).toBe(true)
    expect(wrapper.find('.state-container').exists()).toBe(true)
  })

  it('renders the error rows after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    const rows = wrapper.findAll('.errors-table tbody tr')
    expect(rows.length).toBe(2)
    expect(wrapper.text()).toContain('CLI process exited with code 1')
    expect(wrapper.text()).toContain('Unhandled rejection in component')
    // Source / status badges from the row template.
    expect(wrapper.text()).toContain('backend')
    expect(wrapper.text()).toContain('frontend')
  })

  it('shows the empty state when there are no errors', async () => {
    const { systemErrorApi } = await import('../../services/api')
    vi.mocked(systemErrorApi.listErrors).mockResolvedValue({ errors: [], total_count: 0 })

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.state-empty').exists()).toBe(true)
    expect(wrapper.find('.errors-table').exists()).toBe(false)
  })

  it('shows the error state and re-fetches on retry', async () => {
    const { systemErrorApi, ApiError } = await import('../../services/api')
    vi.mocked(systemErrorApi.listErrors).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    const errorState = wrapper.find('.state-error')
    expect(errorState.exists()).toBe(true)
    expect(wrapper.text()).toContain('boom')

    // Retry re-runs loadErrors(), which now succeeds.
    vi.mocked(systemErrorApi.listErrors).mockResolvedValueOnce({
      errors: mockErrors,
      total_count: mockErrors.length,
    })
    await wrapper.find('.state-error .btn-retry').trigger('click')
    await flushPromises()

    expect(wrapper.find('.state-error').exists()).toBe(false)
    expect(wrapper.text()).toContain('CLI process exited with code 1')
    expect(systemErrorApi.listErrors).toHaveBeenCalledTimes(2)
  })
})
