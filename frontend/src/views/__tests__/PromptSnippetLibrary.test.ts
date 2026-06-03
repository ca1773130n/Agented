import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import PromptSnippetLibrary from '../PromptSnippetLibrary.vue'
import type { PromptSnippet } from '../../services/api'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ query: {}, params: {}, hash: '' }),
}))

const mockSnippets = [
  {
    id: 'snip-1',
    name: 'greeting',
    content: 'Hello, world!',
    description: 'A friendly greeting',
    is_global: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'snip-2',
    name: 'signoff',
    content: 'Best regards,\nThe Team',
    description: 'A closing snippet',
    is_global: 1,
    created_at: '2026-01-02T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  },
] as unknown as PromptSnippet[]

vi.mock('../../services/api', () => ({
  promptSnippetApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
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

describe('PromptSnippetLibrary', () => {
  const mockShowToast = vi.fn()

  function mountComponent() {
    return mount(PromptSnippetLibrary, {
      global: { provide: { showToast: mockShowToast }, stubs: { teleport: true } },
    })
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    const { promptSnippetApi } = await import('../../services/api')
    vi.mocked(promptSnippetApi.list).mockResolvedValue({ snippets: mockSnippets })
    vi.mocked(promptSnippetApi.delete).mockResolvedValue(undefined as unknown as void)
  })

  it('renders the loading state initially', async () => {
    const { promptSnippetApi } = await import('../../services/api')
    vi.mocked(promptSnippetApi.list).mockReturnValue(new Promise(() => {}))
    const wrapper = mountComponent()
    expect(wrapper.find('.loading-state').exists()).toBe(true)
  })

  it('renders the snippet list after loading', async () => {
    const wrapper = mountComponent()
    await flushPromises()
    // Names render as snippet refs: {{name}}
    expect(wrapper.text()).toContain('{{greeting}}')
    expect(wrapper.text()).toContain('{{signoff}}')
    expect(wrapper.findAll('.snippet-table tbody tr').length).toBe(2)
  })

  it('shows the empty state when there are no snippets', async () => {
    const { promptSnippetApi } = await import('../../services/api')
    vi.mocked(promptSnippetApi.list).mockResolvedValue({ snippets: [] })
    const wrapper = mountComponent()
    await flushPromises()
    expect(wrapper.find('.empty-state').exists()).toBe(true)
  })

  it('toasts the error message and shows no list when loading fails', async () => {
    const { promptSnippetApi, ApiError } = await import('../../services/api')
    vi.mocked(promptSnippetApi.list).mockRejectedValueOnce(new ApiError(500, 'boom'))

    const wrapper = mountComponent()
    await flushPromises()

    // This page reports load errors via toast only — no .ds-error-state.
    expect(mockShowToast).toHaveBeenCalledWith('boom', 'error')
    expect(wrapper.find('.snippet-table').exists()).toBe(false)
    // With zero snippets loaded it falls through to the empty state, not the table.
    expect(wrapper.find('.empty-state').exists()).toBe(true)
  })

  it('deletes a snippet after confirmation', async () => {
    const { promptSnippetApi } = await import('../../services/api')
    const wrapper = mountComponent()
    await flushPromises()

    // Target the row by name rather than index.
    const greetingRow = wrapper
      .findAll('.snippet-table tbody tr')
      .find((r) => r.text().includes('{{greeting}}'))
    expect(greetingRow).toBeDefined()
    await greetingRow!.find('.delete-btn').trigger('click')
    await flushPromises()

    // Confirm modal -> confirm delete button.
    await wrapper.find('.delete-confirm-btn').trigger('click')
    await flushPromises()

    expect(promptSnippetApi.delete).toHaveBeenCalledWith('snip-1')
    expect(mockShowToast).toHaveBeenCalledWith('Snippet deleted', 'success')
  })
})
