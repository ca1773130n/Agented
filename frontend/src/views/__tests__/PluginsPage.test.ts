import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { RouterLinkStub } from '@vue/test-utils'
import PluginsPage from '../PluginsPage.vue'
import type { Plugin } from '../../services/api'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ query: {}, params: {}, hash: '' }),
}))

const mockPlugins = [
  { id: 'plug-1', name: 'Slack Notifier', description: 'Posts to Slack', version: '1.0.0', status: 'published', author: 'acme', component_count: 3, created_at: '2026-01-01T00:00:00Z' },
  { id: 'plug-2', name: 'Linter Pack', description: 'Lints code', version: '0.2.0', status: 'draft', author: 'acme', component_count: 5, created_at: '2026-01-02T00:00:00Z' },
] as unknown as Plugin[]

vi.mock('../../services/api', () => ({
  pluginApi: { list: vi.fn(), create: vi.fn(), delete: vi.fn() },
  teamApi: { list: vi.fn() },
  marketplaceApi: { list: vi.fn() },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) { super(message); this.status = status }
  },
}))

describe('PluginsPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(PluginsPage, {
      global: {
        provide: { showToast: mockShowToast },
        stubs: { teleport: true, RouterLink: RouterLinkStub },
      },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { pluginApi, teamApi, marketplaceApi } = await import('../../services/api')
    vi.mocked(pluginApi.list).mockResolvedValue({ plugins: mockPlugins, total_count: mockPlugins.length })
    vi.mocked(pluginApi.delete).mockResolvedValue({ message: 'Deleted' })
    vi.mocked(teamApi.list).mockResolvedValue({ teams: [] })
    vi.mocked(marketplaceApi.list).mockResolvedValue({ marketplaces: [] })
  })

  it('renders the loading state initially', async () => {
    const { pluginApi } = await import('../../services/api')
    vi.mocked(pluginApi.list).mockReturnValue(new Promise(() => {}))
    const wrapper = mountComponent()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
  })

  it('renders the plugin list after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.text()).toContain('Slack Notifier')
    expect(wrapper.text()).toContain('Linter Pack')
    expect(wrapper.findAll('.plugin-card').length).toBe(2)
  })

  it('shows the empty state when there are no plugins', async () => {
    const { pluginApi } = await import('../../services/api')
    vi.mocked(pluginApi.list).mockResolvedValue({ plugins: [], total_count: 0 })
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
  })

  it('shows the error state and re-fetches on retry', async () => {
    const { pluginApi, ApiError } = await import('../../services/api')
    vi.mocked(pluginApi.list).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(true)
    expect(mockShowToast).toHaveBeenCalledWith('boom', 'error')

    vi.mocked(pluginApi.list).mockResolvedValueOnce({ plugins: mockPlugins, total_count: mockPlugins.length })
    await wrapper.find('.ds-error-state button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(false)
    expect(wrapper.text()).toContain('Slack Notifier')
    expect(pluginApi.list).toHaveBeenCalledTimes(2)
  })

  it('deletes a plugin after confirmation', async () => {
    const { pluginApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Target the card by name (list order is not index-stable across sorts).
    const slackCard = wrapper.findAll('.plugin-card').find((c) => c.text().includes('Slack Notifier'))
    expect(slackCard).toBeDefined()
    await slackCard!.find('.btn-danger').trigger('click')
    await flushPromises()

    // ConfirmModal renders the danger confirm button in .confirm-actions.
    await wrapper.find('.confirm-actions .btn-danger').trigger('click')
    await flushPromises()

    expect(pluginApi.delete).toHaveBeenCalledWith('plug-1')
  })
})
