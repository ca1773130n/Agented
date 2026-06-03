import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SecretsVault from '../SecretsVault.vue'
import type { SecretMetadata, VaultStatus, RevealedSecret } from '../../services/api'

// SecretsVault does not use vue-router (no useRouter/useRoute import), so no
// vue-router mock is needed here.

const mockSecrets = [
  {
    id: 'sec-1',
    name: 'GITHUB_TOKEN',
    description: 'CI token',
    scope: 'global',
    created_by: 'user-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: null,
    last_accessed_at: null,
  },
  {
    id: 'sec-2',
    name: 'OPENAI_API_KEY',
    description: '',
    scope: 'global',
    created_by: 'user-1',
    created_at: '2026-01-02T00:00:00Z',
    updated_at: null,
    last_accessed_at: null,
  },
] as unknown as SecretMetadata[]

const configuredStatus = { configured: true, secret_count: 2 } as unknown as VaultStatus
const revealedSecret = {
  id: 'sec-1',
  name: 'GITHUB_TOKEN',
  value: 'ghp_supersecretvalue',
} as unknown as RevealedSecret

vi.mock('../../services/api', () => ({
  secretsApi: {
    getStatus: vi.fn(),
    list: vi.fn(),
    create: vi.fn(),
    delete: vi.fn(),
    reveal: vi.fn(),
  },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  },
}))

describe('SecretsVault', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(SecretsVault, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { secretsApi } = await import('../../services/api')
    vi.mocked(secretsApi.getStatus).mockResolvedValue(configuredStatus)
    vi.mocked(secretsApi.list).mockResolvedValue({ secrets: mockSecrets })
    vi.mocked(secretsApi.delete).mockResolvedValue({ message: 'Deleted' })
    vi.mocked(secretsApi.reveal).mockResolvedValue(revealedSecret)
  })

  it('renders the loading state initially', async () => {
    const { secretsApi } = await import('../../services/api')
    // Keep getStatus pending so isLoading stays true.
    vi.mocked(secretsApi.getStatus).mockReturnValue(new Promise(() => {}))
    const wrapper = mountComponent()
    // isLoading starts true, so the loading state is present on first render.
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
  })

  it('renders the secrets list after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(false)
    // One .secret-row per secret.
    expect(wrapper.findAll('.secret-row').length).toBe(2)
    // A name renders in the list.
    expect(wrapper.text()).toContain('GITHUB_TOKEN')
    expect(wrapper.text()).toContain('OPENAI_API_KEY')
    // Count badge reflects the two secrets.
    expect(wrapper.text()).toContain('2 secrets')
  })

  it('shows the shared EmptyState when there are no secrets', async () => {
    const { secretsApi } = await import('../../services/api')
    vi.mocked(secretsApi.list).mockResolvedValue({ secrets: [] })
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
    expect(wrapper.find('.secret-row').exists()).toBe(false)
  })

  it('shows the error card and re-fetches on retry', async () => {
    const { secretsApi, ApiError } = await import('../../services/api')
    vi.mocked(secretsApi.getStatus).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    // The view renders a custom `.error-card` (no shared `.ds-error-state`).
    expect(wrapper.find('.error-card').exists()).toBe(true)
    expect(wrapper.text()).toContain('boom')

    // Retry button re-runs loadSecrets; happy-path status + list resolve.
    await wrapper.find('.error-card button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.error-card').exists()).toBe(false)
    expect(wrapper.text()).toContain('GITHUB_TOKEN')
    // getStatus called once on mount (rejected) + once on retry.
    expect(secretsApi.getStatus).toHaveBeenCalledTimes(2)
  })

  it('shows the not-configured card when the vault has no keys', async () => {
    const { secretsApi } = await import('../../services/api')
    vi.mocked(secretsApi.getStatus).mockResolvedValue({
      configured: false,
      secret_count: 0,
    } as unknown as VaultStatus)
    const wrapper = mountComponent()
    await flushPromises()
    // Not-configured branch reuses `.error-card`; list() is never called.
    expect(wrapper.find('.error-card').exists()).toBe(true)
    expect(wrapper.find('.secret-row').exists()).toBe(false)
    expect(secretsApi.list).not.toHaveBeenCalled()
  })

  it('reveals a secret value via secretsApi.reveal and displays it', async () => {
    const { secretsApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Before reveal, the value is masked and the plaintext is absent.
    expect(wrapper.find('.revealed-value').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('ghp_supersecretvalue')

    const targetRow = wrapper.findAll('.secret-row').find((r) => r.text().includes('GITHUB_TOKEN'))
    expect(targetRow).toBeDefined()
    await targetRow!.find('.btn-reveal').trigger('click')
    await flushPromises()

    // reveal() is called with the secret id; the plaintext now renders.
    expect(secretsApi.reveal).toHaveBeenCalledWith('sec-1')
    expect(wrapper.find('.revealed-value').exists()).toBe(true)
    expect(wrapper.text()).toContain('ghp_supersecretvalue')
  })

  it('auto-re-masks a revealed secret after the timeout window', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mountComponent()
      await flushPromises()

      const targetRow = wrapper.findAll('.secret-row').find((r) => r.text().includes('GITHUB_TOKEN'))
      await targetRow!.find('.btn-reveal').trigger('click')
      await flushPromises()
      expect(wrapper.find('.revealed-value').exists()).toBe(true)

      // Plaintext must not linger in the DOM — it re-masks after the window.
      vi.advanceTimersByTime(30_000)
      await flushPromises()
      expect(wrapper.find('.revealed-value').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('ghp_supersecretvalue')
    } finally {
      vi.useRealTimers()
    }
  })

  it('deletes a secret via secretsApi.delete', async () => {
    const { secretsApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    const targetRow = wrapper.findAll('.secret-row').find((r) => r.text().includes('GITHUB_TOKEN'))
    expect(targetRow).toBeDefined()
    // This view deletes immediately on click (no confirm dialog).
    await targetRow!.find('.btn-delete').trigger('click')
    await flushPromises()

    expect(secretsApi.delete).toHaveBeenCalledWith('sec-1')
    // Row is removed from the list after a successful delete.
    expect(wrapper.findAll('.secret-row').length).toBe(1)
    expect(wrapper.text()).not.toContain('GITHUB_TOKEN')
  })
})
