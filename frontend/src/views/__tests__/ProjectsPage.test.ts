import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ProjectsPage from '../ProjectsPage.vue'
import type { Project } from '../../services/api'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ query: {}, params: {}, hash: '' }),
}))

const mockProjects = [
  { id: 'proj-1', name: 'Web App', description: 'Main app', status: 'active', github_repo: 'org/web', product_id: null, created_at: '2026-01-01T00:00:00Z' },
  { id: 'proj-2', name: 'API Service', description: 'Backend', status: 'active', github_repo: 'org/api', product_id: null, created_at: '2026-01-02T00:00:00Z' },
] as unknown as Project[]

vi.mock('../../services/api', () => ({
  projectApi: { list: vi.fn(), create: vi.fn(), delete: vi.fn() },
  productApi: { list: vi.fn() },
  teamApi: { list: vi.fn() },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) { super(message); this.status = status }
  },
}))

describe('ProjectsPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(ProjectsPage, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { projectApi, productApi, teamApi } = await import('../../services/api')
    vi.mocked(projectApi.list).mockResolvedValue({ projects: mockProjects })
    vi.mocked(productApi.list).mockResolvedValue({ products: [] })
    vi.mocked(teamApi.list).mockResolvedValue({ teams: [] })
    vi.mocked(projectApi.delete).mockResolvedValue({ message: 'Deleted' })
  })

  it('renders the loading state initially', async () => {
    const { projectApi } = await import('../../services/api')
    vi.mocked(projectApi.list).mockReturnValue(new Promise(() => {}))
    const wrapper = mountComponent()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
  })

  it('renders the project list after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.text()).toContain('Web App')
    expect(wrapper.text()).toContain('API Service')
    expect(wrapper.findAll('.project-card').length).toBe(2)
  })

  it('shows the empty state when there are no projects', async () => {
    const { projectApi } = await import('../../services/api')
    vi.mocked(projectApi.list).mockResolvedValue({ projects: [] })
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
  })

  it('shows the error state and re-fetches on retry', async () => {
    const { projectApi, ApiError } = await import('../../services/api')
    vi.mocked(projectApi.list).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(true)
    expect(mockShowToast).toHaveBeenCalledWith('boom', 'error')

    vi.mocked(projectApi.list).mockResolvedValueOnce({ projects: mockProjects })
    await wrapper.find('.ds-error-state button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.ds-error-state').exists()).toBe(false)
    expect(wrapper.text()).toContain('Web App')
    expect(projectApi.list).toHaveBeenCalledTimes(2)
  })

  it('deletes a project after confirmation', async () => {
    const { projectApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Cards render newest-first, so target by name rather than index.
    const webAppCard = wrapper.findAll('.project-card').find((c) => c.text().includes('Web App'))
    expect(webAppCard).toBeDefined()
    await webAppCard!.find('.btn-danger').trigger('click')
    await flushPromises()

    await wrapper.find('.confirm-actions .btn-danger').trigger('click')
    await flushPromises()

    expect(projectApi.delete).toHaveBeenCalledWith('proj-1')
  })
})
