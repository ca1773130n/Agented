import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import McpServersPage from '../McpServersPage.vue'
import type { McpServer } from '../../services/api'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ query: {}, params: {}, hash: '' }),
}))

const mockServers = [
  {
    id: 'mcp-1', name: 'filesystem', display_name: null, description: 'Local FS access',
    server_type: 'stdio', command: 'npx', args: null, env_json: null, url: null,
    headers_json: null, timeout_ms: 30000, is_preset: 0, icon: null,
    documentation_url: null, npm_package: null, enabled: 1,
    created_at: '2026-01-01T00:00:00Z', updated_at: null, category: 'general',
  },
  {
    id: 'mcp-2', name: 'github', display_name: null, description: 'GitHub API',
    server_type: 'http', command: null, args: null, env_json: null,
    url: 'http://localhost:3001/sse', headers_json: null, timeout_ms: 30000,
    is_preset: 0, icon: null, documentation_url: null, npm_package: null, enabled: 1,
    created_at: '2026-01-02T00:00:00Z', updated_at: null, category: 'general',
  },
] as unknown as McpServer[]

vi.mock('../../services/api', () => ({
  mcpServerApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    testConnection: vi.fn(),
  },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) { super(message); this.status = status }
  },
}))

describe('McpServersPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(McpServersPage, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { mcpServerApi } = await import('../../services/api')
    vi.mocked(mcpServerApi.list).mockResolvedValue({ servers: mockServers, total_count: 2 })
    vi.mocked(mcpServerApi.delete).mockResolvedValue({ message: 'Deleted' })
  })

  it('renders the loading state initially', async () => {
    const { mcpServerApi } = await import('../../services/api')
    vi.mocked(mcpServerApi.list).mockReturnValue(new Promise(() => {}))
    const wrapper = mountComponent()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
  })

  it('renders the server list after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.text()).toContain('filesystem')
    expect(wrapper.text()).toContain('github')
    expect(wrapper.findAll('.server-card').length).toBe(2)
  })

  it('shows the empty state when there are no servers', async () => {
    const { mcpServerApi } = await import('../../services/api')
    vi.mocked(mcpServerApi.list).mockResolvedValue({ servers: [], total_count: 0 })
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
  })

  it('shows the error state and re-fetches on retry', async () => {
    const { mcpServerApi, ApiError } = await import('../../services/api')
    vi.mocked(mcpServerApi.list).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(true)
    expect(mockShowToast).toHaveBeenCalledWith('boom', 'error')

    vi.mocked(mcpServerApi.list).mockResolvedValueOnce({ servers: mockServers, total_count: 2 })
    await wrapper.find('.ds-error-state button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(false)
    expect(wrapper.text()).toContain('filesystem')
    expect(mcpServerApi.list).toHaveBeenCalledTimes(2)
  })

  it('deletes a server after confirmation', async () => {
    const { mcpServerApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Cards may sort, so target by name rather than index.
    const fsCard = wrapper.findAll('.server-card').find((c) => c.text().includes('filesystem'))
    expect(fsCard).toBeDefined()
    await fsCard!.find('.server-actions .btn-danger').trigger('click')
    await flushPromises()

    await wrapper.find('.confirm-actions .btn-danger').trigger('click')
    await flushPromises()

    expect(mcpServerApi.delete).toHaveBeenCalledWith('mcp-1')
  })
})
