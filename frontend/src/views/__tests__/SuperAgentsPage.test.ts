import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SuperAgentsPage from '../SuperAgentsPage.vue'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
}))

const mockSuperAgents = [
  {
    id: 'super-abc123',
    name: 'Code Reviewer',
    description: 'Reviews pull requests automatically',
    backend_type: 'claude',
    preferred_model: 'opus',
    max_concurrent_sessions: 3,
    enabled: 1,
    created_at: '2026-02-16T00:00:00Z',
  },
  {
    id: 'super-def456',
    name: 'Security Scanner',
    description: 'Scans code for vulnerabilities',
    backend_type: 'opencode',
    preferred_model: undefined,
    max_concurrent_sessions: 1,
    enabled: 0,
    created_at: '2026-02-16T00:00:00Z',
  },
]

vi.mock('../../services/api', () => ({
  superAgentApi: {
    list: vi.fn(),
    create: vi.fn(),
    delete: vi.fn(),
  },
  ApiError: class extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  },
}))

describe('SuperAgentsPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(SuperAgentsPage, {
      global: {
        provide: {
          showToast: mockShowToast,
        },
        stubs: {
          teleport: true,
        },
      },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { superAgentApi } = await import('../../services/api')
    vi.mocked(superAgentApi.list).mockResolvedValue({ super_agents: mockSuperAgents })
    vi.mocked(superAgentApi.create).mockResolvedValue({ message: 'Created', super_agent_id: 'super-new123' })
    vi.mocked(superAgentApi.delete).mockResolvedValue({ message: 'Deleted' })
  })

  it('renders loading state initially', async () => {
    const { superAgentApi } = await import('../../services/api')
    // Make list return a promise that doesn't resolve
    vi.mocked(superAgentApi.list).mockReturnValue(new Promise(() => {}))
    const wrapper = mountComponent()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
    expect(wrapper.text()).toContain('Loading super agents')
  })

  it('renders list of super agents after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.text()).toContain('Code Reviewer')
    expect(wrapper.text()).toContain('Security Scanner')
    expect(wrapper.findAll('.sa-card').length).toBe(2)
  })

  it('filters super agents by search query', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    const searchInput = wrapper.find('.search-input')
    await searchInput.setValue('reviewer')
    await flushPromises()

    // Only "Code Reviewer" should match (description "Reviews pull requests" also matches)
    const cards = wrapper.findAll('.sa-card')
    expect(cards.length).toBe(1)
    expect(wrapper.text()).toContain('Code Reviewer')
    expect(wrapper.text()).not.toContain('Security Scanner')
  })

  it('creates a new super agent', async () => {
    const { superAgentApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Open create modal
    const createBtn = wrapper.findAll('button').find(b => b.text().includes('Create SuperAgent'))
    expect(createBtn).toBeDefined()
    await createBtn!.trigger('click')
    await flushPromises()

    // Fill the form (modal is stubbed so it renders inline)
    const inputs = wrapper.findAll('input[type="text"]')
    const nameInput = inputs.find(i => i.attributes('placeholder')?.includes('code-reviewer'))
    expect(nameInput).toBeDefined()
    await nameInput!.setValue('Test Agent')

    const textarea = wrapper.find('textarea')
    await textarea.setValue('Test description')

    // Submit
    const modalBtns = wrapper.findAll('.modal-footer button')
    const submitBtn = modalBtns.find(b => b.text().includes('Create'))
    expect(submitBtn).toBeDefined()
    await submitBtn!.trigger('click')
    await flushPromises()

    expect(superAgentApi.create).toHaveBeenCalledWith({
      name: 'Test Agent',
      description: 'Test description',
      backend_type: 'claude',
    })
    expect(mockShowToast).toHaveBeenCalledWith('SuperAgent created successfully', 'success')
  })

  it('deletes a super agent', async () => {
    const { superAgentApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Click delete button on first card (stop propagation prevents card click)
    const deleteBtn = wrapper.findAll('.btn-danger')[0]
    expect(deleteBtn).toBeDefined()
    await deleteBtn!.trigger('click')
    await flushPromises()

    // Confirm in the delete modal (stubbed teleport renders inline)
    expect(wrapper.text()).toContain('Delete SuperAgent')
    const modalFooterBtns = wrapper.findAll('.modal-footer .btn-danger')
    expect(modalFooterBtns.length).toBeGreaterThan(0)
    await modalFooterBtns[0].trigger('click')
    await flushPromises()

    expect(superAgentApi.delete).toHaveBeenCalledWith('super-abc123')
    expect(mockShowToast).toHaveBeenCalledWith('SuperAgent "Code Reviewer" deleted', 'success')
  })

  it('navigates to playground on card click', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    const firstCard = wrapper.findAll('.sa-card')[0]
    expect(firstCard).toBeDefined()
    await firstCard!.trigger('click')

    expect(mockPush).toHaveBeenCalledWith({
      name: 'super-agent-playground',
      params: { superAgentId: 'super-abc123' },
    })
  })

  it('shows empty state when no super agents exist', async () => {
    const { superAgentApi } = await import('../../services/api')
    vi.mocked(superAgentApi.list).mockResolvedValue({ super_agents: [] })

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
    expect(wrapper.text()).toContain('No super agents yet')
  })

  it('shows empty state with search message when filter matches nothing', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    const searchInput = wrapper.find('.search-input')
    await searchInput.setValue('nonexistent')
    await flushPromises()

    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
    expect(wrapper.text()).toContain('No matching super agents')
  })

  it('displays backend type badges', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.backend-claude').exists()).toBe(true)
    expect(wrapper.find('.backend-opencode').exists()).toBe(true)
  })

  it('displays status badges correctly', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.status-active').exists()).toBe(true)
    expect(wrapper.find('.status-inactive').exists()).toBe(true)
  })
})
