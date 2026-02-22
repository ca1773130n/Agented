import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import WorkflowsPage from '../WorkflowsPage.vue'

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
}))

const mockWorkflows = [
  {
    id: 'wf-abc123',
    name: 'Deploy Pipeline',
    description: 'Automated deployment workflow',
    trigger_type: 'manual',
    enabled: 1,
    created_at: '2026-02-16T00:00:00Z',
  },
  {
    id: 'wf-def456',
    name: 'Data Sync',
    description: 'Scheduled data synchronization',
    trigger_type: 'cron',
    enabled: 0,
    created_at: '2026-02-16T00:00:00Z',
  },
]

vi.mock('../../services/api', () => ({
  workflowApi: {
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

describe('WorkflowsPage', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(WorkflowsPage, {
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
    const { workflowApi } = await import('../../services/api')
    vi.mocked(workflowApi.list).mockResolvedValue({ workflows: mockWorkflows })
    vi.mocked(workflowApi.create).mockResolvedValue({ message: 'Created', workflow_id: 'wf-new123' })
    vi.mocked(workflowApi.delete).mockResolvedValue({ message: 'Deleted' })
  })

  it('renders loading state initially', async () => {
    const { workflowApi } = await import('../../services/api')
    // Make list return a promise that doesn't resolve
    vi.mocked(workflowApi.list).mockReturnValue(new Promise(() => {}))
    const wrapper = mountComponent()
    expect(wrapper.find('.ds-loading-state').exists()).toBe(true)
    expect(wrapper.text()).toContain('Loading workflows')
  })

  it('renders list of workflows after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.text()).toContain('Deploy Pipeline')
    expect(wrapper.text()).toContain('Data Sync')
    expect(wrapper.findAll('.wf-card').length).toBe(2)
  })

  it('filters workflows by search query', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    const searchInput = wrapper.find('.search-input')
    await searchInput.setValue('deploy')
    await flushPromises()

    const cards = wrapper.findAll('.wf-card')
    expect(cards.length).toBe(1)
    expect(wrapper.text()).toContain('Deploy Pipeline')
    expect(wrapper.text()).not.toContain('Data Sync')
  })

  it('creates a new workflow', async () => {
    const { workflowApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Open create modal
    const createBtn = wrapper.findAll('button').find(b => b.text().includes('Create Workflow'))
    expect(createBtn).toBeDefined()
    await createBtn!.trigger('click')
    await flushPromises()

    // Fill the form (modal is stubbed so it renders inline)
    const inputs = wrapper.findAll('input[type="text"]')
    const nameInput = inputs.find(i => i.attributes('placeholder')?.includes('deploy-pipeline'))
    expect(nameInput).toBeDefined()
    await nameInput!.setValue('Test Workflow')

    const textarea = wrapper.find('textarea')
    await textarea.setValue('Test description')

    // Submit
    const modalBtns = wrapper.findAll('.modal-footer button')
    const submitBtn = modalBtns.find(b => b.text().includes('Create'))
    expect(submitBtn).toBeDefined()
    await submitBtn!.trigger('click')
    await flushPromises()

    expect(workflowApi.create).toHaveBeenCalledWith({
      name: 'Test Workflow',
      description: 'Test description',
      trigger_type: 'manual',
    })
    expect(mockShowToast).toHaveBeenCalledWith('Workflow created successfully', 'success')
  })

  it('deletes a workflow', async () => {
    const { workflowApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Click delete button on first card
    const deleteBtn = wrapper.findAll('.btn-danger')[0]
    expect(deleteBtn).toBeDefined()
    await deleteBtn!.trigger('click')
    await flushPromises()

    // Confirm in the delete modal (stubbed teleport renders inline)
    expect(wrapper.text()).toContain('Delete Workflow')
    const modalFooterBtns = wrapper.findAll('.modal-footer .btn-danger')
    expect(modalFooterBtns.length).toBeGreaterThan(0)
    await modalFooterBtns[0].trigger('click')
    await flushPromises()

    expect(workflowApi.delete).toHaveBeenCalledWith('wf-abc123')
    expect(mockShowToast).toHaveBeenCalledWith('Workflow "Deploy Pipeline" deleted', 'success')
  })

  it('navigates to builder on card click', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    const firstCard = wrapper.findAll('.wf-card')[0]
    expect(firstCard).toBeDefined()
    await firstCard!.trigger('click')

    expect(mockPush).toHaveBeenCalledWith({
      name: 'workflow-builder',
      params: { workflowId: 'wf-abc123' },
    })
  })

  it('shows empty state when no workflows exist', async () => {
    const { workflowApi } = await import('../../services/api')
    vi.mocked(workflowApi.list).mockResolvedValue({ workflows: [] })

    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
    expect(wrapper.text()).toContain('No workflows yet')
  })

  it('displays trigger type badges', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.trigger-manual').exists()).toBe(true)
    expect(wrapper.find('.trigger-cron').exists()).toBe(true)
  })

  it('displays enabled/disabled status badges', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    expect(wrapper.find('.ds-status-success').exists()).toBe(true)
    expect(wrapper.find('.ds-status-neutral').exists()).toBe(true)
  })

  it('shows search empty state when filter matches nothing', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    const searchInput = wrapper.find('.search-input')
    await searchInput.setValue('nonexistent')
    await flushPromises()

    expect(wrapper.find('.ds-empty-state').exists()).toBe(true)
    expect(wrapper.text()).toContain('No matching workflows')
  })
})
